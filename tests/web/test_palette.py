"""The command palette (WP61b): key detection and search ranking run in node through tests/web/palette_probe.mjs; every
op the palette sends must be a registered command op; and the palette and its stylesheet keep the CSP and token rules.
Node-based checks are skipped with a message when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
PROBE = os.path.join(TESTS, "web", "palette_probe.mjs")
PALETTE_JS = os.path.join(WEB, "js", "views", "palette.js")
PALETTE_CSS = os.path.join(WEB, "css", "palette.css")
KEYS_JS = os.path.join(WEB, "js", "keys.js")
APP_JS = os.path.join(WEB, "js", "app.js")
INDEX = os.path.join(WEB, "index.html")
TOKENS = os.path.join(WEB, "css", "tokens.css")

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
INLINE_STYLE = re.compile(r"""\bstyle\s*=\s*(["']|\\["'])""")
INLINE_HANDLER = re.compile(r"""\bon[a-z]{3,}\s*=\s*(["']|\\["'])""")
STYLE_PROP = re.compile(r"\.style\.|\.setAttribute\(\s*[\"']style[\"']")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def probe():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, PROBE, WEB], capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("palette_probe.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class PaletteKeysAndSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = probe()

    def test_cmd_or_ctrl_k_opens_and_nothing_else(self):
        keys = self.out["keys"]
        self.assertTrue(keys["cmdK"])
        self.assertTrue(keys["ctrlK"])
        self.assertTrue(keys["upperCtrlK"])
        for name in ("plainK", "cmdJ", "altCmdK", "shiftCmdK", "nullEvent"):
            self.assertFalse(keys[name], name)

    def test_task_id_prefix_ranks_first(self):
        search = self.out["search"]
        self.assertEqual(search["p1"][:2], ["P1.1", "P1.2"])
        self.assertEqual(search["p24"], ["P2.4"])

    def test_issue_and_question_and_title_are_found(self):
        search = self.out["search"]
        self.assertEqual(search["issue"], ["I1"])
        self.assertEqual(search["question"], ["Q3"])
        self.assertEqual(search["titleWord"], ["P1.2"])

    def test_no_match_and_limit(self):
        search = self.out["search"]
        self.assertEqual(search["none"], [])
        self.assertLessEqual(search["limit"], 10)

    def test_command_prefixes(self):
        search = self.out["search"]
        self.assertEqual(search["stopFirst"][0], ">stop")
        self.assertEqual(search["goWork"], [">go work", ">go workflow"])
        self.assertEqual(search["start"], [">start P1.2"])

    def test_typed_unknown_task_still_offers_its_command(self):
        search = self.out["search"]
        self.assertEqual(search["startUnknown"], [">start P9.9"])
        self.assertEqual(search["doneUnknown"], [">done P9.9"])

    def test_all_projects_has_no_project_commands(self):
        search = self.out["search"]
        self.assertEqual(search["noProject"], [])
        self.assertEqual(search["noProjectTasks"], [])
        commands = self.out["commandsAllProjects"]
        self.assertIn(">go work", commands)
        self.assertNotIn(">stop", commands)
        self.assertIn(">stop", self.out["commands"])


class PaletteOpsTest(unittest.TestCase):
    def test_every_op_the_palette_sends_is_registered(self):
        import roadmap.services.cmdops  # noqa: F401  (registers the control, task and feature ops)
        from roadmap.services import commands

        sent = set(re.findall(r'\brun\(\s*"([a-z]+\.[a-z_]+)"', read(PALETTE_JS)))
        self.assertEqual(sent, {"control.stop", "control.resume", "task.start", "task.status"})
        missing = sorted(op for op in sent if op not in commands.OPS)
        self.assertEqual(missing, [])

    def test_done_status_is_a_valid_task_status(self):
        from roadmap.services import commands

        self.assertIn("done", commands.TASK_STATUSES)


class PaletteStaticTest(unittest.TestCase):
    def test_no_inline_style_handlers_or_eval(self):
        for path in (PALETTE_JS, PALETTE_CSS):
            text = read(path)
            self.assertIsNone(INLINE_STYLE.search(text), path)
            self.assertIsNone(INLINE_HANDLER.search(text), path)
            self.assertIsNone(re.search(r"\beval\s*\(|new\s+Function\b", text), path)
        self.assertIsNone(STYLE_PROP.search(read(PALETTE_JS)), "palette.js sets a style property")

    def test_no_hex_outside_tokens(self):
        self.assertIsNone(HEX.search(read(PALETTE_JS)))
        self.assertIsNone(HEX.search(read(PALETTE_CSS)))

    def test_stylesheet_is_small_and_linked_once(self):
        self.assertLessEqual(os.path.getsize(PALETTE_CSS), 1536)
        index = read(INDEX)
        self.assertEqual(index.count('href="/css/palette.css"'), 1)

    def test_keys_and_app_are_wired(self):
        keys = read(KEYS_JS)
        app = read(APP_JS)
        self.assertIn("isPaletteKey(event)", keys)
        self.assertIn("hooks.openPalette()", keys)
        self.assertIn("openPalette: function ()", app)
        self.assertIn('from "./views/palette.js"', app)

    def test_dialog_and_listbox_aria(self):
        text = read(PALETTE_JS)
        for needle in ('role", "combobox"', 'role", "listbox"', 'role="option"', 'aria-selected',
                       'aria-activedescendant', "showModal()", 'aria-controls", "palette-list"'):
            self.assertIn(needle, text)

    def test_row_tracks_are_three_columns(self):
        css = read(PALETTE_CSS)
        match = re.search(r"\.palette-opt\{[^}]*--rg:([^;]+);", css)
        self.assertIsNotNone(match)
        self.assertEqual(len(match.group(1).split()), 3)

    def test_colours_come_from_tokens(self):
        tokens = read(TOKENS)
        for name in ("--surface-1", "--surface-0", "--sel", "--focus", "--scrim", "--line"):
            self.assertIn(name + ":", tokens)
            self.assertIn("var(" + name + ")", read(PALETTE_CSS))


if __name__ == "__main__":
    unittest.main()
