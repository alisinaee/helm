"""The keychain read's network rules without a network: a redirect from the usage endpoint is refused, and the error
text never carries the token."""

import unittest
import urllib.request

from roadmap.services import usage


class RedirectRefusal(unittest.TestCase):
    def test_a_redirect_is_refused_before_any_second_request(self):
        handler = usage._NoRedirect()
        req = urllib.request.Request(usage.USAGE_URL, headers={"Authorization": "Bearer FAKE"})
        with self.assertRaises(usage.UsageError) as ctx:
            handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/steal")
        self.assertEqual(str(ctx.exception), "usage endpoint redirected, refusing to follow")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("FAKE", str(ctx.exception))

    def test_the_opener_is_built_with_the_refusing_handler(self):
        opener = urllib.request.build_opener(usage._NoRedirect)
        kinds = [type(h) for h in opener.handlers]
        self.assertIn(usage._NoRedirect, kinds)
        self.assertNotIn(urllib.request.HTTPRedirectHandler, kinds)
