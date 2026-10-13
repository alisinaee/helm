"""Registry of the optional roadmap extras: spikes, testing (RH checks) and the roadmap's Next up and Progress log.

Each extra is named in a project's roadmap.config.json under "extras". A string value is a file name;
an object value is {"file": ..., plus extra options}. Pure functions: the caller passes the file texts in.
"""

import re

from roadmap.core.mdtables import cell, classify, iter_tables, section

CONFIG_LABEL = "roadmap.config.json"

# the snapshot keys each extra fills in, and their empty values when the extra is not configured
EMPTY_OUTPUTS = {"spikes": [], "rh": [], "next": [], "log": []}
EXTRA_OUTPUTS = {"spikes": ("spikes",), "testing": ("rh",), "roadmap": ("next", "log")}


def extra_file(entry):
    """The file name of one extras entry, or None when the entry names no file."""
    if isinstance(entry, str):
        return entry or None
    if isinstance(entry, dict) and isinstance(entry.get("file"), str) and entry["file"]:
        return entry["file"]
    return None


def _spikes(text, entry):
    spikes = []
    for head, rows in iter_tables(text):
        if not head or head[0] != "Spike" or "Status" not in head:
            continue
        si = head.index("Status")
        di = head.index("Date") if "Date" in head else -1
        ti = head.index("Details") if "Details" in head else -1
        for r in rows:
            if not r or not re.fullmatch(r"S\d+", r[0]):
                continue
            status = cell(r, si)
            spikes.append({
                "id": r[0],
                "label": cell(r, 1),
                "status": status,
                "state": classify(status),
                "date": cell(r, di) if di >= 0 else "",
                "details": cell(r, ti) if ti >= 0 else "",
            })
    if not spikes:
        raise ValueError("no spike rows found in the scoreboard table")
    return {"spikes": spikes}


def _testing(text, entry):
    heading = entry.get("section") if isinstance(entry, dict) else None
    body = section(text, heading) if heading else text
    rh = []
    for _head, rows in iter_tables(body):
        for r in rows:
            if r and re.fullmatch(r"RH\d+", r[0]):
                status = r[-1]
                rh.append({
                    "id": r[0],
                    "label": cell(r, 1),
                    "status": status,
                    "state": classify(status),
                })
    if not rh:
        raise ValueError("no RH rows found in section " + heading if heading else "no RH rows found")
    return {"rh": rh}


def _parse_next(text, heading):
    items = []
    for line in section(text, heading).splitlines():
        m = re.match(r"\s*\d+\.\s+(.*\S)", line)
        if m:
            items.append(m.group(1))
    return items


def _parse_log(text, heading):
    rows = []
    for _head, body in iter_tables(section(text, heading)):
        for r in body:
            if r and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0]):
                rows.append({"date": r[0], "text": cell(r, 1)})
    rows.sort(key=lambda x: x["date"], reverse=True)   # stable: ties keep file order
    return rows[:8]


def _roadmap(text, entry):
    opts = entry if isinstance(entry, dict) else {}
    nxt = _parse_next(text, opts["next"]) if opts.get("next") else []
    log = _parse_log(text, opts["log"]) if opts.get("log") else []
    return {"next": nxt, "log": log}


PARSERS = {"spikes": _spikes, "testing": _testing, "roadmap": _roadmap}


def parse_extras(extras, files):
    """Parse every configured extra. Returns (outputs, errors).

    extras: the "extras" object from roadmap.config.json (or None). files: name -> text, None when missing.
    outputs always holds every snapshot key; an extra that is not configured leaves its keys empty.
    Extras are parsed in the fixed order of PARSERS, so the errors list has a stable order.
    """
    extras = extras if isinstance(extras, dict) else {}
    outputs = {k: list(v) if isinstance(v, list) else v for k, v in EMPTY_OUTPUTS.items()}
    errors = []
    for kind in PARSERS:
        if kind not in extras:
            continue
        entry = extras[kind]
        name = extra_file(entry)
        if name is None:
            errors.append({"file": CONFIG_LABEL, "error": "ValueError: extras.%s names no file" % kind})
            continue
        text = files.get(name)
        if text is None:
            errors.append({"file": name, "error": "FileNotFoundError: file not found"})
            continue
        try:
            found = PARSERS[kind](text, entry)
        except Exception as exc:  # a bad extra must not break the others
            errors.append({"file": name, "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        for key in EXTRA_OUTPUTS[kind]:
            outputs[key] = found.get(key, outputs[key])
    unknown = sorted(k for k in extras if k not in PARSERS)
    for kind in unknown:
        errors.append({"file": CONFIG_LABEL, "error": "ValueError: unknown extra '%s'" % kind})
    return outputs, errors
