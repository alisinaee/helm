"""Plan text format for roadmap tasks and phases, and the bulk "set" line format. Pure functions, no I/O.

Grammar and examples: docs/AGENT-INTERFACE.md section 2. Every problem is reported as
"line N: <problem> (allowed: ...)" so an agent can fix the line and retry.
"""

import datetime
import re
import shlex

PHASE_STATUSES = ("todo", "partial", "done", "hold")
TASK_STATUSES = PHASE_STATUSES
MODELS = ("haiku", "sonnet", "opus")
THINKING = ("low", "medium", "high")
CHECKS = ("none", "sonnet", "opus")
SET_KEYS = ("status", "tokensK", "model", "thinking", "needsUser", "check", "checkK", "note", "title")
PLAN_ALLOWED = ("P <id> <status> | <name>  or  T <id> <status> <tokensK> <model>/<thinking> "
                "[!] [c:<check>/<checkK>] | <title> [# <note>]")
SET_ALLOWED = "<id> key=value ...; keys: " + ", ".join(SET_KEYS)
_KEEP = object()  # marks a set value of "-": keep the current value

PHASE_ID_RE = re.compile(r"^[A-Za-z0-9]+$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9]+\.[0-9]+$")
ANY_ID_RE = re.compile(r"^[A-Za-z0-9]+(\.[0-9]+)?$")
_INT_RE = re.compile(r"^[0-9]+$")
_FENCE = ("```", "~~~")
_BLOCK_TAG = "roadmap-plan"


def _problem(lineno, text):
    return "line " + str(lineno) + ": " + text


def _enum(values, dash=True):
    return "|".join(list(values) + (["-"] if dash else []))


def extract_block(md):
    """Return the body of the first fenced block tagged roadmap-plan, or None when there is none.
    Other fenced blocks are skipped whole, so a tag inside them never counts."""
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        fence = next((f for f in _FENCE if stripped.startswith(f)), None)
        if fence is None:
            i += 1
            continue
        tag = stripped[len(fence):].strip()
        j = i + 1
        body = []
        while j < len(lines) and lines[j].strip() != fence:
            body.append(lines[j])
            j += 1
        if tag == _BLOCK_TAG:
            return "\n".join(body) + "\n"
        i = j + 1
    return None


def parse_plan(text):
    """Parse plan text into (records, errors). Records keep file order; each has "kind" ("phase" or "task"),
    "line" and its fields. A None field means "-" or absent: keep the current value on update, the default on create.
    Parsing checks syntax and duplicate ids in the input only; referential checks happen in the service."""
    records = []
    errors = []
    seen = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head = line.split(None, 1)[0]
        if head == "P":
            rec, problem = _parse_phase(line, lineno)
        elif head == "T":
            rec, problem = _parse_task(line, lineno)
        else:
            rec, problem = None, _problem(lineno, "unknown record '" + head + "' (allowed: P, T, #, blank)")
        if problem is not None:
            errors.append(problem)
            continue
        key = (rec["kind"], rec["id"])
        if key in seen:
            errors.append(_problem(lineno, "duplicate " + rec["kind"] + " id " + rec["id"]
                                   + " (first on line " + str(seen[key]) + ")"
                                   + " (allowed: each id once per input)"))
            continue
        seen[key] = lineno
        records.append(rec)
    return records, errors


def _parse_phase(line, lineno):
    head, sep, name = line.partition("|")
    tokens = head.split()
    if not sep or len(tokens) != 3:
        return None, _problem(lineno, "phase line needs an id, a status and '| name' (allowed: " + PLAN_ALLOWED + ")")
    _, pid, status = tokens
    if not PHASE_ID_RE.match(pid):
        return None, _problem(lineno, "phase id '" + pid + "' has a dot or a symbol (allowed: letters and digits)")
    if status not in PHASE_STATUSES + ("-",):
        return None, _problem(lineno, "status '" + status + "' is not valid (allowed: " + _enum(PHASE_STATUSES) + ")")
    name = name.strip()
    if not name:
        return None, _problem(lineno, "phase name is empty (allowed: text after the '|')")
    rec = {"kind": "phase", "line": lineno, "id": pid, "name": name,
           "status": None if status == "-" else status}
    return rec, None


def _parse_task(line, lineno):
    shape = "task line needs an id, status, tokensK, model/thinking and '| title' (allowed: " + PLAN_ALLOWED + ")"
    head, sep, rest = line.partition("|")
    tokens = head.split()
    if not sep or len(tokens) < 5:
        return None, _problem(lineno, shape)
    tid, status, tokens_text, mt = tokens[1], tokens[2], tokens[3], tokens[4]
    if not TASK_ID_RE.match(tid):
        return None, _problem(lineno, "task id '" + tid + "' must look like P1.2 (allowed: <phase>.<number>)")
    if status not in TASK_STATUSES + ("-",):
        return None, _problem(lineno, "status '" + status + "' is not valid (allowed: " + _enum(TASK_STATUSES) + ")")
    tokens_k = _whole(tokens_text)
    if tokens_text != "-" and tokens_k is None:
        return None, _problem(lineno, "tokensK '" + tokens_text + "' is not a whole number (allowed: 0, 1, 2 ... or -)")
    model, slash, thinking = mt.partition("/")
    if not slash:
        return None, _problem(lineno, "model/thinking '" + mt + "' needs a slash (allowed: "
                              + _enum(MODELS) + "/" + _enum(THINKING) + ")")
    if model not in MODELS + ("-",):
        return None, _problem(lineno, "model '" + model + "' is not valid (allowed: " + _enum(MODELS) + ")")
    if thinking not in THINKING + ("-",):
        return None, _problem(lineno, "thinking '" + thinking + "' is not valid (allowed: " + _enum(THINKING) + ")")
    needs = None
    check = None
    check_k = None
    idx = 5
    if idx < len(tokens) and tokens[idx] == "!":
        needs = True
        idx += 1
    if idx < len(tokens) and tokens[idx].startswith("c:"):
        check, check_k, problem = _parse_check(tokens[idx][2:], lineno)
        if problem is not None:
            return None, problem
        idx += 1
    if idx != len(tokens):
        return None, _problem(lineno, "unexpected '" + tokens[idx] + "' (allowed: !, c:<check>/<checkK>)")
    title, hashsep, note = rest.partition(" # ")
    if not hashsep and rest.rstrip().endswith(" #"):
        return None, _problem(lineno, "note is empty (allowed: '# ' followed by text)")
    title = title.strip()
    if not title:
        return None, _problem(lineno, "task title is empty (allowed: text after the '|')")
    note = note.strip() if hashsep else None
    if hashsep and not note:
        return None, _problem(lineno, "note is empty (allowed: '# ' followed by text)")
    rec = {"kind": "task", "line": lineno, "id": tid, "phase": tid.split(".")[0],
           "title": title, "status": None if status == "-" else status,
           "tokensK": tokens_k, "thinking": None if thinking == "-" else thinking,
           "model": None if model == "-" else model, "needsUser": needs,
           "check": check, "checkK": check_k, "note": note}
    return rec, None


def _parse_check(text, lineno):
    name, slash, number = text.partition("/")
    if not slash:
        return None, None, _problem(lineno, "check '" + text + "' needs a slash (allowed: c:<check>/<checkK>)")
    if name not in CHECKS + ("-",):
        return None, None, _problem(lineno, "check '" + name + "' is not valid (allowed: " + _enum(CHECKS) + ")")
    value = _whole(number)
    if number != "-" and value is None:
        return None, None, _problem(lineno, "checkK '" + number + "' is not a whole number (allowed: 0, 1, 2 ... or -)")
    return (None if name == "-" else name), value, None


def _whole(text):
    """A plan number: a whole number, or None when the text is not one. A dash gives None without an error."""
    if text == "-":
        return None
    if _INT_RE.match(text):
        return int(text)
    return None


def parse_set_line(line, lineno=1):
    """Parse one bulk-update line such as: P2.4 status=done tokensK=35 note="wired; tests green".
    Returns (record, problem). The record is {"kind": "set", "line", "id", "fields"}; a "-" value is left out of
    fields (keep current). note="" is kept as "" and means clear the note."""
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        return None, _problem(lineno, "cannot read this line (" + str(exc) + ") (allowed: " + SET_ALLOWED + ")")
    if not tokens:
        return None, _problem(lineno, "empty line (allowed: " + SET_ALLOWED + ")")
    tid = tokens[0]
    if not ANY_ID_RE.match(tid):
        return None, _problem(lineno, "'" + tid + "' is not a task id (allowed: " + SET_ALLOWED + ")")
    if len(tokens) == 1:
        return None, _problem(lineno, "no fields to change (allowed: " + SET_ALLOWED + ")")
    fields = {}
    for pair in tokens[1:]:
        key, eq, value = pair.partition("=")
        if not eq or not key:
            return None, _problem(lineno, "'" + pair + "' is not key=value (allowed: " + SET_ALLOWED + ")")
        if key not in SET_KEYS:
            return None, _problem(lineno, "unknown key '" + key + "' (allowed: " + ", ".join(SET_KEYS) + ")")
        if key in fields:
            return None, _problem(lineno, "key '" + key + "' is given twice (allowed: each key once)")
        value, problem = _set_value(key, value, lineno)
        if problem is not None:
            return None, problem
        if value is not _KEEP:
            fields[key] = value
    return {"kind": "set", "line": lineno, "id": tid, "fields": fields}, None


def _set_value(key, value, lineno):
    if key == "note":
        return value, None
    if key == "title":
        if not value.strip():
            return None, _problem(lineno, "title is empty (allowed: any text)")
        return value.strip(), None
    if key == "needsUser":
        if value not in ("true", "false"):
            return None, _problem(lineno, "needsUser '" + value + "' is not valid (allowed: true|false)")
        return value == "true", None
    if key in ("tokensK", "checkK"):
        if value == "-":
            return _KEEP, None
        number = _whole(value)
        if number is None:
            return None, _problem(lineno, key + " '" + value + "' is not a whole number (allowed: 0, 1, 2 ... or -)")
        return number, None
    allowed = {"status": TASK_STATUSES, "model": MODELS, "thinking": THINKING, "check": CHECKS}[key]
    if value == "-":
        return _KEEP, None
    if value not in allowed:
        return None, _problem(lineno, key + " '" + value + "' is not valid (allowed: " + _enum(allowed) + ")")
    return value, None


def parse_set_text(text):
    """Parse bulk-update text (one line per task) into (records, errors). Blank lines and # comments are skipped."""
    records = []
    errors = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rec, problem = parse_set_line(line, lineno)
        if problem is not None:
            errors.append(problem)
        else:
            records.append(rec)
    return records, errors


def format_phase(phase):
    """One plan line for a phase dict: P <id> <status> | <name>."""
    status = phase.get("status") if phase.get("status") in PHASE_STATUSES else "todo"
    return "P " + str(phase.get("id", "")) + " " + status + " | " + _one_line(phase.get("name", ""))


def format_task(task):
    """One plan line for a task dict. Missing fields print as '-'. Parses back with parse_plan."""
    status = task.get("status") if task.get("status") in TASK_STATUSES else "-"
    tokens = _format_number(task.get("tokensK"))
    model = task.get("model") if task.get("model") in MODELS else "-"
    thinking = task.get("thinking") if task.get("thinking") in THINKING else "-"
    parts = ["T", str(task.get("id", "")), status, tokens, model + "/" + thinking]
    if task.get("needsUser") is True:
        parts.append("!")
    check = task.get("check") if task.get("check") in CHECKS else "none"
    check_k = _format_number(task.get("checkK"))
    if check != "none" or check_k not in ("0", "-"):
        parts.append("c:" + check + "/" + check_k)
    line = " ".join(parts) + " | " + _one_line(task.get("title", ""))
    note = task.get("note")
    if isinstance(note, str) and note.strip():
        line += " # " + _one_line(note)
    return line


def _format_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return str(int(round(value)))


def _one_line(text):
    return " ".join(str(text).split())


def today():
    """Today's date as YYYY-MM-DD, the value of updated on every write."""
    return datetime.date.today().isoformat()
