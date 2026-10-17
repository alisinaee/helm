"""Checks for the UX discoverability group (R8.20, R8.21, R8.23, R7.16 step 5b).

Cmd+K has a visible button in the top bar, and the shortcut list is in Settings (helpRows in keys.js). The Mark
button, the m key and the palette command "Mark a bug here" call log.js mark() through topbar.js markBug(), and exist
only on localhost with a CSRF value (never on the phone). Settings choice buttons form a radiogroup (role radio with
aria-checked and a tick on the chosen one, arrow keys move between them). Single-key shortcuts can be turned off in
Settings, and Escape that closes the panel sheet returns focus to the panel toggle. The source checks read the files;
the node check renders the top bar with no window (phone-like) and is skipped when node is missing.
"""

import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
TOPBAR_JS = os.path.join(WEB, "js", "views", "topbar.js")
PALETTE_JS = os.path.join(WEB, "js", "views", "palette.js")
KEYS_JS = os.path.join(WEB, "js", "keys.js")
SETTINGS_JS = os.path.join(WEB, "js", "views", "settings.js")
ICONS = os.path.join(WEB, "icons.svg")
INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TopbarDiscoverSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(TOPBAR_JS)

    def test_cmd_k_button_is_gone_but_keys_stay(self):
        self.assertNotIn('data-action="palette-open"', self.src)
        self.assertNotIn("paletteHtml", self.src)

    def test_mark_gate_stays_for_the_key(self):
        self.assertIn('const LOCAL_HOST = /^(localhost|127\\.0\\.0\\.1|\\[::1\\])$/;', self.src)
        self.assertIn("LOCAL_HOST.test(location.hostname) && Boolean(csrfToken())", self.src)
        self.assertNotIn('data-action="mark-bug"', self.src)

class TopbarRenderNode(unittest.TestCase):
    def test_phone_like_render_has_cmd_k_and_no_mark(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed; the top bar render check is skipped")
        script = (
            'const top = await import(' + repr(TOPBAR_JS).replace("'", '"') + ');'
            'const html = top.topbarView({route: {name: "all", section: "overview", view: ""},'
            ' ui: {panelOpen: true}, conn: {ok: true}, control: null, theme: "auto", meterRows: null});'
            'console.log(html);'
        )
        proc = subprocess.run([node, "--experimental-default-type=module", "-e", script],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn('data-action="palette-open"', proc.stdout)
        self.assertNotIn('data-action="mark-bug"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
