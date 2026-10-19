"""ROADMAP_PUBLIC_HOST and ROADMAP_BIND_HOST: serving behind a reverse proxy under one public HTTPS name."""

import os
import unittest
from unittest import mock

from roadmap.http import security, server


class PublicHostTest(unittest.TestCase):
    def test_unset_keeps_loopback_only(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(security.public_host())
            self.assertFalse(security.host_allowed("helm.example.com", 8780))
            self.assertEqual(security.origins(8780), ("http://127.0.0.1:8780", "http://localhost:8780"))

    def test_set_accepts_the_public_name_and_origin(self):
        with mock.patch.dict(os.environ, {"ROADMAP_PUBLIC_HOST": "Helm.Example.com"}, clear=True):
            self.assertTrue(security.host_allowed("helm.example.com", 8780))
            self.assertTrue(security.host_allowed("helm.example.com:443", 8780))
            self.assertTrue(security.host_allowed("127.0.0.1:8780", 8780))
            self.assertFalse(security.host_allowed("evil.example.com", 8780))
            self.assertFalse(security.host_allowed("helm.example.com:8080", 8780))
            self.assertIn("https://helm.example.com", security.origins(8780))
            self.assertNotIn("http://helm.example.com", security.origins(8780))

    def test_invalid_names_are_ignored(self):
        for bad in ("localhost", "a b.com", "x.com/evil", "*.example.com", "-a.com"):
            with mock.patch.dict(os.environ, {"ROADMAP_PUBLIC_HOST": bad}, clear=True):
                self.assertIsNone(security.public_host(), bad)

    def test_write_from_public_origin_passes(self):
        headers = {"Sec-Fetch-Site": "same-origin", "Origin": "https://helm.example.com", "X-Roadmap-CSRF": "t"}
        with mock.patch.dict(os.environ, {"ROADMAP_PUBLIC_HOST": "helm.example.com"}, clear=True):
            self.assertIsNone(security.write_refusal(headers, "t", 8780))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(security.write_refusal(headers, "t", 8780), "origin")


class BindHostTest(unittest.TestCase):
    def test_default_and_override(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(server.main_bind_host(), "127.0.0.1")
        with mock.patch.dict(os.environ, {"ROADMAP_BIND_HOST": "192.168.1.5"}, clear=True):
            self.assertEqual(server.main_bind_host(), "192.168.1.5")
        for bad in ("example.com", "::1", "300.1.1.1"):
            with mock.patch.dict(os.environ, {"ROADMAP_BIND_HOST": bad}, clear=True):
                self.assertEqual(server.main_bind_host(), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
