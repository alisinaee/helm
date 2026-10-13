"""Agent guard: refused from an agent shell (CLAUDECODE=1) or with source agent, with a next line that points at ask."""

import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, RoadmapError
from roadmap.services import agentguard


class AgentGuardTests(unittest.TestCase):
    def test_plain_shell_is_not_an_agent(self):
        self.assertFalse(agentguard.is_agent(None, {}))
        self.assertEqual(agentguard.source_name({}), "cli")
        agentguard.refuse_if_agent("control.resume", None, {})  # no error

    def test_claudecode_one_is_an_agent_and_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            agentguard.refuse_if_agent("control.resume", None, {"CLAUDECODE": "1"})
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(ctx.exception.next, 'roadmap ask "<question>"')
        self.assertIn("control.resume", ctx.exception.message)

    def test_other_claudecode_values_are_not_an_agent(self):
        self.assertFalse(agentguard.is_agent(None, {"CLAUDECODE": "0"}))
        self.assertFalse(agentguard.is_agent(None, {"CLAUDECODE": ""}))

    def test_source_agent_is_refused_without_the_env(self):
        with self.assertRaises(RoadmapError):
            agentguard.refuse_if_agent("limit.set", "agent", {})

    def test_default_environment_is_read_from_os_environ(self):
        with mock.patch.dict("os.environ", {"CLAUDECODE": "1"}):
            self.assertTrue(agentguard.is_agent())
            self.assertEqual(agentguard.source_name(), "agent")
