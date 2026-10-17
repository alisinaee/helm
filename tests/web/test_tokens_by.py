"""R10.35: the By task / By model tables show the weekly-limit estimate column and note."""

import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TokensByTests(unittest.TestCase):
    def test_estimate_column(self):
        out = subprocess.run(["node", os.path.join(HERE, "render_tokens_by.mjs")], capture_output=True, text=True,
                             check=True).stdout
        self.assertIn("Estimate: share of weekly usage by weighted tokens", out)
        self.assertIn("≈ 1.3%", out)  # R1: 1.27 -> 1.3
        self.assertIn("≈ &lt;0.1%", out)  # haiku sliver alone
        self.assertEqual(out.count("≈ Weekly"), 2)
        self.assertNotIn("style=", out)


if __name__ == "__main__":
    unittest.main()
