"""R11.122: patch() in web/js/dom.js morphs the live DOM instead of replacing innerHTML: user-opened <details> and
unhidden forms stay, keyed rows keep their nodes, unchanged markup returns false, dirty focused fields and open
popovers defer the write, and 2,000 rows stay fast. Runs in node with a tiny DOM (dom_morph_harness.mjs)."""

import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DOM = os.path.join(os.path.dirname(os.path.dirname(HERE)), "web", "js", "dom.js")


class DomMorph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("node is not installed")
        proc = subprocess.run([node, os.path.join(HERE, "dom_morph_harness.mjs"), "file://" + DOM],
                              capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout.strip().splitlines()[-1])

    def test_open_details_stays_open(self):
        o = self.out
        self.assertTrue(o["d1"])
        self.assertTrue(o["dSame"])
        self.assertTrue(o["dOpen"])
        self.assertEqual(o["dText"], "ttwo")
        self.assertTrue(o["dServerOpen"])
        self.assertFalse(o["dServerClose"])

    def test_unchanged_html_returns_false(self):
        self.assertFalse(self.out["same"])

    def test_keyed_reorder_keeps_nodes(self):
        self.assertTrue(self.out["reorder"])
        self.assertEqual(self.out["reorderText"], "X2")

    def test_dirty_focused_input_defers_and_keeps_value(self):
        o = self.out
        self.assertFalse(o["focusPatch"])
        self.assertEqual(o["focusDeferred"], "a")
        self.assertEqual(o["focusAfter"], "b")
        self.assertTrue(o["inputSame"])
        self.assertEqual(o["inputValue"], "typed")

    def test_clean_focused_input_is_morphed_in_place(self):
        self.assertTrue(self.out["cleanSame"])

    def test_open_popover_defers_the_patch(self):
        o = self.out
        self.assertFalse(o["popPatch"])
        self.assertEqual(o["popDeferred"], "a")
        self.assertEqual(o["popAfter"], "b")

    def test_user_unhidden_form_stays_visible(self):
        self.assertTrue(self.out["formShown"])

    def test_unfocused_fields_follow_new_markup(self):
        o = self.out
        self.assertTrue(o["cbUnchecked"])
        self.assertTrue(o["txFollows"])
        self.assertTrue(o["txFocusedKept"])

    def test_large_list_is_fast(self):
        o = self.out
        self.assertTrue(o["bigChanged"])
        self.assertEqual(o["bigText"], "row 1999 b")
        self.assertLess(o["bigMs"], 1500)


    def test_empty_mount_host_keeps_mounted_children(self):
        o = self.out
        self.assertTrue(o["hostPatch"])
        self.assertTrue(o["hostKept"])
        self.assertEqual(o["hostRev"], "2")

    def test_empty_plain_element_is_emptied(self):
        self.assertTrue(self.out["plainEmptied"])


if __name__ == "__main__":
    unittest.main()
