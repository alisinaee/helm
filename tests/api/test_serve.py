"""The serve command's port handling and the lsof helper. The servers here never start: a busy port is detected
before anything is served, and the lsof test only reads the port owner of this test process."""

import contextlib
import io
import json
import os
import socket
import unittest

from roadmap import cli
from roadmap.services import loader
from tests.api.support import ServerCase


class BusyPort(ServerCase):
    def test_busy_port_is_exit_4_with_the_owner_named(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(blocker.close)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["serve", "--port", str(port), "--json"])
        self.assertEqual(code, 4)
        body = json.loads(out.getvalue())
        self.assertIs(body["ok"], False)
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertIn("port %d is busy" % port, body["error"]["message"])

    def test_port_out_of_range_is_usage_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["serve", "--port", "70000", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "invalid_input")

    def test_port_owner_finds_a_listener_read_only(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        owner = loader.port_owner(listener.getsockname()[1])
        if owner is None:
            self.skipTest("lsof is not available here")
        self.assertEqual(owner["pid"], os.getpid())

