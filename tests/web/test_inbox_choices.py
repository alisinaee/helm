"""The Inbox answer choices (R9.30, H171): a question with options shows them as aligned option buttons with a letter
and a label (a, b, c ...), the recommended option first; one click answers it. The free-text box stays below as "Other".
A Head ask with no options still shows only the text box. Static checks read web/js/views/inbox.js; the render check
runs questionCardHtml() in node (skipped when node is not installed).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)

WEB = os.path.join(REPO, "web")
INBOX = os.path.join(WEB, "js", "views", "inbox.js")
MAX_LINE = 120
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


NODE_CHECK = r"""
const web = process.argv[1];
const inbox = await import(web + "/js/views/inbox.js");
const now = Date.parse("2026-10-15T10:05:00Z");
const snap = { id: "alpha", title: "Alpha", fetchedAt: "2026-10-15T10:00:00Z", questions: [], tasks: [],
  needsYou: [], head: { rows: [] } };
const q = { id: "Q2", task: null, text: "Which db?", block: false, def: "SQLite",
  opts: ["Postgres: scale later", "SQLite (recommended): simplest", "MySQL"] };
const plain = { id: "Q3", task: null, text: "Free text?", block: false, def: null, opts: [] };
const withOpts = inbox.questionCardHtml({ pid: "alpha", pname: "Alpha", snap: snap, q: q }, now, false);
const noOpts = inbox.questionCardHtml({ pid: "alpha", pname: "Alpha", snap: snap, q: plain }, now, false);
const keys = [...withOpts.matchAll(/qc-key" aria-hidden="true">([a-z])</g)].map(function (m) { return m[1]; });
const values = [...withOpts.matchAll(/data-value="([^"]*)"/g)].map(function (m) { return m[1]; });
console.log(JSON.stringify({ keys: keys, values: values, otherBox: withOpts.indexOf('name="value"') >= 0,
  noOptButtons: (noOpts.match(/qc-opt/g) || []).length, noOptBox: noOpts.indexOf('name="value"') >= 0,
  noOptList: noOpts.indexOf("nz-list") >= 0,
  chipAndLabel: /<button[^>]*qc-opt[^>]*><span class="qc-key" aria-hidden="true">a<\/span><span class="qc-label">SQLite/
    .test(withOpts),
  otherRow: /<span class="qc-id">Other<\/span> <input name="value"[^>]*><\/label><button type="submit" class="btn btn-small">Send</
    .test(withOpts) }));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class InboxChoicesRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(["node", "--input-type=module", "-e", NODE_CHECK, WEB], capture_output=True, text=True,
                             timeout=60)
        if out.returncode != 0:
            raise AssertionError("render check failed: " + out.stderr[-800:])
        cls.got = json.loads(out.stdout.strip().splitlines()[-1])

    def test_options_get_letters_in_order(self):
        self.assertEqual(self.got["keys"], ["a", "b", "c"])

    def test_recommended_option_first_and_answers_by_value(self):
        self.assertEqual(self.got["values"][0], "SQLite")
        self.assertEqual(self.got["values"], ["SQLite", "Postgres", "MySQL"])

    def test_other_text_box_kept(self):
        self.assertTrue(self.got["otherBox"])

    def test_option_row_has_letter_chip_and_label_as_separate_elements(self):
        self.assertTrue(self.got["chipAndLabel"])

    def test_other_row_is_label_input_send(self):
        self.assertTrue(self.got["otherRow"])

    def test_no_options_shows_only_text_box(self):
        self.assertEqual(self.got["noOptButtons"], 0)
        self.assertFalse(self.got["noOptList"])
        self.assertTrue(self.got["noOptBox"])


class InboxChoicesStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(INBOX)

    def test_letter_keys_rendered(self):
        self.assertIn("String.fromCharCode(97 + index)", self.src)

    def test_answer_by_button_uses_question_answer(self):
        self.assertIn('data-action="inbox-answer"', self.src)
        self.assertIn('run("question.answer", { id: qid, value: value }', self.src)

    def test_other_form_kept(self):
        self.assertIn('data-form="inbox-question-answer"', self.src)

    def test_option_css_is_one_row_with_a_28px_chip(self):
        css = read(os.path.join(WEB, "css", "flow.css"))
        self.assertRegex(css, r"\.qc-key \{[^}]*width: 28px")
        self.assertRegex(css, r"\.qc \.nz-list \.qc-opt \{[^}]*min-height: 36px")
        self.assertRegex(css, r"\.qc-label \{[^}]*white-space: nowrap")

    def test_no_inline_styles_or_handlers(self):
        self.assertIsNone(INLINE.search(self.src))

    def test_lines_within_limit(self):
        long = [n for n, line in enumerate(self.src.splitlines(), 1) if len(line) > MAX_LINE]
        self.assertEqual(long, [])


if __name__ == "__main__":
    unittest.main()
