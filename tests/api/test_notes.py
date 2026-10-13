"""The research notes GET route (WP34): the list and the plain-text reader. Checks: only NN-slug.md names are listed or
read, a name that does not match gives 400, traversal can never reach a file outside the research folder, a symlink is
never followed, a note over 64 KB gives 413 (the list still shows it with lines null), a missing note gives 404, an
unregistered project gives 404, and a foreign Host gives 421. Writes are not possible on this route (POST gives 405)."""

import os

from tests.api.support import PROJECT_ID, ServerCase

LIMIT = 64 * 1024


class NotesRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.join(self.project_root, "docs", "research")
        os.makedirs(self.folder, exist_ok=True)
        self.secret = os.path.join(self.tmp, "secret.txt")
        self._write(self.secret, "TOP SECRET\n")
        self.notes_path = "/api/v1/projects/%s/notes" % PROJECT_ID

    def write_note(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_list_is_empty_before_any_note(self):
        res = self.request("GET", self.notes_path)
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), {"notes": []})

    def test_list_shows_only_numbered_notes_with_title_size_and_lines(self):
        self.write_note("01-landscape.md", "# Landscape of tools\n\n## Question\nWhat exists?\n")
        self.write_note("INDEX.md", "# Research index\n")
        self.write_note("notes.md", "# not numbered\n")
        self.write_note("1-short.md", "# not two digits\n")
        res = self.request("GET", self.notes_path)
        self.assertEqual(res.status, 200)
        rows = res.json()["notes"]
        self.assertEqual([r["name"] for r in rows], ["01-landscape.md"])
        row = rows[0]
        self.assertEqual(row["title"], "Landscape of tools")
        self.assertEqual(row["size"], os.path.getsize(os.path.join(self.folder, "01-landscape.md")))
        self.assertEqual(row["lines"], 4)

    def test_reading_a_note_returns_its_bytes_as_plain_text(self):
        text = "# Title <b>not markup</b>\n\n## Findings\n- a & b\n"
        self.write_note("02-compare.md", text)
        res = self.request("GET", self.notes_path + "/02-compare.md")
        self.assertEqual(res.status, 200)
        self.assertTrue(res.header("content-type").startswith("text/plain"))
        self.assertEqual(res.body.decode("utf-8"), text)

    def test_a_name_that_does_not_match_is_a_bad_request(self):
        for name in ("landscape.md", "01-landscape.txt", "01-Landscape.md", "INDEX.md", "%2E%2E", "x"):
            res = self.request("GET", self.notes_path + "/" + name)
            self.assertEqual(res.status, 400, name)
            self.assertEqual(res.json()["error"]["code"], "invalid_input", name)

    def test_traversal_never_reaches_a_file_outside_the_folder(self):
        for path in ("/api/v1/projects/%s/notes/../../../../secret.txt" % PROJECT_ID,
                     "/api/v1/projects/%s/notes/..%%2Fsecret.txt" % PROJECT_ID,
                     "/api/v1/projects/%s/notes/%%2e%%2e%%2fsecret.txt" % PROJECT_ID):
            res = self.request("GET", path)
            self.assertIn(res.status, (400, 404), path)
            self.assertNotIn(b"TOP SECRET", res.body, path)

    def test_a_symlink_named_like_a_note_is_never_followed(self):
        os.symlink(self.secret, os.path.join(self.folder, "03-link.md"))
        res = self.request("GET", self.notes_path + "/03-link.md")
        self.assertEqual(res.status, 404)
        self.assertNotIn(b"TOP SECRET", res.body)
        listing = self.request("GET", self.notes_path).json()["notes"]
        self.assertEqual(listing, [])

    def test_a_symlinked_research_folder_gives_no_notes(self):
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        with open(os.path.join(elsewhere, "04-x.md"), "w", encoding="utf-8") as fh:
            fh.write("# x\n")
        os.rmdir(self.folder)
        os.symlink(elsewhere, self.folder)
        self.assertEqual(self.request("GET", self.notes_path).json(), {"notes": []})
        self.assertEqual(self.request("GET", self.notes_path + "/04-x.md").status, 404)

    def test_a_note_over_the_cap_is_too_large_and_listed_without_lines(self):
        self.write_note("05-big.md", "# big\n" + "x" * LIMIT)
        res = self.request("GET", self.notes_path + "/05-big.md")
        self.assertEqual(res.status, 413)
        self.assertEqual(res.json()["error"]["code"], "too_large")
        row = self.request("GET", self.notes_path).json()["notes"][0]
        self.assertEqual(row["name"], "05-big.md")
        self.assertIsNone(row["lines"])
        self.assertGreater(row["size"], LIMIT)

    def test_a_note_exactly_at_the_cap_is_read(self):
        self.write_note("06-edge.md", "x" * LIMIT)
        res = self.request("GET", self.notes_path + "/06-edge.md")
        self.assertEqual(res.status, 200)
        self.assertEqual(len(res.body), LIMIT)

    def test_a_missing_note_is_not_found(self):
        res = self.request("GET", self.notes_path + "/07-missing.md")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "not_found")

    def test_an_unregistered_project_is_not_found(self):
        res = self.request("GET", "/api/v1/projects/nope/notes")
        self.assertEqual(res.status, 404)

    def test_a_foreign_host_is_refused(self):
        res = self.request("GET", self.notes_path, host="evil.example")
        self.assertEqual(res.status, 421)

    def test_writes_are_not_allowed_on_the_notes_route(self):
        res = self.request("POST", self.notes_path, headers={"Content-Type": "application/json"}, body=b"{}")
        self.assertEqual(res.status, 405)
