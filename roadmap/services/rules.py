"""Project rules (WP22): docs/rules.txt, one rule per line, shown to the lead and to workers, and synced to CLAUDE.md.

A rule line is `R3 haiku budget 60 | text`: id, scope, kind, the number (budget only), a bar and the text.
Scopes: all, lead, worker, haiku, sonnet, opus, phase:X, task:X, claude. Kinds: do, dont, budget N, done.
Caps: 60 rules, 160 characters of text each, 8 KB for the file. Lines starting with # are comments and are kept.

Sync writes the rules of the scopes all, lead and claude into CLAUDE.md, and only between the markers
<!-- roadmap:rules --> and <!-- /roadmap:rules -->. It makes a backup first, and it refuses broken markers.
"""

import os
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import activity, agentguard, jobs, records, tasks
from roadmap.store import atomic, backup, lock

FILE = "rules.txt"
MAX_RULES = 60
MAX_TEXT = 160
MAX_BYTES = 8192
SHOW_LINES = 12
BUDGET_MAX = 100000  # thousands of tokens
FIXED_SCOPES = ("all", "lead", "worker", "haiku", "sonnet", "opus", "claude")
SYNC_SCOPES = ("all", "lead", "claude")
ROLES = ("lead", "worker")
KINDS = ("do", "dont", "budget", "done")
BEGIN = "<!-- roadmap:rules -->"
END = "<!-- /roadmap:rules -->"
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "rules.txt")
_SCOPE_RE = re.compile(r"^(phase|task):([A-Za-z0-9][A-Za-z0-9./-]{0,39})$")
_LINE_RE = re.compile(r"^(R\d+)\s+(\S+)\s+(\S+)(?:\s+(\d+))?\s*\|\s?(.*?)\s*$")


# ------------------------------------------------------------------ format, parse, validate

def format_rule(rule):
    head = rule["id"] + " " + rule["scope"] + " " + rule["kind"]
    if rule["kind"] == "budget":
        head += " " + str(rule["value"])
    return head + " | " + rule["text"]


def _scope_ok(scope):
    return scope in FIXED_SCOPES or _SCOPE_RE.match(scope) is not None


def _check_fields(scope, kind, text, value):
    """Return the clean (scope, kind, text, value) or raise usage. Text is one line of at most MAX_TEXT characters."""
    if not _scope_ok(scope):
        raise RoadmapError("usage", "scope '" + scope + "' is not valid (all, lead, worker, haiku, sonnet, opus, "
                           "phase:X, task:X, claude)", EXIT_USAGE)
    if kind not in KINDS:
        raise RoadmapError("usage", "kind '" + kind + "' is not valid (do, dont, budget N, done)", EXIT_USAGE)
    if kind == "budget":
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= BUDGET_MAX:
            raise RoadmapError("usage", "a budget rule needs a number of thousands of tokens, 1 to %d" % BUDGET_MAX,
                               EXIT_USAGE)
    elif value is not None:
        raise RoadmapError("usage", "only a budget rule takes a number", EXIT_USAGE)
    clean = records.text_field(text, "rule text", MAX_TEXT)
    return scope, kind, clean, value


def parse(text):
    """Return (rules, problems) for the text of rules.txt. Comments and blank lines are skipped."""
    rules = []
    problems = []
    for number, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            problems.append("line %d is not a rule (R3 scope kind | text)" % number)
            continue
        rule_id, scope, kind, number_text, body = match.groups()
        value = int(number_text) if number_text is not None else None
        try:
            scope, kind, body, value = _check_fields(scope, kind, body, value)
        except RoadmapError as exc:
            problems.append("line %d: %s" % (number, exc.message))
            continue
        rules.append({"id": rule_id, "scope": scope, "kind": kind, "value": value, "text": body})
    ids = [r["id"] for r in rules]
    for rule_id in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(rule_id + " is listed more than once")
    if len(rules) > MAX_RULES:
        problems.append("%d rules; the most allowed is %d" % (len(rules), MAX_RULES))
    if len((text or "").encode("utf-8")) > MAX_BYTES:
        problems.append("the file is larger than %d bytes" % MAX_BYTES)
    return rules, problems


def _header(text):
    """The comment lines at the top of the file (kept on every write), or the template's when there are none."""
    lines = []
    for raw in (text or "").splitlines():
        if raw.strip().startswith("#"):
            lines.append(raw.rstrip())
        elif raw.strip():
            break
    if lines:
        return lines
    try:
        with open(TEMPLATE, "r", encoding="utf-8") as fh:
            return [line.rstrip() for line in fh.read().splitlines() if line.strip().startswith("#")]
    except OSError:
        return []


def _render(header, rules):
    return "\n".join(header + [format_rule(r) for r in rules]) + "\n"


def _path(data_dir):
    records.require_dir(data_dir)
    return records.file_of(data_dir, FILE)


def read(data_dir):
    """(text, rules, problems) of docs/rules.txt. A missing file is empty."""
    path = _path(data_dir)
    if not os.path.exists(path):
        return "", [], []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise RoadmapError("invalid_data", "rules.txt cannot be read: " + str(exc), EXIT_INVALID_DATA)
    rules, problems = parse(text)
    return text, rules, problems


def _need_clean(data_dir):
    text, rules, problems = read(data_dir)
    if problems:
        raise RoadmapError("invalid_data", "rules.txt has problems; fix them first:\n" + "\n".join(problems[:5]),
                           EXIT_INVALID_DATA, next="roadmap rules check")
    return text, rules


def _next_id(rules):
    best = 0
    for rule in rules:
        best = max(best, int(rule["id"][1:]))
    return "R%d" % (best + 1)


# ------------------------------------------------------------------ show

def applies(rule, task_id, phase, model, role):
    """True when a rule applies to a task, a model and a role. claude rules are for CLAUDE.md only."""
    scope = rule["scope"]
    if scope == "all":
        return True
    if scope == "claude":
        return False
    if scope == "lead":
        return role in (None, "lead")
    if scope == "worker":
        return role in (None, "worker")
    if scope in ("haiku", "sonnet", "opus"):
        return model == scope
    match = _SCOPE_RE.match(scope)
    if match is None:
        return False
    if match.group(1) == "phase":
        return phase is not None and phase == match.group(2)
    return task_id is not None and task_id == match.group(2)


def _phase_of(data_dir, task_id):
    if not task_id:
        return None
    try:
        task = tasks.get(data_dir, task_id)
    except RoadmapError:
        return None
    return task.get("phase") if isinstance(task, dict) else None


def show(data_dir, task_id=None, model=None, role=None):
    """The rules for a task, a model and a role, one line each, at most SHOW_LINES lines."""
    if role is not None and role not in ROLES:
        raise RoadmapError("usage", "role must be lead or worker", EXIT_USAGE)
    _, rules, _ = read(data_dir)
    phase = _phase_of(data_dir, task_id)
    picked = [format_rule(r) for r in rules if applies(r, task_id, phase, model, role)]
    if len(picked) > SHOW_LINES:
        picked = picked[:SHOW_LINES - 1] + ["+%d more in docs/rules.txt" % (len(picked) - SHOW_LINES + 1)]
    return picked


# ------------------------------------------------------------------ add, rm, check

def add(data_dir, scope, kind, text, value=None, source=None):
    """Add a rule at the end of the file. Returns the rule."""
    agentguard.refuse_if_agent("rules.add", source)
    scope, kind, clean, value = _check_fields(str(scope), str(kind), text, value)
    with lock.locked(data_dir):
        current, rules = _need_clean(data_dir)
        if len(rules) >= MAX_RULES:
            raise RoadmapError("conflict", "rules.txt holds " + str(MAX_RULES) + " rules, the most allowed; remove one "
                               "first", EXIT_CONFLICT, next="roadmap rules rm <ID>")
        rule = {"id": _next_id(rules), "scope": scope, "kind": kind, "value": value, "text": clean}
        body = _render(_header(current), rules + [rule])
        if len(body.encode("utf-8")) > MAX_BYTES:
            raise RoadmapError("conflict", "rules.txt would pass 8 KB; remove or shorten a rule first", EXIT_CONFLICT)
        atomic.write_text(_path(data_dir), body)
    summary = rule["id"] + " " + scope + " " + kind
    activity.append(data_dir, source or agentguard.source_name(), "rules.add", summary, undo=True)
    return dict(rule)


def remove(data_dir, rule_id, source=None):
    """Remove a rule by id. Returns the removed rule."""
    agentguard.refuse_if_agent("rules.rm", source)
    wanted = str(rule_id or "").strip().upper()
    with lock.locked(data_dir):
        current, rules = _need_clean(data_dir)
        gone = next((r for r in rules if r["id"] == wanted), None)
        if gone is None:
            raise RoadmapError("not_found", "no rule " + wanted + " in docs/rules.txt", EXIT_NOT_FOUND,
                               next="roadmap rules show")
        kept = [r for r in rules if r is not gone]
        atomic.write_text(_path(data_dir), _render(_header(current), kept))
    activity.append(data_dir, source or agentguard.source_name(), "rules.rm", wanted, undo=True)
    return dict(gone)


def check(data_dir):
    """Validate docs/rules.txt. Returns the rule count; raises invalid_data listing the problems."""
    _, rules, problems = read(data_dir)
    if problems:
        raise RoadmapError("invalid_data", "rules.txt has problems:\n" + "\n".join(problems[:10]), EXIT_INVALID_DATA,
                           next="fix docs/rules.txt, then roadmap rules check")
    return len(rules)


# ------------------------------------------------------------------ sync to CLAUDE.md

def _block(rules):
    chosen = [r for r in rules if r["scope"] in SYNC_SCOPES]
    lines = [BEGIN, "Roadmap rules (generated from docs/rules.txt by roadmap rules sync; edit the rules there):"]
    lines += ["- " + format_rule(r) for r in chosen]
    lines.append(END)
    return lines


def _rule_lines(lines):
    """{rule id: line} for the rule lines of a block."""
    found = {}
    for line in lines:
        if line.startswith("- R"):
            match = _LINE_RE.match(line[2:])
            if match is not None:
                found[match.group(1)] = line
    return found


def _splice(existing, block):
    """(new text, old block lines or None) for CLAUDE.md. Refuses a broken marker pair."""
    if existing is None or existing == "":
        return "\n".join(block) + "\n", None
    lines = existing.split("\n")
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if not begins and not ends:
        return existing.rstrip("\n") + "\n\n" + "\n".join(block) + "\n", None
    if len(begins) != 1 or len(ends) != 1 or begins[0] > ends[0]:
        raise RoadmapError("invalid_data", "CLAUDE.md has broken roadmap:rules markers (need one start and one end "
                           "marker, in that order); fix them by hand, nothing changed", EXIT_INVALID_DATA)
    start, stop = begins[0], ends[0]
    old = lines[start:stop + 1]
    return "\n".join(lines[:start] + block + lines[stop + 1:]), old


def sync(project, data_dir, dry_run=False, source=None, now=None):
    """Write the rules of scopes all, lead and claude into the project's CLAUDE.md between the markers.

    Returns the counts (+added, ~changed, -removed). Running it again changes nothing and prints +0 ~0 -0.
    """
    if not dry_run:
        agentguard.refuse_if_agent("rules.sync", source)
    _, rules = _need_clean(data_dir)
    block = _block(rules)
    target = os.path.join(project["path"], "CLAUDE.md")
    if os.path.islink(target):
        raise RoadmapError("invalid_data", "refusing to sync into a symlinked CLAUDE.md, left unchanged",
                           EXIT_INVALID_DATA)
    existing = None
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8") as fh:
            existing = fh.read()
    new_text, old_block = _splice(existing, block)
    old_rules = _rule_lines(old_block or [])
    new_rules = _rule_lines(block)
    added = len(set(new_rules) - set(old_rules))
    removed = len(set(old_rules) - set(new_rules))
    changed = sum(1 for k in set(new_rules) & set(old_rules) if new_rules[k] != old_rules[k])
    counts = {"added": added, "changed": changed, "removed": removed}
    result = dict(counts, path=target, dryRun=bool(dry_run), written=False, backup=None)
    if dry_run or new_text == existing:
        return result
    result["backup"] = backup.backup_files(project["id"], [target], now=now) if existing is not None else None
    atomic.write_text(target, new_text)
    result["written"] = True
    summary = "rules sync +%d ~%d -%d" % (added, changed, removed)
    activity.append(data_dir, source or agentguard.source_name(), "rules.sync", summary, undo=False, now=now)
    return result
