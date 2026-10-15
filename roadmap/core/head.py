"""Head section core (HEAD-SPEC section 2, 6): the pure fold of head.jsonl and the stdlib heuristics.

Every function is pure: no file, clock or network access unless `now` is left out of `fold`.
Records that a newer writer may add (unknown `t`, a `v` other than 1, bad JSON) are skipped, never fatal.
"""

import json
import re
from datetime import datetime, timezone

from roadmap.core import planfmt

VERSION = 1
RECORD_TYPES = ("e", "u", "s")
LINK_KINDS = ("task", "sub", "issue", "feature", "question", "backlog", "review", "rule", "doc", "commit", "job", "ask")
MAX_LINKS = 6
MANUAL_STATUSES = ("merged", "declined", "needs-you", "done", "open")
ACTIVE_LINK_STATES = ("doing", "partial", "running")
BLOCKED_LINK_STATES = ("hold", "blocked")
FAILED_LINK_STATES = ("failed",)
CLOSED_STATUSES = ("done", "declined", "merged")
DUP_MIN = 0.6
DUP_WINDOW_DAYS = 30
BIND_MIN = 0.25
BIND_MAX = 2
ID_MENTION = re.compile(r"\b[A-Za-z]{1,3}-?\d+(?:\.\d+)*\b")

# Ordered: the first matching row wins. Matching is case-insensitive.
KIND_TABLE = (
    ("bug", r"\bbugs?\b|\bbroken\b|\berror|does not work|doesn'?t work|\bwrong\b|\bfails?\b|\b404\b"),
    ("rule", r"\balways\b|\bnever\b|\bmust\b|\brules?\b|from now on|\bdon['’]?t\b|\bdo not\b"),
    ("decision", r"^\s*(yes|no)\b|\bgo with\b|\bdecided\b|\bi choose\b"),
    ("preference", r"\bi (like|prefer)\b|\bi want\b.*\bto be\b"),
    ("review", r"\breview\b|\baudit\b|\bcheck\b"),
)
IMPERATIVE_START = frozenset((
    "add", "fix", "make", "run", "show", "change", "update", "build", "write", "tell", "move",
    "remove", "delete", "create", "list", "set", "use", "keep", "put", "send", "split", "rename",
))
FILLER_WORDS = re.compile(r"\b(please|also|kindly|actually|just)\b[,]?\s*", re.IGNORECASE)
LEAD_FILLER = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|so|and|then|now|well)\b[,.!]?\s*", re.IGNORECASE)
LEAD_TELL = re.compile(r"^tell \w+( \w+)?:\s*", re.IGNORECASE)
CLAUSE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n")
SUM_MAX = 100
STOPWORDS = frozenset((
    "a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "but", "is", "are", "was", "be", "it",
    "this", "that", "with", "as", "at", "by", "from", "i", "you", "we", "my", "our", "your", "me", "so",
    "do", "does", "did", "please", "also", "just",
))
WORD = re.compile(r"[a-z0-9]+")


def parse_ts(value):
    """ISO UTC text like '2026-10-15T09:12:03Z' as an aware datetime, or None when it is not that."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_link(ref):
    """'task:R7.31' -> ('task', 'R7.31'). None when the kind is unknown or the value is empty."""
    if not isinstance(ref, str) or ":" not in ref:
        return None
    kind, _, value = ref.partition(":")
    if kind not in LINK_KINDS or not value.strip():
        return None
    return kind, value.strip()


def parse_lines(lines):
    """Parse head.jsonl lines. Returns (records, skipped): skipped counts bad JSON, unknown `t`, and any `v` other than 1."""
    records, skipped = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(rec, dict) or rec.get("v") != VERSION or rec.get("t") not in RECORD_TYPES:
            skipped += 1
            continue
        records.append(rec)
    return records, skipped


def summarize(text):
    """One-line summary: fillers and greetings dropped, the first clause of 2+ words, cut to 100 chars."""
    text = " ".join(str(text or "").split())
    text = LEAD_TELL.sub("", text)
    text = LEAD_FILLER.sub("", text)
    text = FILLER_WORDS.sub("", text).strip()
    clauses = [c.strip() for c in CLAUSE_SPLIT.split(text) if c.strip()]
    chosen = next((c for c in clauses if len(c.split()) >= 2), text)
    if len(chosen) <= SUM_MAX:
        return chosen
    cut = chosen[:SUM_MAX - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def guess_kind(text):
    """Heuristic kind with a '?' suffix (a guess until the head triages). Table order: bug, rule, decision,
    preference, review, question, ask."""
    text = " ".join(str(text or "").split())
    lowered = text.lower()
    for kind, pattern in KIND_TABLE:
        if re.search(pattern, lowered):
            return kind + "?"
    words = WORD.findall(lowered)
    if text.endswith("?") and words and words[0] not in IMPERATIVE_START:
        return "question?"
    return "ask?"


def word_set(text):
    """Lower-case words without stopwords, as a set."""
    return {w for w in WORD.findall(str(text or "").lower()) if w not in STOPWORDS}


def jaccard(a, b):
    """Jaccard similarity of the stopword-free word sets of two texts. 0.0 when either is empty."""
    wa, wb = word_set(a), word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def suggest_binds(text, tasks, issues):
    """Refs ('task:R7.31', 'issue:I4') the text most likely belongs to, best first, at most BIND_MAX.

    An id written in the text (R7.31, I4) that is a known task or issue scores 1.0. Otherwise the score is the
    Jaccard of the word sets of text and title. Below BIND_MIN nothing is suggested. Pure: a suggestion only.
    tasks and issues are lists of dicts with 'id' and 'title'; rows without a string id are skipped.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return []
    mentioned = {m.group(0).upper() for m in ID_MENTION.finditer(text)}
    scored = []
    order = 0
    for kind, rows in (("task", tasks), ("issue", issues)):
        for row in rows or []:
            rid = row.get("id") if isinstance(row, dict) else None
            if not isinstance(rid, str) or not rid:
                continue
            score = 1.0 if rid.upper() in mentioned else jaccard(text, row.get("title"))
            if score >= BIND_MIN:
                scored.append((-score, order, "%s:%s" % (kind, rid)))
            order += 1
    scored.sort()
    refs = [ref for _, _, ref in scored[:BIND_MAX]]
    # An umbrella task (R7.31) may not be the only bind of an open ask (HEAD-SPEC 12), so it is suggested only
    # next to a real task or issue.
    if all(_umbrella_ref(ref) for ref in refs):
        return []
    return refs


def _umbrella_ref(ref):
    kind, _, rid = ref.partition(":")
    return kind == "task" and planfmt.is_umbrella_task(rid)


def _status(entry, link_state):
    links = entry["links"]
    states = [link_state.get(ref) for ref in links]
    manual = entry["manual"]
    if manual in ("merged", "declined", "needs-you"):
        return manual, False
    if manual == "done":
        return "done", False
    if manual is None and links and all(s == "done" for s in states):
        return "done", True
    if any(s in FAILED_LINK_STATES for s in states):
        return "failed", False
    if any(s in BLOCKED_LINK_STATES for s in states):
        return "blocked", False
    if any(s in ACTIVE_LINK_STATES for s in states):
        return "doing", False
    if links:
        return "bound", False
    if entry["triaged"]:
        return "understood", False
    return "new", False


def fold(records, link_state=None, now=None, amber_min=30, stale_min=120):
    """Fold records into one dict per entry, in file order.

    link_state maps a link ref ('task:R7.31', 'job:j599') to 'done', 'doing', 'partial', 'running' or 'open'.
    Status rules, first match wins: merged/declined/needs-you when set by hand; done when set by hand, or
    (auto) when every link is done and the entry has links; failed when a link is failed (a failed job); blocked
    when a link is on hold or blocked; doing when a linked task is doing or partial or a job runs; bound when it has
    a link; understood when the head triaged it; new otherwise.
    age_min, amber and stale apply to new and understood entries only. carried: open, and from a session that
    started before the current head's claim.
    """
    link_state = link_state or {}
    now = now or datetime.now(timezone.utc)
    entries, order = {}, []
    session_start = {}
    claim = None  # (datetime, sid) of the latest claim record
    for rec in records:
        kind = rec.get("t")
        if kind == "e":
            eid = rec.get("id")
            if not isinstance(eid, str) or eid in entries:
                continue
            entries[eid] = {
                "id": eid, "ts": rec.get("ts"), "src": rec.get("src"), "sid": rec.get("sid"),
                "acct": rec.get("acct"), "kind": rec.get("kind"), "sum": rec.get("sum") or "",
                "from": rec.get("from"), "links": [], "manual": None, "triaged": False, "into": None,
            }
            order.append(eid)
        elif kind == "u":
            entry = entries.get(rec.get("id"))
            if entry is not None:
                _apply_update(entry, rec)
        elif kind == "s":
            ts = parse_ts(rec.get("ts"))
            sid = rec.get("sid")
            if ts and sid and (sid not in session_start or ts < session_start[sid]):
                session_start[sid] = ts
            if ts and rec.get("ev") == "claim":
                claim = (ts, sid)

    rows = []
    for eid in order:
        entry = entries[eid]
        status, auto = _status(entry, link_state)
        entry["status"] = status
        entry["auto_done"] = auto
        rows.append(entry)

    for entry in rows:
        ts = parse_ts(entry["ts"])
        open_now = entry["status"] not in CLOSED_STATUSES
        age = None
        if entry["status"] in ("new", "understood") and ts:
            age = max(0.0, (now - ts).total_seconds() / 60.0)
        entry["age_min"] = age
        entry["amber"] = age is not None and age > amber_min
        entry["stale"] = age is not None and age > stale_min
        entry["carried"] = False
        if open_now and claim and entry["sid"] != claim[1]:
            start = session_start.get(entry["sid"], ts)
            entry["carried"] = start is not None and start < claim[0]

    for i, entry in enumerate(rows):
        entry["dup"] = _best_dup(entry, rows[:i], now)
    return rows


def _apply_update(entry, rec):
    sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
    status = sets.get("status")
    if status in MANUAL_STATUSES:
        entry["manual"] = status
    if "kind" in sets:
        entry["kind"] = sets["kind"]
    if "sum" in sets:
        entry["sum"] = sets["sum"]
    if "into" in sets:
        entry["into"] = sets["into"]
    if rec.get("by") == "head" and "kind" in sets and "sum" in sets:
        entry["triaged"] = True
    for ref in rec.get("link") or []:
        if not isinstance(ref, str) or len(ref) < 2 or ref[0] not in "+-":
            continue
        name = ref[1:]
        if ref[0] == "-":
            if name in entry["links"]:
                entry["links"].remove(name)
        elif parse_link(name) and name not in entry["links"] and len(entry["links"]) < MAX_LINKS:
            entry["links"].append(name)


def _best_dup(entry, earlier, now):
    """Best earlier entry at Jaccard >= 0.6 that is open or within 30 days. A suggestion only, never merged."""
    ts = parse_ts(entry["ts"]) or now
    best = None
    for other in earlier:
        other_ts = parse_ts(other["ts"])
        recent = other_ts is not None and abs((ts - other_ts).total_seconds()) <= DUP_WINDOW_DAYS * 86400
        if other["status"] not in CLOSED_STATUSES or recent:
            score = jaccard(entry["sum"], other["sum"])
            if score >= DUP_MIN and (best is None or score > best[1]):
                best = (other["id"], score)
    if best is None:
        return None
    return {"id": best[0], "score": round(best[1], 2)}
