#!/usr/bin/env python3
"""Generate docs/facts/FACTS.md: the one grounding file a weak LLM worker reads before it works on roadmap-board.

Sections: the --help text of every top-level command (run with a temporary ROADMAP_HOME), the HTTP route table,
the /cmd ops, the size and cap constants, the module tree with one-line docstrings, the data-file tables from
docs/ARCHITECTURE.md, the last 30 commit subjects, and the UI rules from docs/UI-CHECKLIST.md. The output is sorted
and deterministic, apart from the date on the header line. Stdlib only, no network, no writes outside --out.

Usage: python3 tools/gen_facts.py [--out PATH]
"""

import argparse
import ast
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO, "docs", "facts", "FACTS.md")
MAX_BYTES = 60 * 1024
HELP_CAP = 1500          # characters of --help text kept per command
HELP_TIMEOUT = 60        # seconds per help call
CONST_RE = re.compile(r"(_MAX|_CAP|_LIMIT|_KEEP)$|^(KEEP|CAP|LIMIT)$|^KEEP_|^LIMIT_")
DOC_CLIP = 96
GIT_LOG_COUNT = 30


def _read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def _clip(text, limit=DOC_CLIP):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _py_files(sub):
    found = []
    for root, dirs, files in os.walk(os.path.join(REPO, sub)):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in files:
            if name.endswith(".py"):
                found.append(os.path.relpath(os.path.join(root, name), REPO))
    return sorted(found)


def _help_env(home):
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    env["ROADMAP_HOME"] = home
    return env


def _run_help(home, args):
    """Run bin/roadmap with the given args plus --help. Returns (exit code, text)."""
    proc = subprocess.run(
        [os.path.join(REPO, "bin", "roadmap"), *args, "--help"],
        cwd=REPO, env=_help_env(home), capture_output=True, text=True, timeout=HELP_TIMEOUT,
    )
    return proc.returncode, (proc.stdout or proc.stderr).rstrip()


def top_level_commands(home):
    """The command names listed under 'positional arguments' in `roadmap --help`."""
    _, text = _run_help(home, [])
    names, in_section = [], False
    for line in text.splitlines():
        if line.startswith("positional arguments:"):
            in_section = True
            continue
        if in_section and line.startswith("options:"):
            break
        match = re.match(r"^    (\S+)\s{2,}\S", line)
        if in_section and match:
            names.append(match.group(1))
    return names


def help_section(home, names):
    lines = ["## 1. Command help (`bin/roadmap <command> --help`)", ""]
    for name in names:
        code, text = _run_help(home, [name])
        if len(text) > HELP_CAP:
            text = text[:HELP_CAP].rstrip() + "\n... (truncated)"
        lines.append(f"### roadmap {name}")
        lines.append("")
        lines.append("```text")
        lines.append(text)
        lines.append("```")
        if code != 0:
            lines.append(f"(help exited with status {code})")
        lines.append("")
    return lines


def _route_purposes(tree):
    docs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            docs[node.name] = _clip(doc.splitlines()[0]) if doc else "-"
    return docs


def routes_section():
    src = _read("roadmap/http/routes.py")
    tree = ast.parse(src)
    purposes = _route_purposes(tree)
    rows = []
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ROUTES" for t in node.targets)):
            continue
        for entry in node.value.elts:
            pattern, methods, handler = entry.elts
            arg = pattern.args[0] if isinstance(pattern, ast.Call) and pattern.args else pattern
            path = arg.value if isinstance(arg, ast.Constant) else ast.unparse(arg)
            meths = ", ".join(ast.literal_eval(methods))
            hname = handler.id if isinstance(handler, ast.Name) else ast.unparse(handler)
            rows.append((meths, path, purposes.get(hname, "-")))
    lines = ["## 2. HTTP routes (roadmap/http/routes.py)", "",
             "| method | path (regex) | purpose |", "|---|---|---|"]
    lines += [f"| {m} | `{p}` | {d} |" for m, p, d in rows]
    lines.append("")
    return lines


def cmd_ops_section():
    tree = ast.parse(_read("roadmap/services/cmdops.py"))
    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_register"
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            names.add(node.args[0].value)
    lines = ["## 3. /cmd ops (roadmap/services/cmdops.py)", ""]
    lines += [f"- `{name}`" for name in sorted(names)]
    lines.append("")
    return lines


def constants_section():
    rows = []
    for rel in _py_files("roadmap"):
        tree = ast.parse(_read(rel))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and CONST_RE.search(target.id):
                rows.append((target.id, f"{rel}:{node.lineno}", ast.unparse(node.value)))
    rows.sort()
    lines = ["## 4. Size and cap constants (module level, roadmap/**/*.py)", "",
             "| name | file:line | value |", "|---|---|---|"]
    lines += [f"| `{n}` | `{loc}` | `{v}` |" for n, loc, v in rows]
    lines.append("")
    return lines


def _js_doc(text):
    block = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            block.append(stripped[2:].strip())
        elif not stripped:
            if block:
                break
        else:
            break
    joined = " ".join(block)
    cut = joined.find(". ")
    return _clip(joined[: cut + 1] if cut != -1 else joined) if joined else "-"


def _py_doc(text):
    doc = ast.get_docstring(ast.parse(text))
    return _clip(doc.splitlines()[0]) if doc else "-"


def tree_section():
    lines = ["## 5. Module tree (first docstring line of each file)", ""]
    groups = [("roadmap", _py_files("roadmap"), _py_doc)]
    js = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "web", "js", "views")):
        for name in files:
            if name.endswith(".js"):
                js.append(os.path.relpath(os.path.join(root, name), REPO))
    groups.append(("web/js/views", sorted(js), _js_doc))
    for label, files, doc_of in groups:
        lines.append(f"### {label}/")
        lines.append("")
        for rel in files:
            lines.append(f"- `{rel}`: {doc_of(_read(rel))}")
        lines.append("")
    return lines


def data_section():
    text = _read("docs/ARCHITECTURE.md")
    wanted = ("## Where things are on disk", "## Data files added for the interactive manager")
    lines = ["## 6. Data files and locations (from docs/ARCHITECTURE.md)", ""]
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line if line.startswith(wanted) else None
            if current:
                lines.append(f"### {line[3:]}")
                lines.append("")
            continue
        if current and line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            lines.append(line)
    lines.append("")
    return lines


def commits_section():
    try:
        proc = subprocess.run(
            ["git", "-C", REPO, "log", f"-{GIT_LOG_COUNT}", "--format=%s"],
            capture_output=True, text=True, timeout=60,
        )
        subjects = proc.stdout.splitlines() if proc.returncode == 0 else ["(git log failed)"]
    except (OSError, subprocess.SubprocessError):
        subjects = ["(git unavailable)"]
    lines = [f"## 7. Last {GIT_LOG_COUNT} commit subjects (newest first)", ""]
    lines += [f"- {s}" for s in subjects]
    lines.append("")
    return lines


def ui_rules_section():
    lines = ["## 8. UI rules (docs/UI-CHECKLIST.md, numbered rules)", ""]
    for line in _read("docs/UI-CHECKLIST.md").splitlines():
        match = re.match(r"^(\d+)\. (.*)$", line)
        if match:
            head = match.group(2).split(":", 1)[0]
            lines.append(f"- {match.group(1)}. {_clip(head, 100)}")
    lines.append("")
    return lines


def build(home, today):
    names = top_level_commands(home)
    if not names:
        raise SystemExit("gen_facts: could not read the top-level commands from bin/roadmap --help")
    body = []
    body += help_section(home, names)
    body += routes_section()
    body += cmd_ops_section()
    body += constants_section()
    body += tree_section()
    body += data_section()
    body += commits_section()
    body += ui_rules_section()
    header = [
        "# FACTS: roadmap-board grounding file",
        "",
        f"Generated {today} by tools/gen_facts.py. Do not edit by hand; run `python3 tools/gen_facts.py`.",
        "Every fact here is read from the code or the docs at generation time. Where this file and another doc"
        " disagree, the code wins.",
        "",
    ]
    return "\n".join(header + body).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=DEFAULT_OUT, help="output path (default: docs/facts/FACTS.md)")
    args = parser.parse_args(argv)
    home = tempfile.mkdtemp(prefix="rb-facts-")
    try:
        text = build(os.path.join(home, "home"), datetime.date.today().isoformat())
    finally:
        shutil.rmtree(home, ignore_errors=True)
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        sys.stderr.write(f"gen_facts: output is {size} bytes, over the {MAX_BYTES} byte cap\n")
        return 1
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {args.out} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
