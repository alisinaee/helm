"""Lint the browser sources under web/: no var, innerHTML only in web/js/dom.js, no console.log,
no eval or Function constructor, 120 columns, and node --check when node is installed.
With no JavaScript files the result is clean.
"""

import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_COLS = 120
DOM_FILE = "web/js/dom.js"
RULES = (
    (re.compile(r"\bvar\s"), "use const or let, not var"),
    (re.compile(r"\bconsole\.log\b"), "console.log is not allowed"),
    (re.compile(r"\beval\s*\("), "eval is not allowed"),
    (re.compile(r"\bnew\s+Function\b"), "the Function constructor is not allowed"),
    (re.compile(r"(?<![\w.])Function\s*\("), "the Function constructor is not allowed"),
)
INNER_HTML = re.compile(r"\binnerHTML\b")


def run(repo=REPO):
    """Return a list of issue strings; an empty list means clean."""
    issues = []
    files = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(repo, "web")):
        dirnames[:] = sorted(d for d in dirnames if d != "vendor")  # third-party minified libraries
        files.extend(os.path.join(dirpath, name) for name in sorted(filenames) if name.endswith(".js"))
    node = shutil.which("node")
    for path in files:
        rel = os.path.relpath(path, repo).replace(os.sep, "/")
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        for number, line in enumerate(lines, 1):
            if len(line) > MAX_COLS:
                issues.append(f"{rel}:{number}: longer than {MAX_COLS} columns")
            for pattern, message in RULES:
                if pattern.search(line):
                    issues.append(f"{rel}:{number}: {message}")
            if INNER_HTML.search(line) and rel != DOM_FILE:
                issues.append(f"{rel}:{number}: innerHTML is allowed only in {DOM_FILE}")
        if node:
            proc = subprocess.run(
                [node, "--experimental-default-type=module", "--check", path],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode != 0:
                issues.append(f"{rel}: node --check failed: {proc.stderr.strip()[-200:]}")
    return issues


def main():
    """Print the issues and return the exit code."""
    issues = run()
    for issue in issues:
        print(issue)
    print("lint_js: " + ("ok" if not issues else str(len(issues)) + " issue(s)"))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
