"""The phone tunnel service: start, stop, link and status with a fake ssh, the stop refusal for a pid that is not our
ssh, token file mode and rotation, and the URL parsing."""

import os
import signal
import stat
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import tunnel
from roadmap.store import config as config_store
from roadmap.store import paths
from tests.unit.test_tunnel_fakes import BANNER, FAKE_PID, SSH_COMMAND, TunnelCase


class StartTests(TunnelCase):
    def test_start_runs_the_exact_ssh_command_and_saves_the_host(self):
        result = tunnel.start(phone_port=8766)
        known_hosts = os.path.join(paths.state_dir(), "known_hosts")
        self.assertEqual(self.ssh.spawned[0][0], ["ssh", "-o", "ServerAliveInterval=30",
                                                   "-o", "StrictHostKeyChecking=yes",
                                                   "-o", "UserKnownHostsFile=" + known_hosts,
                                                   "-R", "80:127.0.0.1:8766", "nokey@localhost.run"])
        self.assertEqual(result, {"running": True, "pid": FAKE_PID, "url": "https://abc123.lhr.life",
                                  "host": "abc123.lhr.life"})
        self.assertEqual(config_store.load()["phoneHost"], "abc123.lhr.life")

    def test_token_is_urlsafe_32_bytes_in_a_0600_file(self):
        tunnel.start()
        token = tunnel.read_token()
        self.assertGreaterEqual(len(token), 43)
        self.assertRegex(token, r"^[A-Za-z0-9_-]+$")
        self.assertEqual(stat.S_IMODE(os.stat(self.token_path()).st_mode), 0o600)

    def test_pid_file_records_the_pid_and_is_private(self):
        tunnel.start()
        with open(self.pid_path(), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), str(FAKE_PID))
        self.assertEqual(stat.S_IMODE(os.stat(self.pid_path()).st_mode), 0o600)

    def test_each_start_rotates_the_token(self):
        tunnel.start()
        first = tunnel.read_token()
        tunnel.stop()
        tunnel.start()
        self.assertNotEqual(first, tunnel.read_token())

    def test_second_start_while_running_is_a_conflict(self):
        tunnel.start()
        with self.assertRaises(RoadmapError) as ctx:
            tunnel.start()
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(len(self.ssh.spawned), 1)

    def test_no_url_in_time_kills_our_pid_and_removes_the_token(self):
        self.ssh.banner = "Welcome to localhost.run, no address yet\n"
        with self.assertRaises(RoadmapError) as ctx:
            tunnel.start(timeout_s=3)
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)
        self.assertEqual(self.ssh.killed, [(FAKE_PID, signal.SIGTERM)])
        self.assertFalse(os.path.exists(self.token_path()))
        self.assertFalse(os.path.exists(self.pid_path()))
        self.assertNotIn("phoneHost", config_store.load())

    def test_missing_ssh_is_exit_6_and_no_token_is_left(self):
        self.ssh.spawn_error = FileNotFoundError("ssh")
        with self.assertRaises(RoadmapError) as ctx:
            tunnel.start()
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)
        self.assertFalse(os.path.exists(self.token_path()))

    def test_the_tunnel_log_is_written_private_and_holds_no_token(self):
        tunnel.start()
        token = tunnel.read_token()
        log_path = self.ssh.spawned[0][1]
        self.assertEqual(stat.S_IMODE(os.stat(log_path).st_mode) & 0o077, 0)
        with open(log_path, encoding="utf-8") as fh:
            self.assertNotIn(token, fh.read())


class UrlParsingTests(TunnelCase):
    def test_banner_links_to_localhost_run_itself_are_skipped(self):
        text = "See https://localhost.run/docs and then https://xyz789.lhr.life/ now"
        self.assertEqual(tunnel.find_tunnel_host(text), "xyz789.lhr.life")

    def test_no_https_host_gives_none(self):
        self.assertIsNone(tunnel.find_tunnel_host("Welcome, no address yet"))
        self.assertIsNone(tunnel.find_tunnel_host("only http://plain.example/ here"))

    def test_host_is_lowercased(self):
        self.assertEqual(tunnel.find_tunnel_host("https://ABC.LHR.LIFE"), "abc.lhr.life")


class StopTests(TunnelCase):
    def test_stop_kills_our_tunnel_and_deletes_token_pid_and_host(self):
        tunnel.start()
        result = tunnel.stop()
        self.assertEqual(self.ssh.killed, [(FAKE_PID, signal.SIGTERM)])
        self.assertEqual(result, {"stopped": True, "pid": FAKE_PID, "tokenDeleted": True})
        self.assertFalse(os.path.exists(self.token_path()))
        self.assertFalse(os.path.exists(self.pid_path()))
        self.assertNotIn("phoneHost", config_store.load())

    def test_stop_refuses_a_pid_that_is_not_our_ssh(self):
        tunnel.start()
        self.ssh.table[FAKE_PID] = "/usr/bin/python3 -m http.server"
        with self.assertRaises(RoadmapError) as ctx:
            tunnel.stop()
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(self.ssh.killed, [])
        self.assertTrue(os.path.exists(self.pid_path()), "the pid file is kept when the pid is not ours")
        self.assertFalse(os.path.exists(self.token_path()), "the token is deleted even when the kill is refused")

    def test_stop_refuses_an_ssh_that_is_not_to_localhost_run(self):
        tunnel.start()
        self.ssh.table[FAKE_PID] = "ssh user@build.example.com"
        with self.assertRaises(RoadmapError):
            tunnel.stop()
        self.assertEqual(self.ssh.killed, [])

    def test_stop_with_a_dead_pid_only_cleans_up(self):
        tunnel.start()
        self.ssh.table.pop(FAKE_PID)
        result = tunnel.stop()
        self.assertEqual(self.ssh.killed, [])
        self.assertIsNone(result["pid"])
        self.assertFalse(os.path.exists(self.pid_path()))

    def test_stop_with_nothing_running_is_fine(self):
        self.assertEqual(tunnel.stop()["stopped"], True)

    def test_is_our_tunnel_needs_both_ssh_and_localhost_run(self):
        self.assertTrue(tunnel.is_our_tunnel(SSH_COMMAND))
        self.assertFalse(tunnel.is_our_tunnel("ssh user@other.example"))
        self.assertFalse(tunnel.is_our_tunnel("python3 localhost.run"))
        self.assertFalse(tunnel.is_our_tunnel(None))


class StatusAndLinkTests(TunnelCase):
    def test_status_before_and_after_start(self):
        self.assertEqual(tunnel.status(), {"running": False, "pid": None, "url": None, "tokenFile": False})
        tunnel.start()
        self.assertEqual(tunnel.status(), {"running": True, "pid": FAKE_PID, "url": "https://abc123.lhr.life",
                                           "tokenFile": True})

    def test_status_never_contains_the_token(self):
        tunnel.start()
        self.assertNotIn(tunnel.read_token(), repr(tunnel.status()))

    def test_link_is_the_host_and_the_token_as_k(self):
        tunnel.start()
        result = tunnel.link()
        self.assertEqual(result["url"], "https://abc123.lhr.life/?k=" + tunnel.read_token())
        self.assertTrue(result["running"])

    def test_link_without_token_or_host_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            tunnel.link()
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        tunnel.start()
        tunnel.stop()
        with self.assertRaises(RoadmapError):
            tunnel.link()

    def test_configured_host_rejects_a_value_that_is_not_a_bare_host(self):
        tunnel._save_host("https://evil.example/path")
        self.assertIsNone(tunnel.configured_host())


class HostAndPidSafetyTests(TunnelCase):
    def test_only_a_tunnel_domain_host_is_taken_from_the_banner(self):
        banner = ("Visit https://evil.example/?k=x first\n"
                  "also https://lookalike.lhr.life.evil.example/\n"
                  "Connect to https://abc123.lhr.life\n")
        self.assertEqual(tunnel.find_tunnel_host(banner), "abc123.lhr.life")
        self.assertIsNone(tunnel.find_tunnel_host("Visit https://evil.example/ only\n"))
        self.ssh.banner = banner
        self.assertEqual(tunnel.start()["host"], "abc123.lhr.life")

    def test_start_never_signals_a_pid_that_is_not_our_ssh(self):
        self.ssh.banner = ""
        spawn = self.ssh.spawn

        def spawn_then_reuse(argv, log_path):
            pid = spawn(argv, log_path)
            self.ssh.table[pid] = "vim notes.txt"  # ssh exited and the pid now belongs to another program
            return pid

        with mock.patch.object(tunnel, "SPAWN", spawn_then_reuse):
            with self.assertRaises(RoadmapError) as ctx:
                tunnel.start(timeout_s=1)
        self.assertEqual(ctx.exception.code, "external")
        self.assertEqual(self.ssh.killed, [])

    def test_stop_with_a_ps_failure_keeps_the_pid_file_and_signals_nothing(self):
        tunnel.start()
        with mock.patch.object(tunnel, "PS", side_effect=tunnel.ProcessListError("ps broke")):
            with self.assertRaises(RoadmapError) as ctx:
                tunnel.stop()
        self.assertEqual(ctx.exception.code, "external")
        self.assertEqual(self.ssh.killed, [])
        self.assertTrue(os.path.exists(self.pid_path()))
