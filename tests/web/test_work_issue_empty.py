"""R7.98: filters that leave no task still show the issue cards (no "No tasks match" line while issues match), and the
snapshot's issuesClosed key is kept by the state normaliser."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "..", "web"))

SCRIPT = r"""
import { pathToFileURL } from "node:url";
const web = process.argv[2];
globalThis.window = { location: { hash: "" }, matchMedia: () => ({ matches: false }), setTimeout: () => 0,
  addEventListener() {} };
globalThis.document = { dispatchEvent() { return true; }, addEventListener() {}, getElementById: () => null,
  querySelector: () => null, body: {} };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
const work = await import(pathToFileURL(web + "/js/views/work.js").href);
const snap = { id: "p", fetchedAt: 0, tasks: [], phases: [], runningJobs: [], issuesClosed: [],
  issues: [{ id: "I1", title: "bug", kind: "bug", sev: 1, status: "open", tasks: [] }] };
const out = {};
for (const f of ["state:done", ""]) {
  const vm = { now: 0, route: { name: "project", id: "p", section: "work", view: "board", item: null, filters: { f } },
    project: { snapshot: snap }, projects: [], snapshotList: [], home: { loading: false }, projectsError: null };
  const html = work.sectionView(vm);
  out[f] = { noMatch: html.includes("No tasks match"), issueCard: html.includes("I1") };
}
console.log(JSON.stringify(out));
"""


class WorkIssuesWhenNoTaskMatches(unittest.TestCase):
    def test_issue_cards_show_instead_of_no_match(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "probe.mjs")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(SCRIPT)
        proc = subprocess.run(["node", path, WEB], capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        for filt, row in out.items():
            self.assertFalse(row["noMatch"], filt)
            self.assertTrue(row["issueCard"], filt)


class StateKeepsIssuesClosed(unittest.TestCase):
    def test_state_source_reads_issues_closed(self):
        with open(os.path.join(WEB, "js", "state.js"), encoding="utf-8") as fh:
            self.assertIn("issuesClosed: list(raw.issuesClosed)", fh.read())


if __name__ == "__main__":
    sys.exit(unittest.main())
