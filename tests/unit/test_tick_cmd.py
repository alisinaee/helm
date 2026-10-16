"""The tick command (one supervisor pass with serve down), the serve-side supervisor pass, and the lock shared by both."""

import json
import shutil
import threading
import time
import unittest
from unittest import mock

from roadmap.http import server
from roadmap.services import supervisor
from roadmap.store import db, jobs_db
from tests.unit.test_project_support import ProjectCase, run_cli


def hold_lock(data_dir, owner="other-pass", until=None):
    """Write the supervisor lock as if another pass were running."""
    conn = db.open_project(data_dir)
    try:
        value = json.dumps({"owner": owner, "until": until if until is not None else time.time() + 600},
                           sort_keys=True)
        with db.txn(conn):
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (supervisor.LOCK_KEY, value))
    finally:
        conn.close()


class TickCommandTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()

    def tick_json(self):
        code, out, err = run_cli(["tick", "--project", "demo", "--json"])
        self.assertEqual(code, 0, err)
        return json.loads(out)["data"]

    def test_tick_does_one_full_pass_with_serve_down(self):
        conn = db.open_project(self.data)
        try:
            with db.txn(conn):
                jobs_db._save(conn, {"id": "j1", "title": "j1", "model": "m", "status": "running", "task": None,
                                     "started": None, "ended": None, "kind": "edit", "files": [],
                                     "heartbeat": 1000.0})
        finally:
            conn.close()
        data = self.tick_json()
        self.assertTrue(data["ran"])
        self.assertEqual(data["reaped"], ["j1"])
        for key in ("expired_leases", "queued", "needs_you", "done_tasks", "closed_asks"):
            self.assertIn(key, data)
        conn = db.open_project(self.data)
        try:
            self.assertEqual(jobs_db._load(conn, "j1")["status"], "failed")
        finally:
            conn.close()

    def test_tick_is_skipped_while_another_pass_holds_the_lock(self):
        hold_lock(self.data)
        data = self.tick_json()
        self.assertFalse(data["ran"])
        self.assertIn("lock", data["reason"])

    def test_tick_runs_again_once_an_expired_lock_is_left_behind(self):
        hold_lock(self.data, until=time.time() - 1)
        self.assertTrue(self.tick_json()["ran"])

    def test_plain_output_names_the_outcome(self):
        code, out, _ = run_cli(["tick", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("tick done", out)
        hold_lock(self.data)
        code, out, _ = run_cli(["tick", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("tick skipped", out)


class ServePassTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()

    def test_serve_pass_ticks_registered_projects_and_respects_the_lock(self):
        reports = server.supervisor_pass()
        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0]["ran"])
        hold_lock(self.data)
        self.assertFalse(server.supervisor_pass()[0]["ran"])

    def test_serve_pass_skips_a_project_whose_data_folder_is_gone(self):
        shutil.rmtree(self.data)
        self.assertEqual(server.supervisor_pass(), [])

    def test_loop_survives_a_failed_pass_and_stops_on_event(self):
        stop = threading.Event()
        calls = []

        def flaky(now=None):
            calls.append(now)
            stop.set()
            raise RuntimeError("boom")

        with mock.patch.object(server, "supervisor_pass", side_effect=flaky):
            with self.assertLogs("roadmap.supervisor", level="WARNING"):
                server.supervisor_loop(stop)
        self.assertEqual(len(calls), 1)


class ServeThreadTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()

    def test_serving_runs_the_supervisor_thread_until_shutdown(self):
        ran = threading.Event()

        def fake_pass(now=None):
            ran.set()
            return []

        httpd = server.make_server(0, sync=lambda: None)
        with mock.patch.object(server, "supervisor_pass", side_effect=fake_pass):
            worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            worker.start()
            self.assertTrue(ran.wait(5), "supervisor pass did not run while serving")
            httpd.shutdown()
            worker.join(5)
        httpd.server_close()
        self.assertTrue(httpd._supervisor_stop.is_set())
        deadline = time.time() + 5
        while any(t.name == "supervisor" for t in threading.enumerate()) and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(any(t.name == "supervisor" for t in threading.enumerate()))

    def test_server_without_supervise_starts_no_supervisor_thread(self):
        httpd = server.make_server(0, sync=lambda: None, supervise=False)
        worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        worker.start()
        time.sleep(0.1)
        self.assertFalse(any(t.name == "supervisor" for t in threading.enumerate()))
        httpd.shutdown()
        worker.join(5)
        httpd.server_close()


if __name__ == "__main__":
    unittest.main()
