"""Budget and job changes: job done --tokens feeds the budget once per job id, job start --parent/--role, and
budget show (at most 8 lines). Includes the WP21 acceptance chain: job start, job done --tokens 20, budget show."""

from roadmap.services import budget, jobs
from tests.unit.test_cmd_support import CmdCase


class JobBudgetTests(CmdCase):
    def test_acceptance_chain_job_tokens_show_in_budget(self):
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)
        code, out, err = self.cli(["job", "done", "j1", "--tokens", "20"])
        self.assertEqual((code, out.strip()), (0, "j1 done"), err)
        code, out, err = self.cli(["budget", "show"])
        self.assertEqual(code, 0, err)
        self.assertIn("spent 20k; no project limit", out.splitlines())
        self.assertIn("models: haiku 20k", out.splitlines())

    def test_tokens_are_spent_once_per_job_id(self):
        self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.cli(["job", "done", "j1", "--tokens", "20"])
        code, out, err = self.cli(["job", "done", "j1", "--tokens", "20"])
        self.assertEqual(code, 4, err)
        self.assertEqual(budget.get(self.data)["spent"], {"P1.1": {"haiku": 20.0}})

    def test_the_budget_service_itself_is_idempotent_per_job_id(self):
        self.assertTrue(budget.record_job_spend(self.data, "j7", "P1.1", "sonnet", 12))
        self.assertFalse(budget.record_job_spend(self.data, "j7", "P1.1", "sonnet", 12))
        self.assertEqual(budget.get(self.data)["spent"]["P1.1"]["sonnet"], 12.0)

    def test_a_job_without_tokens_spends_nothing(self):
        self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.cli(["job", "done", "j1"])
        self.assertEqual(budget.get(self.data)["spent"], {})

    def test_parent_and_role_are_recorded(self):
        self.cli(["job", "start", "lead work", "opus", "P2.1"])
        code, out, err = self.cli(["job", "start", "helper", "haiku", "P1.1", "--parent", "j1", "--role", "worker"])
        self.assertEqual((code, out.strip()), (0, "j2"), err)
        rows = {j["id"]: j for j in jobs.list_jobs(self.data)}
        self.assertEqual((rows["j2"]["parent"], rows["j2"]["role"]), ("j1", "worker"))
        self.assertNotIn("parent", rows["j1"])

    def test_role_must_be_lead_or_worker_and_needs_a_parent(self):
        self.cli(["job", "start", "lead", "opus"])
        code, _, err = self.cli(["job", "start", "x", "haiku", "--parent", "j1", "--role", "boss"])
        self.assertEqual(code, 2)
        code, _, err = self.cli(["job", "start", "x", "haiku", "--role", "lead"])
        self.assertEqual(code, 2)
        self.assertIn("--role needs --parent", err)

    def test_unknown_parent_is_not_found(self):
        code, _, err = self.cli(["job", "start", "x", "haiku", "--parent", "j99", "--role", "lead"])
        self.assertEqual(code, 3)
        self.assertIn("j99", err)

    def test_budget_show_is_at_most_eight_lines_and_takes_a_phase(self):
        self.cli(["job", "start", "a", "haiku", "P1.1"])
        self.cli(["job", "done", "j1", "--tokens", "20"])
        self.cli(["job", "start", "b", "sonnet", "P2.1"])
        self.cli(["job", "done", "j2", "--tokens", "5.5"])
        code, out, err = self.cli(["budget", "show"])
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(out.splitlines()), 8)
        code, out, _ = self.cli(["budget", "show", "--phase", "P1"])
        self.assertLessEqual(len(out.splitlines()), 8)
        self.assertIn("P1: spent 20k, no limit", out.splitlines())
        self.assertIn("tasks: P1.1 20k", out.splitlines())

    def test_budget_show_json_envelope(self):
        code, body = self.envelope(["budget", "show"])
        self.assertEqual(code, 0)
        self.assertTrue(body["ok"])
        self.assertIn("lines", body["data"])
