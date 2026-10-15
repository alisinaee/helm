"""Rule proposals (R7.103): propose (agents may), accept and reject (person only), duplicates against the rules and the
proposals, accept through the add path, the snapshot's rule_state_map, and the commands ops."""

import os
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import commands, rules
from roadmap.core import snapshot
from tests.unit.test_control_support import ControlCase

AGENT = {"CLAUDECODE": "1"}


class ProposalCase(ControlCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.docs, "rules.txt"), "w", encoding="utf-8") as fh:
            fh.write("R1 all do | Test first\n")

    def rules_text(self):
        with open(os.path.join(self.docs, "rules.txt"), encoding="utf-8") as fh:
            return fh.read()


class ProposeTests(ProposalCase):
    def test_propose_stores_an_open_proposal_with_sources(self):
        row = rules.propose(self.docs, "Keep small things as context", sources=["h12", "H40", "H12"])
        self.assertEqual(row["id"], "RP1")
        self.assertFalse(row["duplicate"])
        self.assertEqual(row["sources"], ["H12", "H40"])
        self.assertEqual(row["status"], "proposed")
        self.assertEqual([p["id"] for p in rules.open_proposals(self.docs)], ["RP1"])
        second = rules.propose(self.docs, "Ask before a paid step", sources=["H3"])
        self.assertEqual(second["id"], "RP2")

    def test_agent_may_propose(self):
        with mock.patch.dict(os.environ, AGENT):
            row = rules.propose(self.docs, "Check the diff before commit", sources=["H7"])
        self.assertEqual(row["id"], "RP1")

    def test_duplicates_of_a_rule_or_a_proposal_return_the_existing_id(self):
        rule_dup = rules.propose(self.docs, "test  FIRST!", sources=["H1"])
        self.assertEqual((rule_dup["id"], rule_dup["duplicate"], rule_dup["of"]), ("R1", True, "rule"))
        rules.propose(self.docs, "Keep small things as context", sources=["H2"])
        prop_dup = rules.propose(self.docs, "keep small things as context.", sources=["H9"])
        self.assertEqual((prop_dup["id"], prop_dup["of"]), ("RP1", "proposal"))
        self.assertEqual(len(rules.proposals(self.docs)), 1)

    def test_bad_source_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            rules.propose(self.docs, "Something", sources=["X9"])
        self.assertEqual(ctx.exception.exit, 2)

    def test_empty_text_is_refused(self):
        with self.assertRaises(RoadmapError):
            rules.propose(self.docs, "   ", sources=[])


class DecisionTests(ProposalCase):
    def test_accept_appends_to_rules_and_records_the_rule_id(self):
        rules.propose(self.docs, "Keep small things as context", sources=["H12"])
        row = rules.accept(self.docs, "rp1", edited_text="Keep small things as context only")
        self.assertEqual(row["status"], "accepted")
        self.assertEqual(row["rule"], "R2")
        self.assertIn("R2 all do | Keep small things as context only", self.rules_text())
        self.assertEqual(rules.open_proposals(self.docs), [])
        with self.assertRaises(RoadmapError) as ctx:
            rules.accept(self.docs, "RP1")
        self.assertEqual(ctx.exception.code, "conflict")

    def test_accept_and_reject_are_refused_from_an_agent(self):
        rules.propose(self.docs, "Keep small things as context", sources=["H12"])
        with mock.patch.dict(os.environ, AGENT):
            with self.assertRaises(RoadmapError) as ctx:
                rules.accept(self.docs, "RP1")
            self.assertEqual(ctx.exception.code, "agent_refused")
            with self.assertRaises(RoadmapError) as ctx:
                rules.reject(self.docs, "RP1")
            self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(rules.open_proposals(self.docs)[0]["id"], "RP1")
        self.assertNotIn("Keep small", self.rules_text())

    def test_reject_and_merge_set_the_status(self):
        rules.propose(self.docs, "Keep small things as context", sources=["H12"])
        rules.propose(self.docs, "Ask before a paid step", sources=["H3"])
        self.assertEqual(rules.reject(self.docs, "RP1")["status"], "rejected")
        merged = rules.reject(self.docs, "RP2", merged_into="R1")
        self.assertEqual((merged["status"], merged["merged_into"]), ("merged", "R1"))
        self.assertEqual(rules.open_proposals(self.docs), [])

    def test_missing_proposal_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            rules.accept(self.docs, "RP9")
        self.assertEqual(ctx.exception.code, "not_found")


class SnapshotStateTests(ProposalCase):
    def test_rule_state_follows_the_proposals(self):
        state = snapshot.rule_state_map([
            {"status": "accepted", "sources": ["H1"]},
            {"status": "proposed", "sources": ["H1", "H2"]},
            {"status": "rejected", "sources": ["H3", "H2"]},
            {"status": "merged", "sources": ["H4"]},
        ])
        self.assertEqual(state, {"H1": "in rules", "H2": "proposed", "H3": "kept as context",
                                 "H4": "kept as context"})
        self.assertEqual(snapshot.rule_state_map(None), {})


class CommandOpTests(ProposalCase):
    def op(self, name, args, source="gui"):
        return commands.run(name, args, source, self.docs)

    def test_propose_op_is_allowed_for_agents(self):
        out = self.op("rules.propose", {"text": "Check the diff", "sources": ["H5"]}, source="agent")
        self.assertEqual(out["data"]["id"], "RP1")

    def test_accept_and_reject_ops_are_person_only_and_refused_over_phone(self):
        self.op("rules.propose", {"text": "Check the diff", "sources": ["H5"]}, source="agent")
        with self.assertRaises(RoadmapError):
            self.op("rules.accept", {"id": "RP1"}, source="agent")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("rules.reject", {"id": "RP1"}, source="phone")
        self.assertEqual(ctx.exception.code, "forbidden")
        out = self.op("rules.accept", {"id": "RP1"}, source="cli")
        self.assertEqual(out["data"]["rule"], "R2")
