"""Run every check: Python lint, JavaScript lint, then the unit tests. Exits non-zero on any failure."""

import os
import subprocess
import sys

import lint_js
import lint_py

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    """Run the checks in order and return the exit code."""
    failed = False
    for name, module in (("lint_py", lint_py), ("lint_js", lint_js)):
        issues = module.run(REPO)
        for issue in issues:
            print(issue)
        print(name + ": " + ("ok" if not issues else str(len(issues)) + " issue(s)"))
        failed = failed or bool(issues)
    sys.stdout.flush()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=REPO,
        check=False,
    )
    print("unittest: " + ("ok" if proc.returncode == 0 else "failed"))
    failed = failed or proc.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
