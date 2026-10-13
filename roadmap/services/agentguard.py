"""Agent guard: ops that loosen control are refused from an agent's shell (any non-empty CLAUDECODE), or when the
source is agent.

The refusal names `roadmap ask` as the next step, so the agent asks the person instead of changing the control state.
"""

import os

from roadmap.errors import EXIT_CONFLICT, RoadmapError

ENV = "CLAUDECODE"
ASK_NEXT = 'roadmap ask "<question>"'


def is_agent(source=None, environ=None):
    """True when the call comes from an agent: source is agent, or the shell has a non-empty CLAUDECODE."""
    environ = os.environ if environ is None else environ
    return source == "agent" or str(environ.get(ENV, "")).strip() != ""


def source_name(environ=None):
    """The activity source of a CLI call: agent inside an agent's shell, otherwise cli."""
    return "agent" if is_agent(None, environ) else "cli"


def refuse_if_agent(op, source=None, environ=None):
    """Raise agent_refused (exit 4) when the call comes from an agent. Returns None otherwise."""
    if is_agent(source, environ):
        raise RoadmapError("agent_refused", op + " is refused from an agent; ask the person instead", EXIT_CONFLICT,
                           next=ASK_NEXT)
