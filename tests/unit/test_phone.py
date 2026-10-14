"""The phone command group through the CLI: start, stop, link and status with a fake ssh, the --json envelopes and exit
codes, and the rule that only `phone link` prints the token. Also the open command module (its runner is a fake)."""

import contextlib
import io
import json

from roadmap import cli
from roadmap.commands import open as open_cmd
from roadmap.errors import EXIT_EXTERNAL, RoadmapError
from roadmap.services import tunnel
from roadmap.store import config as config_store
from roadmap.store import paths, schema
from tests.unit.test_tunnel_fakes import FAKE_PID, TunnelCase


def run(argv):
    """Run the CLI in-process; return (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class PhoneCli(TunnelCase):
    def test_start_json_envelope_has_url_and_no_token(self):
        code, out, err = run(["phone", "start", "--json"])
        self.assertEqual(code, 0, err)
        body = json.loads(out)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["data"]["url"], "https://abc123.lhr.life")
        self.assertNotIn(tunnel.read_token(), out + err)

    def test_start_plain_output_names_the_url_not_the_token(self):
        code, out, err = run(["phone", "start"])
        self.assertEqual(code, 0)
        self.assertIn("https://abc123.lhr.life", out)
        self.assertNotIn(tunnel.read_token(), out + err)

    def test_link_prints_the_private_link_and_warns_on_stderr(self):
        run(["phone", "start"])
        code, out, err = run(["phone", "link"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "https://abc123.lhr.life/?k=" + tunnel.read_token())
        self.assertIn("read access", err)
        self.assertIn("Keep it private", err)

    def test_link_json_envelope(self):
        run(["phone", "start"])
        code, out, _ = run(["phone", "link", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["url"], "https://abc123.lhr.life/?k=" + tunnel.read_token())

    def test_link_before_start_is_not_found_exit_3(self):
        code, out, err = run(["phone", "link", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")

    def test_status_plain_and_json(self):
        self.assertIn("not running", run(["phone", "status"])[1])
        run(["phone", "start"])
        code, out, _ = run(["phone", "status", "--json"])
        body = json.loads(out)
        self.assertEqual((code, body["data"]["running"], body["data"]["pid"]), (0, True, FAKE_PID))
        self.assertIn("running (pid %d)" % FAKE_PID, run(["phone", "status"])[1])

    def test_stop_plain_and_json_clean_up(self):
        run(["phone", "start"])
        code, out, _ = run(["phone", "stop", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["pid"], FAKE_PID)
        self.assertIsNone(tunnel.read_token())
        self.assertNotIn("phoneHost", config_store.load())

    def test_start_twice_is_exit_4_conflict(self):
        run(["phone", "start"])
        code, out, _ = run(["phone", "start", "--json"])
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["error"]["code"], "conflict")

    def test_start_without_ssh_is_exit_6(self):
        self.ssh.spawn_error = FileNotFoundError("ssh")
        code, out, err = run(["phone", "start", "--json"])
        self.assertEqual(code, EXIT_EXTERNAL)
        self.assertEqual(json.loads(out)["error"]["code"], "external")

    def test_stop_of_a_foreign_pid_is_exit_4_and_kills_nothing(self):
        run(["phone", "start"])
        self.ssh.table[FAKE_PID] = "/bin/sleep 600"
        code, out, _ = run(["phone", "stop", "--json"])
        self.assertEqual(code, 4)
        self.assertEqual(self.ssh.killed, [])


class OpenCommand(TunnelCase):
    def test_open_runs_the_macos_open_tool_with_the_loopback_url(self):
        calls = []

        def runner(argv):
            calls.append(list(argv))
            return 0, "", ""

        result = open_cmd.open_dashboard(port=8765, runner=runner)
        self.assertEqual(calls, [["open", "http://127.0.0.1:8765/"]])
        self.assertEqual(result, {"url": "http://127.0.0.1:8765/", "opened": True})

    def test_open_uses_the_default_port_and_the_configured_one(self):
        self.assertEqual(open_cmd.dashboard_url(), "http://127.0.0.1:8780/")
        cfg = config_store.load()
        cfg["port"] = 9001
        schema.write_data("config", paths.config_file(), cfg)
        self.assertEqual(open_cmd.dashboard_url(), "http://127.0.0.1:9001/")

    def test_a_failed_open_is_exit_6(self):
        with self.assertRaises(RoadmapError) as ctx:
            open_cmd.open_dashboard(port=8765, runner=lambda argv: (1, "", "no"))
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)

    def test_handle_prints_the_address(self):
        class Args:
            json = False

        original = open_cmd.RUNNER
        open_cmd.RUNNER = lambda argv: (0, "", "")
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                open_cmd.handle(Args())
        finally:
            open_cmd.RUNNER = original
        self.assertEqual(out.getvalue(), "opened http://127.0.0.1:8780/\n")
