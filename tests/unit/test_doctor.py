"""Tests for roadmap doctor: every check ok, each check failing or warning on its own, the exit codes, and the --json
envelope. launchctl, lsof, security and plutil are fake runners; the health probe is injected. No network."""

import json
import os
import stat
import sys
import unittest
from unittest import mock

from roadmap.services import doctor, launchd
from roadmap.services import usage as usage_service
from roadmap.store import atomic, config as config_store, paths, schema
from tests.unit.test_launchd_support import FakeRunner, LaunchdCase, SAMPLE_PRINT, answer_for, envelope, run_cli


def healthy(**overrides):
    """A handler where every tool answers like a healthy install. overrides replace one tool's answer."""
    answers = {
        "launchctl": {"rc": 0, "out": SAMPLE_PRINT},
        "lsof": {"rc": 0, "out": "p4242\ncPython\n"},
        "security": {"rc": 0, "out": "keychain: attributes only\n"},
        "/usr/bin/plutil": {"rc": 0, "out": "OK"},
    }
    answers.update(overrides)
    return answer_for(**answers)


REAL_PROBE = doctor.probe_health


def answer_ok(port, timeout=1.0):
    return True, "answered on 127.0.0.1:%d" % port


def no_answer(port, timeout=1.0):
    return False, "no answer (ConnectionRefusedError)"


def row(report, check_id):
    matches = [r for r in report["checks"] if r["id"] == check_id]
    assert len(matches) == 1, check_id
    return matches[0]


class DoctorCase(LaunchdCase):
    def setUp(self):
        super().setUp()
        for folder in (paths.config_dir(), paths.state_dir(), paths.logs_dir()):
            paths.ensure_dir(folder)
        self.patch(mock.patch("roadmap.services.doctor.shutil.which", return_value="/usr/local/bin/roadmap"))
        self.patch(mock.patch.object(doctor, "probe_health", answer_ok))
        self.install_plist()
        self.write_usage({})

    def patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def install_plist(self):
        os.makedirs(self.agents, exist_ok=True)
        text = launchd.render_plist(python=sys.executable, logs_dir=paths.logs_dir())
        launchd._write_plist(launchd.plist_path(), text)

    def write_usage(self, changes):
        from datetime import datetime, timezone
        record = {"weeklyPercent": 62, "fiveHourPercent": 20, "weeklyResetsAt": None, "fiveHourResetsAt": None,
                  "updated": datetime.now(timezone.utc).isoformat(), "source": "test", "lastError": None}
        record.update(changes)
        schema.write_data("usage", paths.usage_file(), record)

    def run_doctor(self, handler=None, probe=answer_ok):
        fake = FakeRunner(handler or healthy())
        return doctor.run(runner=fake, probe=probe), fake


class AllOkTests(DoctorCase):
    def test_every_check_is_ok_and_exit_is_zero(self):
        report, _ = self.run_doctor()
        bad = [r for r in report["checks"] if r["status"] != "ok"]
        self.assertEqual(bad, [])
        self.assertEqual(report["summary"], {"ok": len(report["checks"]), "warn": 0, "fail": 0})
        self.assertEqual(report["exitCode"], 0)
        ids = {r["id"] for r in report["checks"]}
        for expected in ("python", "repo", "shim", "config", "plist", "service", "health", "port", "modes",
                         "keychain", "usage", "projects", "logs"):
            self.assertIn(expected, ids)

    def test_checks_only_use_read_only_tools(self):
        _, fake = self.run_doctor()
        tools = {call[0] for call in fake.calls}
        self.assertLessEqual(tools, {"launchctl", "lsof", "security", "/usr/bin/plutil"})
        for call in fake.calls:
            if call[0] == "launchctl":
                self.assertEqual(call[1], "print")
            if call[0] == "security":
                self.assertNotIn("-w", call)  # metadata only, never the token

    def test_security_check_never_shows_the_token_text(self):
        report, _ = self.run_doctor(healthy(security={"rc": 0, "out": "password: SECRETTOKEN"}))
        self.assertNotIn("SECRETTOKEN", json.dumps(report))


class PythonAndRepoTests(DoctorCase):
    def test_old_python_fails(self):
        with mock.patch.object(sys, "version_info", (3, 8, 18, "final", 0)):
            result = doctor.check_python()
        self.assertEqual(result["status"], "fail")
        self.assertIn("3.9", result["fix"])

    def test_missing_repo_package_fails(self):
        with mock.patch.object(doctor.launchd, "repo_root", return_value=self.tmp):
            self.assertEqual(doctor.check_repo()["status"], "fail")

    def test_shim_not_executable_fails_with_chmod_fix(self):
        real = os.path.join(launchd.repo_root(), "bin", "roadmap")
        with mock.patch.object(doctor.os, "access", return_value=False):
            result = doctor.check_shim()
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["fix"], "Run: chmod +x " + real)

    def test_shim_not_on_path_is_only_a_warning(self):
        with mock.patch("roadmap.services.doctor.shutil.which", return_value=None):
            result = doctor.check_shim()
        self.assertEqual((result["id"], result["status"]), ("shim_path", "warn"))


class PlistAndServiceTests(DoctorCase):
    def test_missing_plist_is_a_warning_with_install_fix(self):
        os.remove(launchd.plist_path())
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "plist")["status"], "warn")
        self.assertEqual(row(report, "plist")["fix"], "Run: roadmap service install")

    def test_plist_that_does_not_lint_fails(self):
        report, _ = self.run_doctor(healthy(**{"/usr/bin/plutil": {"rc": 1, "out": "", "err": "bad plist"}}))
        self.assertEqual(row(report, "plist")["status"], "fail")
        self.assertEqual(report["exitCode"], doctor.EXIT_DOCTOR)

    def test_service_not_loaded_is_a_warning(self):
        report, _ = self.run_doctor(healthy(launchctl={"rc": 113, "err": "Could not find service"}))
        self.assertEqual(row(report, "service")["status"], "warn")
        self.assertIn("roadmap service start", row(report, "service")["fix"])

    def test_health_failure_is_only_a_warning_when_not_installed(self):
        os.remove(launchd.plist_path())
        report, _ = self.run_doctor(healthy(launchctl={"rc": 113}, lsof={"rc": 1, "out": ""}), probe=no_answer)
        self.assertEqual(row(report, "health")["status"], "warn")
        self.assertEqual(report["exitCode"], 0)

    def test_health_failure_is_a_failure_when_the_service_is_loaded(self):
        report, _ = self.run_doctor(probe=no_answer)
        self.assertEqual(row(report, "health")["status"], "fail")
        self.assertEqual(report["exitCode"], doctor.EXIT_DOCTOR)
        self.assertIn("roadmap service restart", row(report, "health")["fix"])

    def test_health_probe_only_uses_loopback_and_one_second(self):
        conn = mock.MagicMock()
        conn.getresponse.return_value.status = 200
        conn.getresponse.return_value.read.return_value = b'{"ok": true, "version": "1.0.0"}'
        with mock.patch("roadmap.services.doctor.http.client.HTTPConnection", return_value=conn) as ctor:
            self.assertEqual(REAL_PROBE(8765)[0], True)
        ctor.assert_called_once_with("127.0.0.1", 8765, timeout=1.0)
        self.assertEqual(conn.request.call_args[0][:2], ("GET", "/api/v1/health"))


class PortTests(DoctorCase):
    def test_free_port_is_ok(self):
        report, _ = self.run_doctor(healthy(lsof={"rc": 1, "out": ""}))
        self.assertEqual(row(report, "port")["status"], "ok")
        self.assertEqual(row(report, "port")["detail"], "free")

    def test_port_held_by_someone_else_fails_and_names_the_process(self):
        report, _ = self.run_doctor(healthy(lsof={"rc": 0, "out": "p999\ncnode\n"}))
        port = row(report, "port")
        self.assertEqual(port["status"], "fail")
        self.assertIn("node (pid 999)", port["detail"])

    def test_missing_lsof_is_a_warning(self):
        report, _ = self.run_doctor(healthy(lsof={"rc": 127, "err": "lsof not found"}))
        self.assertEqual(row(report, "port")["status"], "warn")


class ModeTests(DoctorCase):
    def test_wide_config_dir_fails_with_chmod_fix(self):
        os.chmod(paths.config_dir(), 0o755)
        report, _ = self.run_doctor()
        result = row(report, "modes")
        self.assertEqual(result["status"], "fail")
        self.assertIn("chmod 0700 " + paths.config_dir(), result["fix"])

    def test_phone_token_must_be_0600(self):
        token = paths.phone_token_file()
        atomic.write_json(token, {"x": 1})
        os.chmod(token, 0o644)
        self.assertEqual(row(self.run_doctor()[0], "modes")["status"], "fail")
        os.chmod(token, 0o600)
        self.assertEqual(row(self.run_doctor()[0], "modes")["status"], "ok")
        self.assertEqual(stat.S_IMODE(os.stat(token).st_mode), 0o600)


class KeychainTests(DoctorCase):
    def test_found_is_ok(self):
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "keychain")["status"], "ok")

    def test_not_found_is_a_warning(self):
        report, _ = self.run_doctor(healthy(security={"rc": 44}))
        result = row(report, "keychain")
        self.assertEqual((result["status"], result["detail"]), ("warn", "not found"))

    def test_denied_is_a_warning_that_mentions_the_one_time_prompt(self):
        report, _ = self.run_doctor(healthy(security={"rc": 36}))
        result = row(report, "keychain")
        self.assertEqual(result["status"], "warn")
        self.assertIn("denied", result["detail"])
        self.assertIn("macOS asks once for access", result["fix"])


class UsageTests(DoctorCase):
    def test_last_error_is_a_warning(self):
        self.write_usage({"lastError": "usage endpoint returned HTTP 500"})
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "usage")["status"], "warn")
        self.assertIn("HTTP 500", row(report, "usage")["detail"])

    def test_stale_usage_is_a_warning(self):
        self.write_usage({"updated": "2020-01-01T00:00:00+00:00"})
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "usage")["status"], "warn")
        self.assertIn("stale", row(report, "usage")["detail"])

    def test_no_usage_yet_is_a_warning(self):
        os.remove(paths.usage_file())
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "usage")["status"], "warn")


class ProjectTests(DoctorCase):
    def add_project(self, tasks_text=None):
        folder = self.make_project("alpha")
        data = os.path.join(folder, "docs")
        os.makedirs(data, exist_ok=True)
        if tasks_text is not None:
            with open(os.path.join(data, "tasks.json"), "w", encoding="utf-8") as fh:
                fh.write(tasks_text)
        config_store.add_project("Alpha", folder)
        return data

    def test_project_with_a_broken_file_fails(self):
        self.add_project(tasks_text="{not json")
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "project:alpha:files")["status"], "fail")
        self.assertEqual(report["exitCode"], doctor.EXIT_DOCTOR)

    def test_project_without_hooks_is_a_warning(self):
        from roadmap.services import projects
        self.add_project(tasks_text=json.dumps({"schemaVersion": 1, "phases": [], "tasks": []}))
        with mock.patch.object(projects, "check_projects", wraps=projects.check_projects):
            report, _ = self.run_doctor()
        self.assertEqual(row(report, "project:alpha:hooks")["status"], "warn")
        self.assertEqual(row(report, "project:alpha:hooks")["fix"], "Run: roadmap hooks install alpha")


class LogSizeTests(DoctorCase):
    def test_launchd_log_over_5_mb_is_a_warning(self):
        with open(os.path.join(paths.logs_dir(), "launchd.err"), "wb") as fh:
            fh.write(b"e" * (5 * 1024 * 1024 + 1))
        report, _ = self.run_doctor()
        self.assertEqual(row(report, "logs")["status"], "warn")

    def test_small_logs_are_ok(self):
        self.assertEqual(row(self.run_doctor()[0], "logs")["status"], "ok")


class DoctorCommandTests(DoctorCase):
    def test_json_lists_checks_and_exits_zero_when_healthy(self):
        self.use_runner(FakeRunner(healthy()))
        with mock.patch.object(doctor, "probe_health", answer_ok):
            code, out, _ = run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["data"]["exitCode"], 0)
        self.assertGreater(len(body["data"]["checks"]), 10)

    def test_json_exits_10_when_a_check_failed_and_prints_one_envelope(self):
        self.use_runner(FakeRunner(healthy(lsof={"rc": 0, "out": "p999\ncnode\n"})))
        with mock.patch.object(doctor, "probe_health", answer_ok):
            code, out, _ = run_cli(["doctor", "--json"])
        self.assertEqual(code, 10)
        self.assertEqual(out.count("\n"), 1)  # one envelope line only
        body = json.loads(out)
        self.assertEqual(body["data"]["summary"]["fail"], 1)

    def test_plain_output_has_fix_lines(self):
        self.use_runner(FakeRunner(healthy(launchctl={"rc": 113}, lsof={"rc": 1, "out": ""})))
        with mock.patch.object(doctor, "probe_health", no_answer):
            code, out, _ = run_cli(["doctor"])
        self.assertIn("fix: Run: roadmap service start", out)
        self.assertIn("warn", out)
        self.assertEqual(code, 0 if "FAIL" not in out else 10)


if __name__ == "__main__":
    unittest.main()
