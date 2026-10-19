"""UX group B (R8.5-R8.10): the Overview cards, the Activity rows, the Agents rows and the Roadmap lanes. The checks read
the renderers and the two CSS files they use; no browser is needed."""

import os
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
VIEWS = os.path.join(REPO, "web", "js", "views")
CSS = os.path.join(REPO, "web", "css")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class OverviewCardsTest(unittest.TestCase):
    def test_banner_has_no_stop_button(self):
        # R8.6: Stop lives in the top bar only; the Running banner just says what is happening.
        text = read(VIEWS, "overview.js")
        self.assertNotIn('data-op="control.stop"', text)
        self.assertIn('"Running. Agents may start jobs."', text)
        self.assertIn('data-op="control.resume"', text)

    def test_missing_meter_values_say_unknown(self):
        # R8.4 (overview part): a bare dash is replaced by one word.
        text = read(VIEWS, "overview.js")
        self.assertIn('const UNKNOWN = "unknown";', text)
        self.assertNotIn('"This week: " + MISSING', text)

    def test_empty_next_and_recent_cards_explain_and_point_somewhere(self):
        # R8.5: an empty card says why it is empty and gives one next step.
        nxt = read(VIEWS, "next.js")
        self.assertIn("Nothing is queued.", nxt)
        self.assertIn('/roadmap">Open Roadmap</a>', nxt)
        recent = read(VIEWS, "recent.js")
        self.assertNotIn("No log rows", recent)
        self.assertIn("Nothing logged yet.", recent)


class ActivityRowsTest(unittest.TestCase):
    def test_source_names_are_plain_words(self):
        # R8.7: the log keeps gui, cli, agent or phone; the row shows the plain name.
        text = read(VIEWS, "activity.js")
        self.assertIn('gui: "Dashboard"', text)
        self.assertIn("SOURCE_WORD[line.src]", text)
        self.assertNotIn("chipHtml(line.src ||", text)

    def test_undo_label_says_what_it_undoes(self):
        text = read(VIEWS, "activity.js")
        # R7.65: the visible label is the fixed word; the full text is in aria-label and title.
        self.assertIn('class="act-undo"', text)
        self.assertIn('aria-label="\' + label + \'" title="\' + label', text)
        self.assertIn('class="act-row row-grid"', text)

    def test_undo_sits_in_one_fixed_column(self):
        flow = read(CSS, "flow.css")
        self.assertIn(".act-list > .act-row.row-grid { grid-template-columns: 3rem auto minmax(0, 1fr) 1.75rem;", flow)
        self.assertIn(".act-undo { display: inline-grid; place-items: center; width: 28px; height: 28px;", flow)


class AgentsRowsTest(unittest.TestCase):
    def test_finished_rows_use_the_running_row_grid(self):
        # R8.8: one set of tracks for running and finished jobs.
        text = read(VIEWS, "agents.js")
        self.assertIn('<li class="ag-row"><div class="row-grid rg-agent">', text)
        self.assertNotIn("rg-fin", text)
        self.assertNotIn("act-row", text)

    def test_agent_rows_use_fixed_tracks_and_wrap_on_a_phone(self):
        # The header (Model, Effort, Job, Task, Elapsed, Tokens) and every row share the same eight tracks.
        css = read(CSS, "components.css")
        self.assertIn(".row-grid.rg-agent { --rg: 1.5rem 7.5rem minmax(0, 1fr) 4.5rem 3rem 4.5rem 7.5rem 4.25rem;", css)
        self.assertIn(".row-grid.rg-head { display: none; }", css)
        self.assertIn("@media (min-width: 640px) { .row-grid.rg-head { display: grid; } }", css)
        # Phone: line 1 is lead, title and action; the numbers wrap to the next line with tokens kept right.
        self.assertIn(".rg-agent>:nth-child(8) { order: 2; flex: none }", css)
        self.assertIn(".rg-agent>:nth-child(7) { margin-left: auto }", css)

    def test_running_tokens_show_a_dash_when_unknown(self):
        # Unknown tokens show the shared missing-value dash (MISSING), not the words "not yet" (see test_agents).
        text = read(VIEWS, "agents.js")
        self.assertIn("job.tokensK == null ? MISSING : fmtTokens(job.tokensK);", text)
        self.assertNotIn('"not yet"', text)


class RoadmapLanesTest(unittest.TestCase):
    def test_done_phases_start_folded(self):
        # R8.10: a done phase starts collapsed; an explicit choice still wins.
        text = read(VIEWS, "roadmap.js")
        self.assertIn('return typeof saved === "boolean" ? saved : phase.state !== "done";', text)

    def test_approve_has_a_fixed_column_on_the_header_line(self):
        # R8.9: the header is name | Approve column; the stats span the row below.
        plan = read(CSS, "plan.css")
        self.assertIn(".lane-head { display: grid; grid-template-columns: minmax(0, 1fr) auto;", plan)
        self.assertIn(".lane-act { --rg: 6.5rem; }", plan)
        self.assertIn("grid-column: 1 / -1;", plan)

    def test_chevron_is_a_24_px_target(self):
        self.assertIn(".lane-caret { width: 24px;", read(CSS, "plan.css"))

    def test_up_and_down_keep_their_own_columns_on_phone(self):
        plan = read(CSS, "plan.css")
        self.assertIn(".rc-move { display: grid; }", plan)
        self.assertIn(".rc-move > .btn { width: 100%; margin: 0; }", plan)

    def test_up_and_down_are_disabled_at_the_ends(self):
        # R8.9 (already in place): the first card's Up and the last card's Down are disabled.
        text = read(VIEWS, "roadmap.js")
        self.assertIn('(pos === 0 ? " disabled" : "")', text)
        self.assertIn("(pos === count - 1 ? \" disabled\" : \"\")", text)


if __name__ == "__main__":
    unittest.main()
