"""Tests for the CLI: the version command, the --json envelope, exit codes and the shim."""

import contextlib
import io
import json
import os
import subprocess
import unittest

from roadmap import __version__
from roadmap.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIM = os.path.join(REPO, "bin", "roadmap")


def run(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_version_json_envelope(self):
        code, out, _ = run(["version", "--json"])
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["data"]["version"], __version__)

    def test_json_flag_before_command(self):
        code, out, _ = run(["--json", "version"])
        self.assertEqual(code, 0)
        self.assertIs(json.loads(out)["ok"], True)

    def test_version_plain_text(self):
        code, out, _ = run(["version"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "Helm " + __version__ + "\n")

    def test_stub_handler_raises_not_implemented(self):
        from roadmap.errors import RoadmapError, stub
        with self.assertRaises(RoadmapError) as ctx:
            stub("demo")(None)
        self.assertEqual(ctx.exception.code, "not_implemented")
        self.assertEqual(ctx.exception.exit, 1)
        self.assertIn("not implemented", str(ctx.exception))

    def test_every_group_is_registered(self):
        for argv in (["open"], ["serve"], ["doctor"], ["service", "status"], ["project", "list"], ["job", "list"],
                     ["hooks", "status", "x"], ["usage", "show"], ["phone", "status"], ["backup"]):
            with self.subTest(argv=argv):
                from roadmap.cli import build_parser
                parser = build_parser()
                args = parser.parse_args(argv + ["--json"])
                self.assertTrue(callable(args.handler))

    def test_unknown_command_exit_2(self):
        code, out, err = run(["nosuch"])
        self.assertEqual(code, 2)
        self.assertIn("nosuch", err)

    def test_usage_error_json_envelope_on_stdout(self):
        code, out, _ = run(["nosuch", "--json"])
        self.assertEqual(code, 2)
        body = json.loads(out)
        self.assertIs(body["ok"], False)
        self.assertEqual(body["error"]["code"], "usage")


class ShimTests(unittest.TestCase):
    def test_shim_version_json(self):
        proc = subprocess.run([SHIM, "version", "--json"], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIs(json.loads(proc.stdout)["ok"], True)

    def test_shim_unknown_command_exit_code(self):
        proc = subprocess.run([SHIM, "nosuch"], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
