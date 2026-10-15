"""HEAD-SPEC H11: seed the head ledger from a markdown doc. Numbered items and bullets under the chosen `## <n>`
headings (or every item in the file when no section is named) become head entries with src "import". Text is
redacted by roadmap/core/secrets.scrub (through the head's clean_text) before it is written, and an entry whose sha1
text hash is already in the ledger is skipped, so a second run adds nothing. Standard library only.

parse_doc() is pure: it reads the file and returns the candidate items. import_doc() also writes when a data dir is
given, through the head store service (roadmap/services/head.py) under the data-dir lock."""

import os
import re

from roadmap.core import head
from roadmap.errors import EXIT_NOT_FOUND, RoadmapError
from roadmap.services import head as svc
from roadmap.store import lock

SRC = "import"
_H2 = re.compile(r"^## +(\d+[a-z]?)\b", re.IGNORECASE)
_ITEM = re.compile(r"^ {0,3}(?:\d{1,3}[.)]|[-*+])\s+(\S.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_DECISION = re.compile(r"\b(decided|decision|chose|choose|we will use)\b", re.IGNORECASE)


def _wanted(sections):
    """The lower-cased section tokens to keep, or None for the whole file. Accepts '2,2b' or a list."""
    if sections is None:
        return None
    if isinstance(sections, str):
        sections = sections.split(",")
    tokens = {str(s).strip().lower() for s in sections if str(s).strip()}
    return tokens or None


def _kind_of(text):
    """ask for a question, decision for a decided item, otherwise rule (imported items are binding notes)."""
    if text.rstrip().endswith("?"):
        return "ask"
    if _DECISION.search(text):
        return "decision"
    return "rule"


def parse_doc(path, sections=None):
    """The candidate items of a markdown file as dicts {"kind", "text"}, in file order. Items are numbered or
    bullet lines (continuation lines join them), fenced code is skipped, and only the named `## <n>` sections are
    read when sections is given (e.g. "2,2b"). Raises not_found when the file is missing."""
    if not os.path.isfile(path):
        raise RoadmapError("not_found", "no doc at " + str(path), EXIT_NOT_FOUND)
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    wanted = _wanted(sections)
    items = []
    buf = None
    current = None
    in_fence = False

    def close():
        if buf:
            text = " ".join(buf).strip()
            if text:
                items.append({"kind": _kind_of(text), "text": text})

    for raw in lines:
        if _FENCE.match(raw):
            close()
            buf = None
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not raw.strip():
            close()
            buf = None
            continue
        if raw.startswith("## "):
            close()
            buf = None
            match = _H2.match(raw)
            current = match.group(1).lower() if match else None
            continue
        if raw.startswith("# "):
            close()
            buf = None
            current = None
            continue
        if raw.startswith("#") or _RULE_LINE.match(raw):
            close()
            buf = None
            continue
        match = _ITEM.match(raw)
        if match:
            close()
            buf = [match.group(1).strip()] if (wanted is None or current in wanted) else None
            continue
        if buf is not None:
            buf.append(raw.strip())
    close()
    return items


def _build(item, now=None):
    """One ledger entry (without id) and its redacted text, from a parsed item."""
    clean = svc.clean_text(item["text"])
    entry = {
        "v": head.VERSION, "t": "e", "ts": svc._ts(now), "src": SRC, "kind": item["kind"],
        "sum": svc.make_summary(clean), "len": len(clean), "h": svc._digest(clean),
    }
    return entry, clean


def import_doc(path, sections=None, data_dir=None, now=None):
    """Parse the doc and return one result per item: {"id", "status", "kind", "sum", "h"}. status is "new" (no
    data dir given: nothing is written), "logged" (written under the lock) or "skipped" (the same text hash is
    already in the ledger, or it repeats earlier in this doc). Writes only when data_dir is set."""
    built = [_build(item, now) for item in parse_doc(path, sections)]
    if data_dir is None:
        return [{"id": None, "status": "new", "kind": e["kind"], "sum": e["sum"], "h": e["h"]} for e, _ in built]
    results = []
    with lock.locked(data_dir, None):
        svc._adopt_locked(data_dir)
        known = {o.get("h") for o in svc._records(data_dir) if o.get("t") == "e"}
        for entry, clean in built:
            if entry["h"] in known:
                results.append({"id": None, "status": "skipped", "kind": entry["kind"], "sum": entry["sum"],
                                "h": entry["h"]})
                continue
            line = svc._append_entry_locked(data_dir, entry, clean)
            known.add(entry["h"])
            results.append({"id": line["id"], "status": "logged", "kind": line["kind"], "sum": line["sum"],
                            "h": line["h"]})
    return results
