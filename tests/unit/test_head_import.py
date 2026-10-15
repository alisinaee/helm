"""HEAD-SPEC H11: the seeding importer. Parses numbered items and bullets under chosen `## <n>` headings, redacts,
caps the summary at 100 characters, and skips text whose hash is already in the ledger. Runs in temp folders only."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from roadmap.errors import RoadmapError
from roadmap.services import headimport as imp

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

DOC = """# Handover

Intro text that is not an item.

## 1. Vision

- Not imported: section 1 is not chosen.

## 2. Rules from the person (obey)

1. Answer short and spartan.
2. Never push to main without asking
   the person first.
- Use the roadmap CLI for every change.

```
1. code inside a fence is ignored
```

## 2b. Decisions added 2026-10-15

- Decided: the board uses its own design system.
- Does the head ask before a worker edits a shared file?

## 3. Later

- Not imported: section 3.
"""


class HeadImportCase(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-h11-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)
        self.doc = os.path.join(self.root, "HANDOVER.md")
        with open(self.doc, "w", encoding="utf-8") as fh:
            fh.write(DOC)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def ledger(self, name="head.jsonl"):
        path = os.path.join(self.data, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


class ParseTests(HeadImportCase):
    def test_sections_select_only_named_headings(self):
        items = imp.parse_doc(self.doc, "2,2b")
        texts = [i["text"] for i in items]
        self.assertEqual(len(items), 5)
        self.assertNotIn("Not imported: section 1 is not chosen.", texts)
        self.assertFalse(any("section 3" in t for t in texts))

    def test_whole_file_when_no_section_given(self):
        texts = [i["text"] for i in imp.parse_doc(self.doc)]
        self.assertIn("Not imported: section 1 is not chosen.", texts)
        self.assertIn("Not imported: section 3.", texts)

    def test_continuation_lines_join_and_fences_are_skipped(self):
        texts = [i["text"] for i in imp.parse_doc(self.doc, ["2"])]
        self.assertIn("Never push to main without asking the person first.", texts)
        self.assertFalse(any("code inside a fence" in t for t in texts))
        self.assertEqual(len(texts), 3)

    def test_kinds(self):
        by_text = {i["text"]: i["kind"] for i in imp.parse_doc(self.doc, "2,2b")}
        self.assertEqual(by_text["Answer short and spartan."], "rule")
        self.assertEqual(by_text["Decided: the board uses its own design system."], "decision")
        self.assertEqual(by_text["Does the head ask before a worker edits a shared file?"], "ask")

    def test_missing_file_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            imp.parse_doc(os.path.join(self.root, "nope.md"), "2")
        self.assertEqual(ctx.exception.code, "not_found")


class ImportTests(HeadImportCase):
    def test_pure_mode_writes_nothing(self):
        results = imp.import_doc(self.doc, "2,2b", data_dir=None, now=NOW)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r["status"] == "new" and r["id"] is None for r in results))
        self.assertEqual(self.ledger(), [])

    def test_writes_entries_with_import_source(self):
        results = imp.import_doc(self.doc, "2,2b", data_dir=self.data, now=NOW)
        self.assertEqual([r["status"] for r in results], ["logged"] * 5)
        self.assertEqual([r["id"] for r in results], ["H1", "H2", "H3", "H4", "H5"])
        recs = [o for o in self.ledger() if o.get("t") == "e"]
        self.assertEqual({o["src"] for o in recs}, {"import"})
        self.assertTrue(all(o["h"].startswith("sha1:") and len(o["sum"]) <= 100 for o in recs))
        texts = {o["id"]: o for o in self.ledger("head-text.jsonl")}
        self.assertEqual(texts["H1"]["text"], "Answer short and spartan.")

    def test_second_run_is_idempotent(self):
        imp.import_doc(self.doc, "2,2b", data_dir=self.data, now=NOW)
        again = imp.import_doc(self.doc, "2,2b", data_dir=self.data, now=NOW)
        self.assertEqual([r["status"] for r in again], ["skipped"] * 5)
        self.assertEqual(len([o for o in self.ledger() if o.get("t") == "e"]), 5)

    def test_duplicate_text_in_one_doc_is_written_once(self):
        path = os.path.join(self.root, "dup.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("## 1\n\n- Keep the same line.\n- Keep the same line.\n")
        results = imp.import_doc(path, "1", data_dir=self.data, now=NOW)
        self.assertEqual([r["status"] for r in results], ["logged", "skipped"])
        self.assertEqual(len([o for o in self.ledger() if o.get("t") == "e"]), 1)

    def test_secrets_are_redacted_before_write(self):
        path = os.path.join(self.root, "secret.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("## 1\n\n- Use password=hunter2 and mail bob@example.com for the deploy.\n")
        imp.import_doc(path, "1", data_dir=self.data, now=NOW)
        with open(os.path.join(self.data, "head-text.jsonl"), encoding="utf-8") as fh:
            raw = fh.read()
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("bob@example.com", raw)
        self.assertIn("[email]", raw)

    def test_long_item_summary_is_capped(self):
        path = os.path.join(self.root, "long.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("## 1\n\n- " + "word " * 80 + "\n")
        results = imp.import_doc(path, "1", data_dir=self.data, now=NOW)
        self.assertLessEqual(len(results[0]["sum"]), 100)


if __name__ == "__main__":
    unittest.main()
