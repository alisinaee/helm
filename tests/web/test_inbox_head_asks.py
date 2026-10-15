"""The Head asks on the Inbox (R7.81): every Head ledger row with status needs-you (snap.head.rows) is an Inbox item:
its kind, summary, age, the head's note, a reply form that sends head.set with the note, and an "Open in Head" link to
#/p/<id>/head?id=Hn. Static checks read web/js/views/inbox.js; the render check runs inboxBody() in node (skipped when
node is not installed) on a view model with asks, other statuses and a second project.
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
const now = Date.parse("2026-10-15T10:00:00Z");
const snap = (id, title, rows) => ({ id: id, title: title, fetchedAt: "2026-10-15T10:00:00Z", questions: [], tasks: [],
  needsYou: [], head: { rows: rows } });
const rowsA = [
  { id: "H3", kind: "ask", sum: "Pick the database", status: "needs-you", age: 90 },
  { id: "H4", kind: "decision", sum: "Done thing", status: "done", age: 5 },
  { id: "H5", kind: "ask", sum: "Blocked on DNS", status: "needs-you", age: 3, note: "Need the DNS zone" },
];
const rowsB = [{ id: "H9", kind: "question", sum: "Scope?", status: "needs-you", age: 2 }];
const vm = { route: { name: "all", section: "inbox" }, snapshotList: [snap("alpha", "Alpha", rowsA),
  snap("beta", "Beta", rowsB)], projects: [{}, {}], home: {}, meterRows: [] };
const c = inbox.collect(inbox.scopeSnapshots(vm));
const html = inbox.inboxBody(vm);
const plain = inbox.inboxBody({ route: { name: "project", id: "alpha", section: "inbox" },
  snapshotList: [snap("alpha", "Alpha", rowsA)], project: {}, meterRows: [] });
console.log(JSON.stringify({
  asks: c.asks.map(function (e) { return e.pid + ":" + e.row.id; }),
  hasSection: html.indexOf('aria-labelledby="inbox-asks-h"') >= 0,
  openLinkA: html.indexOf('href="#/p/alpha/head?id=H3"') >= 0,
  openLinkB: html.indexOf('href="#/p/beta/head?id=H9"') >= 0,
  doneAbsent: html.indexOf("H4") < 0,
  noteShown: html.indexOf("Need the DNS zone") >= 0,
  defaultNote: html.indexOf("The head needs your answer.") >= 0,
  ageShown: /Waiting [^<]+/.test(html),
  formOp: (html.match(/data-op="head.set"/g) || []).length,
  formProject: html.indexOf('data-project="beta" data-id="H9"') >= 0,
  projectScopeLink: plain.indexOf('href="#/p/alpha/head?id=H3"') >= 0,
  countCopy: inbox.sectionView(vm).indexOf("3") >= 0,
  navInbox: (await import(web + "/js/views/nav.js")).countsFor(vm).inbox,
}));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class InboxHeadAskRender(unittest.TestCase):
    def test_asks_render_in_inbox(self):
        result = subprocess.run(["node", "--input-type=module", "-e", NODE_CHECK, WEB], cwd=REPO,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(got["asks"], ["alpha:H3", "alpha:H5", "beta:H9"])
        self.assertTrue(got["hasSection"])
        self.assertTrue(got["openLinkA"])
        self.assertTrue(got["openLinkB"])
        self.assertTrue(got["doneAbsent"])
        self.assertTrue(got["noteShown"])
        self.assertTrue(got["defaultNote"])
        self.assertTrue(got["ageShown"])
        self.assertEqual(got["formOp"], 3)
        self.assertTrue(got["formProject"])
        self.assertTrue(got["projectScopeLink"])
        self.assertTrue(got["countCopy"])
        self.assertEqual(got["navInbox"], 3)


class HeadRowNote(unittest.TestCase):
    def test_note_passes_through_and_truncates(self):
        from datetime import datetime, timezone
        from roadmap.core import snapshot
        moment = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
        entry = {"id": "H3", "kind": "ask", "sum": "Pick", "status": "needs-you", "ts": "2026-10-15T09:00:00Z"}
        self.assertNotIn("note", snapshot.head_row(entry, moment))
        entry["note"] = "x" * 500
        self.assertEqual(len(snapshot.head_row(entry, moment)["note"]), snapshot.HEAD_NOTE_MAX)


class InboxHeadAskSource(unittest.TestCase):
    def setUp(self):
        self.src = read(INBOX)

    def test_reply_uses_existing_head_set_op(self):
        self.assertIn('run("head.set", { id: id, note: value }', self.src)
        self.assertNotIn("head.answer", self.src)
        self.assertNotIn("head.reply", self.src)

    def test_open_in_head_link_and_status_filter(self):
        self.assertIn('"Open in Head"', self.src)
        self.assertIn('projectHash(pid, "head") + "?id=" + encodeURIComponent(id)', self.src)
        self.assertIn('row.status === "needs-you"', self.src)

    def test_badge_count_includes_asks(self):
        self.assertIn("found.questions.length + found.asks.length", self.src)

    def test_no_inline_styles_or_handlers(self):
        self.assertIsNone(INLINE.search(self.src))

    def test_lines_within_limit(self):
        long = [n for n, line in enumerate(self.src.splitlines(), 1) if len(line) > MAX_LINE]
        self.assertEqual(long, [])


if __name__ == "__main__":
    unittest.main()
