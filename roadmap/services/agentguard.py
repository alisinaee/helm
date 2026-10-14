"""Agent guard: ops that loosen control are refused from an agent's shell (any non-empty CLAUDECODE), or when the
source is agent.

A call is a person's browser click only when the HTTP layer proved it: the request had an Origin of this server and
Sec-Fetch-Site same-origin. The proof is kept in a thread-local flag set by browser_proven() for the one request, so
the process environment is never changed (another thread never sees a cleared CLAUDECODE). A local process can still
send those two headers itself; this is a speed bump against accidents, not a boundary against a malicious local
process (see docs/SECURITY.md, Known limits).

The refusal names `roadmap ask` as the next step, so the agent asks the person instead of changing the control state.
"""

import contextlib
import os
import sys
import threading

from roadmap.errors import EXIT_CONFLICT, RoadmapError

ENV = "CLAUDECODE"
ASK_NEXT = 'roadmap ask "<question>"'
# Env names that mark an agent's shell beyond CLAUDECODE (Claude Code's own, Cursor, agy/Antigravity, Codex).
AGENT_ENV_PREFIXES = ("CLAUDE_CODE_", "CURSOR_", "AGY_", "ANTIGRAVITY_", "CODEX_")
_TL = threading.local()


@contextlib.contextmanager
def browser_proven(proven):
    """Mark the calls this thread makes inside the block as a browser's (proven) or not. Restores the old mark after."""
    saved = getattr(_TL, "proven", False)
    _TL.proven = bool(proven)
    try:
        yield
    finally:
        _TL.proven = saved


def gui_proven():
    """True while this thread serves a request whose browser proof (Origin and Sec-Fetch-Site) checked out."""
    return getattr(_TL, "proven", False) is True


def is_agent(source=None, environ=None):
    """True when the call comes from an agent: source is agent, or the shell has a non-empty CLAUDECODE. A gui call
    with a browser proof on this thread is a person, whatever the environment says."""
    if source == "agent":
        return True
    if source == "gui" and gui_proven():
        return False
    environ = os.environ if environ is None else environ
    return str(environ.get(ENV, "")).strip() != ""


def source_name(environ=None):
    """The activity source of a CLI call: agent inside an agent's shell, otherwise cli."""
    return "agent" if is_agent(None, environ) else "cli"


def refuse_if_agent(op, source=None, environ=None):
    """Raise agent_refused (exit 4) when the call comes from an agent. Returns None otherwise."""
    if is_agent(source, environ):
        raise RoadmapError("agent_refused", op + " is refused from an agent; ask the person instead", EXIT_CONFLICT,
                           next=ASK_NEXT)


def agent_marked(environ=None):
    """True when the environment has an agent marker with a non-empty value: CLAUDECODE or a known agent prefix."""
    environ = os.environ if environ is None else environ
    for key, value in environ.items():
        if str(value).strip() == "":
            continue
        if key == ENV or str(key).startswith(AGENT_ENV_PREFIXES):
            return True
    return False


def _isatty(stream):
    try:
        return stream is not None and bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def person_context(source, environ=None, stdin=None, stdout=None):
    """True only when the call is provably the person's. That is a browser click with the same-origin proof (source
    gui), or an interactive terminal CLI (source cli, stdin and stdout are TTYs, no agent marker in the environment).
    An agent, the phone, a bare non-TTY cli (a Cursor, agy or script shell) and anything unproven are not the person."""
    if source == "gui":
        return gui_proven()
    if source != "cli" or agent_marked(environ):
        return False
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    return _isatty(stdin) and _isatty(stdout)
