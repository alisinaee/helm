"""Tests for the port cutover (WP43): the 8780 default, an existing config keeping its port, the doctor warning for a
non-roadmap listener on the legacy port 8765, `roadmap open --port`, and the serve conflict hint.

Nothing binds the real 8765. The legacy port is monkeypatched to a free port, and listeners are dummy sockets. The
open command never starts a browser: its runner is injected or replaced."""

import contextlib
import io
import json
import os
import shutil
import socket
import unittest
from unittest import mock

from roadmap import cli
from roadmap.commands import open as open_cmd
from roadmap.commands import serve
from roadmap.errors import EXIT_CONFLICT, EXIT_USAGE, RoadmapError
from roadmap.services import doctor, launchd
from roadmap.store import config as config_store
from roadmap.store import paths, schema
from tests.unit.test_doctor import DoctorCase, healthy
from tests.unit.test_store_support import HomeCase


def free_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock


class DefaultPortTests(HomeCase):
    def test_fresh_config_gives_8780(self):
        self.assertEqual(config_store.load()["port"], 8780)
        self.assertEqual(serve.DEFAULT_PORT, 8780)
        self.assertEqual(open_cmd.DEFAULT_PORT, 8780)
        self.assertEqual(doctor.DEFAULT_PORT, 8780)

    def test_existing_config_keeps_its_port(self):
        cfg = config_store.default_config()
        cfg["port"] = 8765
        schema.write_data("config", paths.config_file(), cfg)
        self.assertEqual(config_store.load()["port"], 8765)
        self.assertEqual(open_cmd.dashboard_url(), "http://127.0.0.1:8765/")


class OpenPortTests(HomeCase):
    def test_open_port_overrides_the_config_for_one_call(self):
        calls = []

        def runner(argv):
            calls.append(list(argv))
            return 0, "", ""

        result = open_cmd.open_dashboard(port=8790, runner=runner)
        self.assertEqual(calls, [["open", "http://127.0.0.1:8790/"]])
        self.assertEqual(result, {"url": "http://127.0.0.1:8790/", "opened": True})
        self.assertEqual(open_cmd.dashboard_url(), "http://127.0.0.1:8780/")

    def test_cli_open_port_flag_is_used(self):
        calls = []
        out = io.StringIO()
        with mock.patch.object(open_cmd, "RUNNER", lambda argv: (calls.append(list(argv)) or (0, "", ""))):
            with contextlib.redirect_stdout(out):
                code = cli.main(["open", "--port", "8790"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [["open", "http://127.0.0.1:8790/"]])
        self.assertEqual(out.getvalue(), "opened http://127.0.0.1:8790/\n")

    def test_open_port_out_of_range_is_usage_error(self):
        class Args:
            json = False
            port = 70000

        with self.assertRaises(RoadmapError) as ctx:
            open_cmd.handle(Args())
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)


class LegacyPortDoctorTests(DoctorCase):
    def setUp(self):
        super().setUp()
        self.free = free_port()
        patcher = mock.patch.object(doctor, "LEGACY_PORT", self.free)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nothing_listening_is_ok(self):
        report, _ = self.run_doctor(healthy(lsof={"rc": 1, "out": ""}))
        row = [r for r in report["checks"] if r["id"] == "port_legacy"][0]
        self.assertEqual(row["status"], "ok")
        self.assertIsNone(row["fix"])

    def test_foreign_listener_on_the_legacy_port_warns_with_the_fix(self):
        report, _ = self.run_doctor(healthy(lsof={"rc": 0, "out": "p999\ncnode\n"}))
        row = [r for r in report["checks"] if r["id"] == "port_legacy"][0]
        self.assertEqual(row["status"], "warn")
        self.assertEqual(row["fix"], doctor.LEGACY_FIX)
        self.assertIn("The old split-net dashboard may still run on 8765", row["fix"])
        self.assertIn("docs/RELEASE.md", row["fix"])

    def test_dummy_socket_on_the_checked_port_warns(self):
        if shutil.which("lsof") is None:
            self.skipTest("lsof is not available here")
        sock = listener()
        self.addCleanup(sock.close)
        doctor_port = sock.getsockname()[1]
        with mock.patch.object(doctor, "LEGACY_PORT", doctor_port):
            row = doctor.check_legacy_port({"loaded": False, "pid": None}, launchd._default_runner)
        self.assertEqual(row["status"], "warn")
        self.assertIn("pid %d" % os.getpid(), row["detail"])
        self.assertEqual(row["fix"], doctor.LEGACY_FIX)

    def test_no_listener_on_the_checked_port_is_ok(self):
        if shutil.which("lsof") is None:
            self.skipTest("lsof is not available here")
        row = doctor.check_legacy_port({"loaded": False, "pid": None}, launchd._default_runner, port=free_port())
        self.assertEqual(row["status"], "ok")

    def test_roadmap_service_on_the_legacy_port_is_ok(self):
        fake_pid = 4242
        report, _ = self.run_doctor(healthy(lsof={"rc": 0, "out": "p%d\ncPython\n" % fake_pid}))
        row = [r for r in report["checks"] if r["id"] == "port_legacy"][0]
        self.assertEqual(row["status"], "ok")


class ServeConflictHintTests(HomeCase):
    def test_config_on_the_legacy_port_adds_the_doctor_hint(self):
        blocker = listener()
        self.addCleanup(blocker.close)
        busy = blocker.getsockname()[1]
        cfg = config_store.default_config()
        cfg["port"] = busy
        schema.write_data("config", paths.config_file(), cfg)
        with mock.patch.object(serve, "LEGACY_PORT", busy):
            with self.assertRaises(RoadmapError) as ctx:
                serve.run(mock.Mock(port=None, no_usage_loop=True, no_phone=True, json=False))
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertIn("port %d is busy" % busy, ctx.exception.message)
        self.assertEqual(ctx.exception.next, "roadmap doctor")

    def test_busy_port_without_the_legacy_config_has_no_hint(self):
        blocker = listener()
        self.addCleanup(blocker.close)
        busy = blocker.getsockname()[1]
        cfg = config_store.default_config()
        cfg["port"] = 8780
        schema.write_data("config", paths.config_file(), cfg)
        with self.assertRaises(RoadmapError) as ctx:
            serve.run(mock.Mock(port=busy, no_usage_loop=True, no_phone=True, json=False))
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertIsNone(ctx.exception.next)


if __name__ == "__main__":
    unittest.main()
