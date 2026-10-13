"""Run the roadmap commands that the docs show, so a documented command that is unknown or broken fails the build.

Scans fenced ```bash and ```sh blocks in README.md, CONTRIBUTING.md and docs/*.md for lines that start with
"roadmap ". The lines run in the order the files are listed, against one temporary sandbox:
  - ROADMAP_HOME and HOME point into the sandbox, so config, state and logs never touch the real machine;
  - the working directory is a fixture project (my-app) with a small tasks.json that has task P1.1;
  - the text <project-path> in a command is replaced with the fixture folder.

Most commands run with --json, and the reply must be a JSON envelope with "ok": true. Commands that would touch
launchd, the keychain, the network, a live port or stdin run with --help only: doctor, hook, open, phone, serve,
service, usage sync, usage push, hooks install and hooks uninstall.

A command fails when it exits 2 (unknown command or bad arguments), prints a traceback, returns an "internal" or
"not_implemented" error, returns "ok": false, or (for --help) does not print a usage line.

Usage: python3 tools/check_docs.py    (exit 0 when every command passes; prints each command it ran)
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import namedtuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(REPO, "bin", "roadmap")
DOC_FILES = ("README.md", "CONTRIBUTING.md", "docs/ARCHITECTURE.md", "docs/API.md", "docs/SECURITY.md")
PROJECT_PLACEHOLDER = "<project-path>"
HELP_ONLY = (
    ("doctor",), ("hook",), ("open",), ("phone",), ("serve",), ("service",),
    ("usage", "sync"), ("usage", "push"), ("hooks", "install"), ("hooks", "uninstall"),
)
FAILING_CODES = ("internal", "not_implemented")
SHELL_LANGS = ("bash", "sh")
FENCE_RE = re.compile(r"^\s*```(\S*)\s*$")
FIXTURE_TASKS = {
    "schemaVersion": 1,
    "updated": "2026-10-13",
    "phases": [{"id": "P1", "name": "Engine", "status": "todo"}],
    "tasks": [{
        "id": "P1.1", "phase": "P1", "title": "Example task", "status": "todo", "tokensK": 20,
        "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0, "note": "",
    }],
}

Command = namedtuple("Command", "source line argv text")
Result = namedtuple("Result", "command mode exit problem")


def extract(path, source=None):
    """The roadmap commands in the shell fences of one Markdown file, as Command rows in file order."""
    found = []
    in_shell = False
    with open(path, "r", encoding="utf-8") as fh:
        for number, raw in enumerate(fh, start=1):
            fence = FENCE_RE.match(raw)
            if fence:
                in_shell = (not in_shell) and fence.group(1) in SHELL_LANGS
                continue
            if not in_shell:
                continue
            text = raw.strip()
            if not text.startswith("roadmap "):
                continue
            argv = shlex.split(text, comments=True)[1:]
            found.append(Command(source or path, number, argv, text))
    return found


def is_help_only(argv):
    words = [word for word in argv if not word.startswith("-")]
    return any(tuple(words[:len(prefix)]) == prefix for prefix in HELP_ONLY)


def build_fixture(root):
    """A project folder with a docs/ folder that has only tasks.json. The other data files come from project init."""
    project = os.path.join(root, "my-app")
    docs = os.path.join(project, "docs")
    os.makedirs(docs)
    with open(os.path.join(docs, "tasks.json"), "w", encoding="utf-8") as fh:
        json.dump(FIXTURE_TASKS, fh, indent=2)
    return project


def sandbox_env(root):
    """The environment for every command: all roadmap paths and HOME inside the sandbox."""
    env = dict(os.environ)
    env.pop("ROADMAP_PROJECT", None)
    home = os.path.join(root, "home")
    env["ROADMAP_HOME"] = home
    env["HOME"] = home
    env["ROADMAP_LAUNCH_AGENTS"] = os.path.join(root, "agents")
    os.makedirs(home, exist_ok=True)
    return env


def run_one(command, project, env):
    """Run one documented command and judge it. Returns a Result."""
    argv = [project if word == PROJECT_PLACEHOLDER else word for word in command.argv]
    if not argv:
        return Result(command, "json", None, "no command after roadmap")
    if is_help_only(argv):
        mode = "help"
        full = argv + ["--help"]
    else:
        mode = "json"
        full = argv if "--json" in argv else argv + ["--json"]
    proc = subprocess.run([SHIM] + full, cwd=project, env=env, capture_output=True, text=True, timeout=120)
    problem = None
    if "Traceback (most recent call last)" in proc.stderr:
        problem = "crashed (traceback on stderr)"
    elif proc.returncode == 2:
        problem = "unknown command or bad arguments: " + _usage_detail(proc)
    elif mode == "help":
        if "usage:" not in proc.stdout or proc.returncode != 0:
            problem = "--help did not print a usage line"
    else:
        problem = envelope_problem(proc.stdout)
    return Result(command, mode, proc.returncode, problem)


def _usage_detail(proc):
    """The plain reason a command rejected its arguments: the JSON error message, else the last stderr line."""
    try:
        error = json.loads(proc.stdout).get("error") or {}
        if error.get("message"):
            return str(error["message"])
    except (ValueError, AttributeError):
        pass
    return (proc.stderr.strip().splitlines() or ["no message"])[-1]


def envelope_problem(stdout):
    """None when stdout is a successful JSON envelope, else the reason it is not."""
    try:
        reply = json.loads(stdout)
    except ValueError:
        return "output is not a JSON envelope"
    if not isinstance(reply, dict):
        return "output is not a JSON object"
    if reply.get("ok") is True:
        return None
    error = reply.get("error") if isinstance(reply.get("error"), dict) else {}
    code = error.get("code", "?")
    if code in FAILING_CODES:
        return "returned error code '%s'" % code
    return "returned error '%s': %s" % (code, error.get("message", ""))


def check(files=DOC_FILES, root_dir=REPO):
    """Run every command in files (paths relative to root_dir, or absolute). Returns the list of Results."""
    commands = []
    for rel in files:
        path = os.path.join(root_dir, rel)
        if os.path.isfile(path):
            commands.extend(extract(path, rel))
    results = []
    with tempfile.TemporaryDirectory(prefix="roadmap-docs-") as root:
        project = build_fixture(root)
        env = sandbox_env(root)
        for command in commands:
            results.append(run_one(command, project, env))
    return results


def report(results):
    """Print one line per command and a summary. Returns the exit code."""
    failed = 0
    for result in results:
        command = result.command
        where = "%s:%d" % (command.source, command.line)
        if result.problem is None:
            print("  ok    %-24s %s  (exit %s, %s)" % (where, command.text, result.exit, result.mode))
        else:
            failed += 1
            print("  FAIL  %-24s %s  (exit %s): %s" % (where, command.text, result.exit, result.problem))
    print("checked %d documented roadmap command(s): %d failed" % (len(results), failed))
    return 1 if failed else 0


def main():
    """Check the shipped docs and return the exit code."""
    results = check()
    if not results:
        print("no roadmap commands found in the docs")
        return 1
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
