"""The question card (R7.90): options as a vertical list of buttons (label and description), the recommended option
first, an "Other…" text box that sends question.answer, and keys 1 to 6. Static checks read web/js/views/inbox.js; the
render check runs inboxBody() in node (skipped when node is not installed)."""

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
const q = { id: "Q2", task: "P1.1", text: "Which db?", block: false, timeoutS: null, askedMs: null, def: "SQLite",
  opts: ["Postgres: scale later", "SQLite (recommended): simplest", "MySQL", "Redis", "Mongo", "Cassandra"] };
const snap = { id: "alpha", title: "Alpha", fetchedAt: "2026-10-15T10:00:00Z", questions: [q], tasks: [],
  needsYou: [], head: { rows: [] } };
const vm = { route: { name: "project", id: "alpha", section: "inbox" }, snapshotList: [snap],
  project: { snapshot: snap }, meterRows: [] };
const html = inbox.inboxBody(vm);
const labels = [...html.matchAll(/data-value="([^"]*)"/g)].map(function (m) { return m[1]; });
const card = html.slice(html.indexOf('data-qid="Q2"'));
console.log(JSON.stringify({
  parts: inbox.optionParts("SQLite (recommended): simplest"),
  labels: labels,
  firstIsRecommended: labels[0] === "SQLite",
  buttons: (html.match(/class="btn qc-opt/g) || []).length,
  keys: (html.match(/qc-key" aria-hidden="true">([a-f])</g) || []).length,
  listVertical: html.indexOf('class="nz-list ib-opts" role="group"') >= 0,
  otherForm: html.indexOf('data-form="inbox-question-answer"') >= 0,
  otherInput: html.indexOf('name="value"') >= 0,
  descShown: html.indexOf("simplest") >= 0 && html.indexOf("scale later") >= 0,
  recBadge: html.indexOf("recommended</span>") >= 0,
  defaultMarked: /btn-primary is-default" data-action="inbox-answer"[^>]*data-value="SQLite"/.test(html),
  noTerminalNote: html.indexOf("Answer in terminal") < 0,
  cardHasOther: card.indexOf("Other") >= 0,
}));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class QuestionOptionsRender(unittest.TestCase):
    def test_options_render_as_a_vertical_list_with_other(self):
        result = subprocess.run(["node", "--input-type=module", "-e", NODE_CHECK, WEB], cwd=REPO,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(got["parts"], {"label": "SQLite", "desc": "simplest", "recommended": True})
        self.assertEqual(got["labels"][0], "SQLite")
        self.assertEqual(got["labels"][1:], ["Postgres", "MySQL", "Redis", "Mongo", "Cassandra"])
        self.assertEqual(got["buttons"], 6)
        self.assertEqual(got["keys"], 6)
        self.assertTrue(got["firstIsRecommended"])
        self.assertTrue(got["listVertical"])
        self.assertTrue(got["otherForm"])
        self.assertTrue(got["otherInput"])
        self.assertTrue(got["descShown"])
        self.assertTrue(got["recBadge"])
        self.assertTrue(got["defaultMarked"])
        self.assertTrue(got["noTerminalNote"])


class QuestionOptionsSource(unittest.TestCase):
    def setUp(self):
        self.src = read(INBOX)

    def test_text_answers_and_buttons_use_question_answer(self):
        self.assertIn('run("question.answer", { id: qid, value: value }', self.src)
        self.assertIn('form.getAttribute("data-form") === "inbox-question-answer"', self.src)

    def test_keys_one_to_six_without_arming(self):
        self.assertIn("const KEY_MAX = 6;", self.src)
        self.assertIn("for (let n = 1; n <= KEY_MAX; n++) bindKey(String(n), onDigit(n - 1));", self.src)
        self.assertNotIn("ARM_MS", self.src)

    def test_no_inline_styles_or_handlers(self):
        self.assertIsNone(INLINE.search(self.src))

    def test_lines_within_limit(self):
        long = [n for n, line in enumerate(self.src.splitlines(), 1) if len(line) > MAX_LINE]
        self.assertEqual(long, [])


if __name__ == "__main__":
    unittest.main()
