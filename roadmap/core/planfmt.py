"""Plan text format for roadmap tasks and phases, and the bulk "set" line format. Pure functions, no I/O.

Grammar and examples: docs/AGENT-INTERFACE.md section 2. Every problem is reported as
"line N: <problem> (allowed: ...)" so an agent can fix the line and retry.
"""

import datetime
import re
import shlex

PHASE_STATUSES = ("todo", "partial", "done", "hold")
TASK_STATUSES = PHASE_STATUSES + ("backlog",)   # a phase is never backlog (PHASE_STATUSES has no backlog)
MODELS = ("haiku", "sonnet", "opus", "cursor", "agy", "head")
THINKING = ("low", "medium", "high")
CHECKS = ("none", "sonnet", "opus")
SET_KEYS = ("status", "tokensK", "model", "thinking", "needsUser", "check", "checkK", "note", "title", "after")
AFTER_MAX = 5                          # most task ids in a task's after list
FEAT_MAX_PER_TASK = 3                  # most feature ids in a task's feats list
FEATURES_MAX = 60                      # most features in docs/features.json
FEAT_TITLE_MAX = 80
FEAT_ACC_MAX = 160
FEAT_LEVELS = 3                        # levels of the plan tree: phase > sub plan > item (parent chain <= 2)
PRIOS = ("1", "2", "3")
PLAN_ALLOWED = ("P <id> <status> | <name>  or  T <id> <status> <tokensK> <model>/<thinking> "
                "[!] [c:<check>/<checkK>] [a:<ids>] [f:<feats>] | <title> [# <note>]  or  "
                "F <id> <-|hold> <1|2|3> <phase|-> <parent|-> [ask] | <title> [# <acceptance>]  or  "
                "L <featureId> <taskId> [<taskId>...]")
SET_ALLOWED = "<id> key=value ...; keys: " + ", ".join(SET_KEYS)
_KEEP = object()  # marks a set value of "-": keep the current value

PHASE_ID_RE = re.compile(r"^[A-Za-z0-9]+$")
FEAT_ID_RE = re.compile(r"^F[1-9][0-9]?$")
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
        elif head == "F":
            rec, problem = _parse_feature(line, lineno)
        elif head == "L":
            rec, problem = _parse_link(line, lineno)
        else:
            rec, problem = None, _problem(lineno, "unknown record '" + head + "' (allowed: P, T, #, blank) "
                                          "(also: F, L)")
        if problem is not None:
            errors.append(problem)
            continue
        if rec["kind"] == "link":
            records.append(rec)
            continue
        key = (rec["kind"], rec["id"])
        if key in seen:
            errors.append(_problem(lineno, "duplicate " + rec["kind"] + " id " + rec["id"]
                                   + " (first on line " + str(seen[key]) + ")"
                                   + " (allowed: each id once per input)"))
            continue
        seen[key] = lineno
        records.append(rec)
    errors.extend(_tree_errors(records))
    return records, errors


def _tree_errors(records):
    """Parent loops and levels deeper than FEAT_LEVELS among the F lines of one input, in line order. A parent
    defined later in the same input counts. A parent outside the input is checked by the service."""
    feats = {rec["id"]: rec for rec in records if rec["kind"] == "feature"}
    problems = []
    for rec in records:
        if rec["kind"] != "feature":
            continue
        level, loop_at = _level(rec, feats)
        if loop_at is not None:
            problems.append(_problem(rec["line"], rec["id"] + " is its own ancestor (parent loop back to "
                                     + loop_at + ") (allowed: a parent chain that ends at a top-level feature or -)"
                                     + " next: set the parent of " + loop_at + " to -"))
        elif level > FEAT_LEVELS:
            problems.append(_problem(rec["line"], rec["id"] + " would be level " + str(level)
                                     + " (allowed: " + str(FEAT_LEVELS) + " levels: phase > sub plan > item)"
                                     + " next: move " + rec["id"] + " to a parent one level up, or set its parent"
                                     + " to -"))
    return problems


def _level(rec, feats):
    """(level, loop_at): level 1 is a top-level feature; loop_at is the id that closes a parent loop, else None."""
    level = 1
    seen = {rec["id"]}
    parent = rec.get("parent")
    while parent is not None and parent in feats:
        if parent in seen:
            return level, parent
        seen.add(parent)
        level += 1
        parent = feats[parent].get("parent")
    return level, None


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
    after = None
    idx = 5
    if idx < len(tokens) and tokens[idx] == "!":
        needs = True
        idx += 1
    if idx < len(tokens) and tokens[idx].startswith("c:"):
        check, check_k, problem = _parse_check(tokens[idx][2:], lineno)
        if problem is not None:
            return None, problem
        idx += 1
    if idx < len(tokens) and tokens[idx].startswith("a:"):
        after, problem = _parse_after_token(tokens[idx][2:], lineno)
        if problem is not None:
            return None, problem
        idx += 1
    feats = None
    if idx < len(tokens) and tokens[idx].startswith("f:"):
        feats, problem = _parse_feats(tokens[idx][2:], lineno)
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
           "check": check, "checkK": check_k, "note": note, "after": after, "feats": feats}
    return rec, None


def _parse_feats(text, lineno):
    """The f:<ids> token of a task line: feature ids such as F3,F7, or None for f:- (keep the current list)."""
    if text == "-":
        return None, None
    ids = [part.strip() for part in text.split(",")]
    for fid in ids:
        if not FEAT_ID_RE.match(fid):
            return None, _problem(lineno, "feature id '" + fid + "' must look like F3 (allowed: F1 to F99, comma "
                                  "separated)")
    if len(set(ids)) != len(ids):
        return None, _problem(lineno, "f: lists a feature id twice (allowed: each feature id once)")
    if len(ids) > FEAT_MAX_PER_TASK:
        return None, _problem(lineno, "f: has " + str(len(ids)) + " features (allowed: up to "
                              + str(FEAT_MAX_PER_TASK) + " per task)")
    return ids, None


def _parse_feature(line, lineno):
    """F <id> <-|hold> <prio> <phase|-> <parent|-> | <title> [# <acceptance>]. A feature line sets every field:
    '-' for status means not held, '-' for phase or parent means none, and no acceptance means empty."""
    shape = "feature line needs an id, status, prio, phase, parent and '| title' (allowed: " + PLAN_ALLOWED + ")"
    head, sep, rest = line.partition("|")
    tokens = head.split()
    if not sep or len(tokens) not in (6, 7):
        return None, _problem(lineno, shape)
    if len(tokens) == 7 and tokens[6] != "ask":
        return None, _problem(lineno, "'" + tokens[6] + "' is not valid after the parent (allowed: ask, or nothing)")
    _, fid, status, prio, phase, parent = tokens[:6]
    ask = len(tokens) == 7
    if not FEAT_ID_RE.match(fid):
        return None, _problem(lineno, "feature id '" + fid + "' must look like F3 (allowed: F1 to F99)")
    if status not in ("-", "hold"):
        return None, _problem(lineno, "status '" + status + "' is not valid (allowed: -|hold)")
    if prio not in PRIOS:
        return None, _problem(lineno, "prio '" + prio + "' is not valid (allowed: 1|2|3)")
    if phase != "-" and not PHASE_ID_RE.match(phase):
        return None, _problem(lineno, "phase '" + phase + "' has a dot or a symbol (allowed: phase id or -)")
    if parent != "-" and not FEAT_ID_RE.match(parent):
        return None, _problem(lineno, "parent '" + parent + "' must look like F3 (allowed: feature id or -)")
    if parent == fid:
        return None, _problem(lineno, fid + " cannot be its own parent (allowed: another feature id or -)")
    title, hashsep, acc = rest.partition(" # ")
    if not hashsep and rest.rstrip().endswith(" #"):
        return None, _problem(lineno, "acceptance is empty (allowed: '# ' followed by text, or no '#')")
    title = " ".join(title.split())
    if not title:
        return None, _problem(lineno, "feature title is empty (allowed: text after the '|')")
    if len(title) > FEAT_TITLE_MAX:
        return None, _problem(lineno, "feature title is " + str(len(title)) + " characters (allowed: up to "
                              + str(FEAT_TITLE_MAX) + ")")
    acc = " ".join(acc.split()) if hashsep else ""
    if len(acc) > FEAT_ACC_MAX:
        return None, _problem(lineno, "acceptance is " + str(len(acc)) + " characters (allowed: up to "
                              + str(FEAT_ACC_MAX) + ")")
    rec = {"kind": "feature", "line": lineno, "id": fid, "hold": status == "hold", "prio": int(prio),
           "phase": None if phase == "-" else phase, "parent": None if parent == "-" else parent,
           "title": title, "acc": acc}
    if ask:
        rec["ask"] = True
    return rec, None


def _parse_link(line, lineno):
    """L <featureId> <taskId> [<taskId>...]: adds the feature to each task's feats (idempotent)."""
    shape = "link line needs a feature id and at least one task id (allowed: L <featureId> <taskId> [<taskId>...])"
    tokens = line.split()
    if len(tokens) < 3:
        return None, _problem(lineno, shape)
    fid = tokens[1]
    if not FEAT_ID_RE.match(fid):
        return None, _problem(lineno, "feature id '" + fid + "' must look like F3 (allowed: F1 to F99)")
    for tid in tokens[2:]:
        if not TASK_ID_RE.match(tid):
            return None, _problem(lineno, "task id '" + tid + "' must look like P1.2 (allowed: <phase>.<number>)")
    return {"kind": "link", "line": lineno, "feature": fid, "tasks": tokens[2:]}, None


def _parse_after_token(text, lineno):
    """The a:<ids> token of a task line: a list of task ids, or None for a:- (keep the current list)."""
    if text == "-":
        return None, None
    ids, problem = parse_after(text)
    if problem is not None:
        return None, _problem(lineno, problem)
    return ids, None


def parse_after(text):
    """A task's after list from 'P2.2,P2.3': (ids, None), or (None, problem) when an id is not a task id or there
    are more than AFTER_MAX ids. Empty text gives [] (which clears the list in a set line)."""
    if not text.strip():
        return [], None
    ids = [part.strip() for part in text.split(",")]
    for tid in ids:
        if not TASK_ID_RE.match(tid):
            return None, ("after id '" + tid + "' must look like P2.2 (allowed: task ids, up to "
                          + str(AFTER_MAX) + ", comma separated)")
    if len(ids) > AFTER_MAX:
        return None, ("after has " + str(len(ids)) + " ids (allowed: up to " + str(AFTER_MAX) + ")")
    return ids, None


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
    if key == "after":
        if value == "-":
            return _KEEP, None
        ids, problem = parse_after(value)
        if problem is not None:
            return None, _problem(lineno, problem)
        return ids, None
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


def format_feature(feature):
    """One plan line for a feature dict. Parses back with parse_plan (round trip), keeping the stored fields."""
    prio = feature.get("prio") if feature.get("prio") in (1, 2, 3) else 2
    phase = feature.get("phase") if isinstance(feature.get("phase"), str) and feature.get("phase") else "-"
    parent = feature.get("parent") if isinstance(feature.get("parent"), str) and feature.get("parent") else "-"
    status = "hold" if feature.get("hold") is True else "-"
    parts = ["F", str(feature.get("id", "")), status, str(prio), phase, parent]
    if feature.get("ask") is True:
        parts.append("ask")
    line = " ".join(parts) + " | " + _one_line(feature.get("title", ""))
    acc = feature.get("acc")
    if isinstance(acc, str) and acc.strip():
        line += " # " + _one_line(acc)
    return line


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
    after = task.get("after")
    if isinstance(after, list) and after:
        parts.append("a:" + ",".join(str(tid) for tid in after))
    feats = task.get("feats")
    if isinstance(feats, list) and feats:
        parts.append("f:" + ",".join(str(fid) for fid in feats))
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
