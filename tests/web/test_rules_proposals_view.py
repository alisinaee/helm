"""Rule proposals in the UI (R7.103): the Inbox "Rule proposals" block (Accept, Edit and accept, Reject, Head links) and
the rule state chip on Head rule rows. Static checks read the two view files; the render check runs inboxBody() in node
(skipped when node is not installed). No inline styles or handlers, lines within 120 characters."""

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
FILES = [os.path.join(WEB, "js", "views", "inbox.js"), os.path.join(WEB, "js", "views", "head.js")]
MAX_LINE = 120
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)

NODE_CHECK = r"""
const web = process.argv[1];
const inbox = await import(web + "/js/views/inbox.js");
const snap = { id: "alpha", title: "Alpha", fetchedAt: "2026-10-15T10:00:00Z", questions: [], tasks: [],
  needsYou: [], head: { rows: [] }, rulesProposals: [{ id: "RP1", text: "Keep small things as context",
  sources: ["H12", "H40"] }] };
const vm = { route: { name: "project", id: "alpha", section: "inbox" }, snapshotList: [snap], project: {},
  meterRows: [] };
const html = inbox.inboxBody(vm);
const empty = { ...snap, rulesProposals: [] };
const emptyHtml = inbox.inboxBody({ ...vm, snapshotList: [empty] });
console.log(JSON.stringify({
  block: html.indexOf('data-key="r:alpha:RP1"') >= 0,
  text: html.indexOf("Keep small things as context") >= 0,
  links: html.indexOf('href="#/p/alpha/head?id=H12"') >= 0 && html.indexOf('href="#/p/alpha/head?id=H40"') >= 0,
  accept: html.indexOf('data-action="rule-accept" data-project="alpha" data-id="RP1"') >= 0,
  reject: html.indexOf('data-action="rule-reject" data-project="alpha" data-id="RP1"') >= 0,
  editForm: html.indexOf('data-form="inbox-rule-edit" data-project="alpha" data-id="RP1"') >= 0,
  noBlockWhenEmpty: emptyHtml.indexOf("data-key=") < 0,
}));
"""


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RuleProposalsRender(unittest.TestCase):
    def test_block_renders_with_accept_edit_reject(self):
        result = subprocess.run(["node", "--input-type=module", "-e", NODE_CHECK, WEB], cwd=REPO,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout.strip().splitlines()[-1])
        for key in ("block", "text", "links", "accept", "reject", "editForm", "noBlockWhenEmpty"):
            self.assertTrue(got[key], key)


class RuleProposalsSource(unittest.TestCase):
    def test_inbox_and_head_wire_the_rule_ops(self):
        inbox = read(FILES[0])
        self.assertIn('"rules.accept"', inbox)
        self.assertIn('"rules.reject"', inbox)
        self.assertIn('"inbox-rule-edit"', inbox)
        self.assertIn('action === "rule-accept"', inbox)

    def test_head_chip_on_rule_rows_only(self):
        head = read(FILES[1])
        self.assertIn("ruleStateHtml(row)", head)
        self.assertIn('row.kind !== "rule"', head)
        self.assertIn('"kept as context"', head)

    def test_no_inline_styles_or_handlers(self):
        for path in FILES:
            self.assertIsNone(INLINE.search(read(path)), path)

    def test_lines_within_limit(self):
        for path in FILES:
            for number, line in enumerate(read(path).splitlines(), 1):
                self.assertLessEqual(len(line), MAX_LINE, "%s:%d" % (path, number))


if __name__ == "__main__":
    unittest.main()
