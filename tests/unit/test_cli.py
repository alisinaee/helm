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
        self.assertEqual(out, "roadmap " + __version__ + "\n")

    def test_stub_command_exit_1_and_error_code(self):
        code, out, _ = run(["doctor", "--json"])
        self.assertEqual(code, 1)
        body = json.loads(out)
        self.assertIs(body["ok"], False)
        self.assertEqual(body["error"]["code"], "not_implemented")

    def test_stub_plain_mode_writes_error_to_stderr(self):
        code, out, err = run(["doctor"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("not implemented", err)

    def test_every_group_is_registered_and_stubbed(self):
        for argv in (["serve"], ["open"], ["service", "logs"], ["project", "check"],
                     ["hooks", "status", "x"], ["phone", "link"], ["doctor"], ["backup"]):
            with self.subTest(argv=argv):
                code, out, _ = run(argv + ["--json"])
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(out)["error"]["code"], "not_implemented")

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

    def test_shim_stub_exit_code(self):
        proc = subprocess.run([SHIM, "doctor"], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
