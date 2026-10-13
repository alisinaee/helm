"""Top-level command doctor: runs the install checks and prints ok, warn or fail with a plain-words fix for each
problem (WP11). Exit 0 when nothing failed (warnings do not count), 10 when a check failed.

With --json the handler prints the envelope itself, so the checks are listed in data, then exits 10 if needed.
cli.main would return 0 for a handler that returns data, so the exit code is set here.
"""

import json
import sys

from roadmap.errors import EXIT_DOCTOR
from roadmap.services import doctor

STATUS_MARK = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}


def register(sub, common):
    """Add the doctor command to the root subparsers."""
    parser = sub.add_parser("doctor", parents=[common], help="check the install and print a fix for each problem")
    parser.set_defaults(handler=_run)


def _print_plain(report):
    for row in report["checks"]:
        print("[%s] %s: %s" % (STATUS_MARK[row["status"]], row["title"], row["detail"]))
        if row["fix"]:
            print("       fix: " + row["fix"])
    summary = report["summary"]
    print("%d ok, %d warn, %d fail" % (summary["ok"], summary["warn"], summary["fail"]))


def _run(args):
    report = doctor.run()
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "data": report}))
        args.json = False  # the envelope is printed above; cli.main must not print a second one
    else:
        _print_plain(report)
    if report["exitCode"] != 0:
        sys.stdout.flush()
        raise SystemExit(EXIT_DOCTOR)
    return None
