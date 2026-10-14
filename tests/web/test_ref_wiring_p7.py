"""Copy-reference wiring for the job lists and panels (R7.12 P7).

tests/web/render_ref_p7.mjs renders Running now, Agents, Activity, Recent progress, the Work list, the Tokens panels
(one project and all projects) and the Usage band in node from the golden snapshot plus running and finished jobs and
meters. The checks: each running and agent job row carries one data-action="copy-ref" button with a valid rb: ref
(rb:<project>/job/<id>), an aria-label and a one-line summary; each Tokens and Usage panel header carries a section ref;
no ref or summary has an absolute path or "~"; no copy button sits inside another button or link; the text from the
data is escaped; and the module is lint clean. Skipped with a message when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_ref_p7.mjs")
GOLDEN = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
P7_FILES = ["running.js", "agents.js", "activity.js", "recent.js", "work.js", "limits.js", "usage.js", "tokens.js"]

REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
COPY = re.compile(r'<button[^>]*data-action="copy-ref"[^>]*>')
ATTR = re.compile(r'(data-ref|data-sum|aria-label)="([^"]*)"')
TAG = re.compile(r"<(/?)(button|a)\b[^>]*>")

JOBS = [
    {"id": "j90", "task": "P0.8", "title": "haiku: Check <b>the</b> runner", "model": "haiku",
     "status": "running", "started": "2026-10-13T11:50:00Z", "tokensK": 12, "role": None, "parent": None},
    {"id": "j91", "task": "P0.8", "title": "Lint pass", "model": "sonnet", "status": "running",
     "started": "2026-10-13T11:55:00Z", "tokensK": None, "role": "edit", "parent": "j90"},
    {"id": "j92", "task": "P1.1", "title": "Finished one", "model": "opus", "status": "done",
     "started": "2026-10-13T11:20:00Z", "ended": "2026-10-13T11:40:00Z", "elapsed_s": 1200, "tokensK": 40,
     "role": None, "parent": None},
    {"id": "j93", "task": None, "title": "Broke", "model": "agy", "status": "failed",
     "started": "2026-10-13T10:20:00Z", "ended": "2026-10-13T10:30:00Z", "elapsed_s": 600, "tokensK": None,
     "role": None, "parent": None},
]

METERS = {
    "limits": [
        {"id": "L1", "scope": "global", "window": "day", "kind": "pct", "used": 9.0, "limit": 10, "state": "warn",
         "est": False, "paceAt": "2026-10-13T16:40:00", "src": None},
        {"id": "L2", "scope": "project", "window": "week", "kind": "tok", "used": 120, "limit": 500, "state": "ok",
         "est": True, "paceAt": None, "src": "budget"},
    ],
    "today": {"pts": 9.0, "tokK": 120, "estPts": None},
    "week": {"pct": 62, "tokK": 300, "estPts": None},
}


def augmented_snapshot(path):
    """Write a copy of the golden snapshot with running and finished jobs and meters; return its path."""
    with open(GOLDEN, encoding="utf-8") as fh:
        raw = json.load(fh)
    raw["jobs"] = list(raw.get("jobs") or []) + JOBS
    raw["meters"] = METERS
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return path


def render():
    node = shutil.which("node")
    with tempfile.TemporaryDirectory() as tmp:
        snap = augmented_snapshot(os.path.join(tmp, "snapshot.json"))
        proc = subprocess.run(
            [node, "--experimental-default-type=module", RENDER, WEB, snap],
            capture_output=True, text=True, check=False, timeout=60,
        )
    if proc.returncode != 0:
        raise AssertionError("render_ref_p7.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def copy_buttons(html):
    """Each copy-ref button tag as a dict of its ref, summary and aria-label."""
    found = []
    for tag in COPY.findall(html):
        attrs = dict(ATTR.findall(tag))
        found.append(attrs)
    return found


def nested_copy_buttons(html):
    """The copy buttons that sit inside another button or link (should be none)."""
    stack = []
    bad = []
    for m in TAG.finditer(html):
        closing, name = m.group(1), m.group(2)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == name:
                    del stack[i]
                    break
            continue
        if 'data-action="copy-ref"' in m.group(0) and stack:
            bad.append(m.group(0))
        if not m.group(0).endswith("/>"):
            stack.append(name)
    return bad


class RefWiringP7Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the copy-reference render checks are skipped")
        cls.out = render()

    def test_every_view_renders(self):
        for key, html in self.out.items():
            self.assertTrue(html.strip(), key)

    def test_running_rows_carry_a_valid_job_ref(self):
        html = self.out["running"]
        refs = [b.get("data-ref") for b in copy_buttons(html)]
        rows = html.count('class="row-grid run-item"') + html.count('class="fin-row row-grid"')
        self.assertEqual(len(refs), rows)
        self.assertIn("rb:splitnet/job/j90", refs)
        self.assertTrue(all(r.startswith("rb:splitnet/job/") for r in refs))

    def test_agent_rows_carry_a_job_ref_per_row(self):
        refs = [b.get("data-ref") for b in copy_buttons(self.out["agents"])]
        self.assertIn("rb:splitnet/job/j90", refs)
        self.assertIn("rb:splitnet/job/j91", refs)
        self.assertTrue(all(r.startswith("rb:splitnet/job/") for r in refs))

    def test_every_copy_button_has_a_valid_ref_summary_and_label(self):
        for key in ("running", "agents", "agentsAll", "tokens", "tokensAll", "usage"):
            buttons = copy_buttons(self.out[key])
            self.assertTrue(buttons, key + " has no copy button")
            for attrs in buttons:
                self.assertRegex(attrs.get("data-ref", ""), REF_RE, key)
                self.assertTrue(attrs.get("aria-label", "").startswith("Copy reference to "), key)
                self.assertTrue(attrs.get("data-sum", ""), key)

    def test_refs_and_summaries_carry_no_paths(self):
        for key, html in self.out.items():
            for attrs in copy_buttons(html):
                for name in ("data-ref", "data-sum"):
                    value = attrs.get(name, "")
                    self.assertNotIn("/Users/", value, key)
                    self.assertNotIn("~", value, key)

    def test_no_copy_button_sits_inside_another_button_or_link(self):
        for key, html in self.out.items():
            self.assertEqual(nested_copy_buttons(html), [], key)

    def test_panel_headers_carry_section_refs(self):
        refs = [b.get("data-ref") for b in copy_buttons(self.out["tokens"])]
        for ref in ("rb:splitnet/section/tokens.limits", "rb:splitnet/section/tokens.account",
                    "rb:splitnet/section/tokens.spend", "rb:splitnet/section/tokens.override"):
            self.assertIn(ref, refs)
        usage_refs = [b.get("data-ref") for b in copy_buttons(self.out["usage"])]
        self.assertEqual(usage_refs, ["rb:splitnet/section/usage.band"])

    def test_section_summary_uses_the_count_key(self):
        sums = [b.get("data-sum") for b in copy_buttons(self.out["tokens"])]
        self.assertTrue(all(s.startswith("section count=") for s in sums), sums)

    def test_lists_without_job_rows_carry_no_job_ref(self):
        for key in ("activity", "recent"):
            self.assertNotIn("/job/", self.out[key], key)

    def test_job_title_text_is_escaped(self):
        self.assertNotIn("<b>the</b>", self.out["running"])
        self.assertIn("&lt;b&gt;the&lt;/b&gt;", self.out["running"])

    def test_no_inline_style_or_handler_in_output(self):
        inline = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
        for key, html in self.out.items():
            self.assertIsNone(inline.search(html), key)

    def test_p7_modules_are_lint_clean(self):
        files = [os.path.join(WEB, "js", "views", name) for name in P7_FILES]
        proc = subprocess.run([sys.executable, os.path.join(REPO, "tools", "lint_js.py")] + files,
                              capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
