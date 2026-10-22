"""R7.66: the Head states and kind chips, and the questions from agents block (web/js/views/head.js).

Static checks read head.js, components.css and tokens.css. The render checks run head.js in node (no DOM): the state
chips, the filter bar, the kind chips and the questions group with its one-click answers and one free-text box.
"""

import datetime
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

from roadmap.core.head import fold  # noqa: E402

WEB = os.path.join(REPO, "web")
HEAD_JS = os.path.join(WEB, "js", "views", "head.js")
COMPONENTS = os.path.join(WEB, "css", "components.css")
TOKENS = os.path.join(WEB, "css", "tokens.css")
LABELS = ("Queue", "Doing", "Done", "Failed", "Needs you", "Blocked", "Closed")
KINDS = ("ask", "bug", "rule", "decision", "preference", "question", "review", "info")
NODE_SCRIPT = """
const web = %s;
const head = await import(web + "/js/views/head.js");
const vm = JSON.parse(%s);
const entries = [{ pid: "alpha", pname: "alpha", snap: { fetchedAt: "2026-10-15T10:00:00Z" },
  q: { id: "Q1", text: "Ship the export?", opts: ["yes", "no"], def: "yes", task: "R7.31", block: false } }];
const base = { project: "alpha", view: "list", questions: entries };
console.log(JSON.stringify({
  screen: head.headHtml(vm, Object.assign({ f: "all" }, base)),
  queue: head.headHtml(vm, Object.assign({ f: "queue" }, base)),
  doing: head.headHtml(vm, Object.assign({ f: "doing" }, base)),
  closed: head.headHtml(vm, Object.assign({ f: "closed" }, base)),
  questionsTab: (head.setHeadTab("q"), head.headHtml(vm, Object.assign({ f: "all" }, base))),
  noQuestions: head.headHtml(vm, { f: "all", project: "alpha", view: "list" }),
  hashFailed: head.hashOf({ f: "failed" }),
}));
head.setHeadTab("chat");
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def state_table(src):
    """STATE_OF from head.js: {status: (filter key, label, tone)}."""
    body = re.search(r"const STATE_OF = \{(.*?)\};", src, re.S).group(1)
    rows = re.findall(r'("[\w-]+"|\w+):\s*\["(\w+)",\s*"([^"]+)",\s*"(\w+)"\]', body)
    return {key.strip('"'): (filt, label, tone) for key, filt, label, tone in rows}


def kind_table(src):
    """KIND_TONE from head.js: {kind: tone}."""
    body = re.search(r"const KIND_TONE = \{(.*?)\};", src, re.S).group(1)
    return dict(re.findall(r"(\w+):\s*\"(\w+)\"", body))


def chip_colour_token(components, tone):
    """The colour token a chip tone uses in components.css (the one-line and the multi-line rules both count)."""
    match = re.search(r"\.chip-" + tone + r"\s*\{\s*color:\s*var\((--[\w-]+)\)", components)
    return match.group(1) if match else None


def theme_tokens(path, selector):
    """The hex colour tokens of one theme block of tokens.css."""
    text = read(path)
    start = text.index(selector)
    block = text[start:text.index("}", start)]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted([luminance(a), luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def demo_vm():
    """Ten entries, one per ledger status the view maps, folded with the link states the snapshot would give."""
    recs = []
    plan = [("H1", "new", None), ("H2", "understood", None), ("H3", "bound", "task:R7.31"),
            ("H4", "doing", "task:R7.32"), ("H5", "done", None), ("H6", "failed", "job:j1"),
            ("H7", "needs-you", None), ("H8", "blocked", "task:R7.33"), ("H9", "declined", None),
            ("H10", "merged", None)]
    for i, (hid, status, ref) in enumerate(plan, start=1):
        ts = "2026-10-15T09:%02d:00Z" % i
        recs.append({"v": 1, "t": "e", "id": hid, "ts": ts, "src": "hook", "sid": "s1", "acct": "A",
                     "kind": "bug", "sum": "Row " + hid + " text", "len": 10})
        if ref:
            recs.append({"v": 1, "t": "u", "id": hid, "ts": ts, "by": "person", "link": ["+" + ref]})
        if status == "understood":
            recs.append({"v": 1, "t": "u", "id": hid, "ts": ts, "by": "head",
                         "set": {"kind": "bug", "sum": "Row " + hid + " text"}})
        if status in ("done", "needs-you", "declined", "merged"):
            recs.append({"v": 1, "t": "u", "id": hid, "ts": ts, "by": "person", "set": {"status": status}})
    link_state = {"task:R7.31": "todo", "task:R7.32": "doing", "job:j1": "failed", "task:R7.33": "hold"}
    now = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=datetime.timezone.utc)
    rows = []
    for entry in fold(recs, link_state=link_state, now=now):
        rows.append({"id": entry["id"], "kind": entry["kind"], "sum": entry["sum"], "status": entry["status"],
                     "links": entry["links"], "acct": entry["acct"], "sid": entry["sid"], "ts": entry["ts"],
                     "age": 5})
    return {"pinNow": "2026-10-15T10:00:00Z", "head": {"now": {"model": "Opus 5.5"}, "prev": [], "counts": {},
                                                       "rows": rows}}


def run_node(vm):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    script = NODE_SCRIPT % (json.dumps(WEB), json.dumps(json.dumps(vm)))
    proc = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=False,
                          cwd=REPO)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


class StateSource(unittest.TestCase):
    def setUp(self):
        self.src = read(HEAD_JS)

    def test_filter_bar_offers_the_states_and_keeps_open_and_all(self):
        block = self.src.split("export const FILTERS", 1)[1][:400]
        labels = [label for _, label in re.findall(r'\["(\w+)", "([^"]+)"\]', block)]
        self.assertEqual(labels, ["Open", "Queue", "Doing", "Done", "Failed", "Needs you", "Blocked", "Closed", "All"])
        self.assertNotIn("Unhandled", self.src)

    def test_every_ledger_status_maps_to_one_of_the_seven_states(self):
        table = state_table(self.src)
        self.assertEqual(set(table), {"new", "understood", "bound", "doing", "done", "failed", "needs-you",
                                      "blocked", "declined", "merged"})
        self.assertEqual({label for _, label, _ in table.values()}, set(LABELS))
        self.assertEqual(table["new"][:2], ("queue", "Queue"))
        self.assertEqual(table["bound"][:2], ("doing", "Doing"))
        self.assertEqual(table["failed"][:2], ("failed", "Failed"))
        self.assertEqual(table["blocked"][:2], ("blocked", "Blocked"))
        self.assertEqual(table["declined"][:2], ("closed", "Closed"))

    def test_each_state_has_its_own_tone(self):
        tones = {label: tone for _, label, tone in state_table(self.src).values()}
        self.assertEqual(len(tones), 7)
        self.assertEqual(len(set(tones.values())), 7, tones)

    def test_each_kind_has_its_own_tone(self):
        table = kind_table(self.src)
        self.assertEqual(sorted(table), sorted(KINDS))
        self.assertEqual(len(set(table.values())), len(KINDS))

    def test_every_tone_is_an_existing_chip_with_a_token_colour(self):
        components = read(COMPONENTS)
        tones = {tone for _, _, tone in state_table(self.src).values()} | set(kind_table(self.src).values())
        for tone in tones - {"neutral"}:
            self.assertIsNotNone(chip_colour_token(components, tone), tone)

    def test_tones_keep_4_5_to_1_contrast_in_dark_and_light(self):
        components = read(COMPONENTS)
        tones = {tone for _, _, tone in state_table(self.src).values()} | set(kind_table(self.src).values())
        for name, selector in (("dark", ":root {"), ("light", ':root[data-mode="light"]')):
            colours = theme_tokens(TOKENS, selector)
            for tone in tones - {"neutral"}:
                ratio = contrast(colours[chip_colour_token(components, tone)], colours["--surface-2"])
                self.assertGreaterEqual(ratio, 4.5, "%s %s %.2f" % (name, tone, ratio))


class StateRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_node(demo_vm())

    def test_state_chips_show_their_labels(self):
        screen = self.out["screen"]
        for label in LABELS:
            self.assertIn(">" + label + "</span>", screen, label)
        self.assertNotIn(">new</span>", screen)
        self.assertNotIn(">understood</span>", screen)

    def test_each_state_is_marked_on_its_chip(self):
        for state in ("queue", "doing", "done", "failed", "needs", "blocked", "closed"):
            self.assertIn('data-state="' + state + '"', self.out["screen"], state)

    def test_filters_group_their_states(self):
        self.assertEqual(self.out["queue"].count('<tbody class="hd-item'), 2)
        self.assertEqual(self.out["doing"].count('<tbody class="hd-item'), 2)
        self.assertEqual(self.out["closed"].count('<tbody class="hd-item'), 2)

    def test_kind_chips_use_their_tone(self):
        self.assertIn('<span class="chip chip-danger">bug</span>', self.out["screen"])

    def test_failed_filter_hash_is_offered(self):
        self.assertEqual(self.out["hashFailed"], "#head?f=failed")


class QuestionsRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_node(demo_vm())

    def test_questions_are_their_own_tab_with_a_badge_and_a_banner(self):
        screen = self.out["screen"]
        self.assertIn('data-action="head-tab" data-tab="q" aria-selected="false">Questions <span class="hd-tn hd-tbadge">1</span>', screen)
        self.assertIn('1 question waits for you', screen)
        self.assertNotIn('<details class="hd-qs"', screen)
        self.assertNotIn('data-role="questions"', screen)  # the cards show only on the Questions tab
        src = read(HEAD_JS)
        self.assertIn('<div class="hd-qs" data-role="questions"', src)
        self.assertIn('data-action="inbox-answer" data-project="alpha" data-qid="Q1" data-value="yes"',
                      self.out["questionsTab"])
        self.assertIn('data-role="questions"', self.out["questionsTab"])

    def test_one_free_text_answer_control_per_question(self):
        screen = self.out["questionsTab"]
        self.assertIn('aria-label="Other answer for Q1"', screen)
        self.assertEqual(screen.count('<input name="value" required'), 1)
        self.assertNotIn("Your answer", screen)
        self.assertNotIn('data-op="question.answer"', screen)

    def test_questions_older_than_a_day_are_marked_old(self):
        src = read(HEAD_JS)
        self.assertIn("OLD_QUESTION_MS = 24 * 60 * 60 * 1000", src)
        self.assertIn('(old ? " is-old" : "")', src)
        self.assertIn('old, asked ', src)

    def test_no_questions_no_block(self):
        self.assertNotIn("Questions from agents", self.out["noQuestions"])

    def test_the_view_answers_through_the_inbox_and_writes_no_question_run(self):
        src = read(HEAD_JS)
        self.assertNotIn("pageAction", src)
        self.assertNotIn('run("question.answer"', src)


if __name__ == "__main__":
    unittest.main()
