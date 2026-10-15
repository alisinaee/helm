"""Status roll-up for Work items (docs/WORK-MODEL.md section 2). Pure: no I/O, stdlib only.

Stored state is only the person's intent: Backlog and Won't do. Everything else is derived from the agent tasks.
Done is reached only through the person's accept (`person_accepted`). Legacy stored "done" migrates to Done.
"""

from typing import Any, Iterable, Mapping

BACKLOG = "Backlog"
TODO = "Todo"
DOING = "Doing"
REVIEW = "Review"
DONE = "Done"
WONT_DO = "Won't do"

BADGE_NEEDS_YOU = "needs-you"
BADGE_BLOCKED = "blocked"
BADGE_RUNNING = "running"

_CANCELLED = {"cancelled", "canceled"}
_STARTED = {"claimed", "running", "verify", "failed"}
_RUNNING = {"claimed", "running", "verify"}
_CLOSED_ISSUE = {"done", "wontfix", "won't do"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def rollup(work_item: Mapping[str, Any], agent_tasks: Iterable[Mapping[str, Any]],
           person_accepted: bool, now: Any = None) -> dict:
    """Return {status, badges, progress: {done, total}} for one Work item.

    work_item: {state, reopened?, blocked_by?: [{state}]}. state is "backlog", "wontfix" or "done" (legacy).
    agent_tasks: [{state}] with states todo, claimed, running, verify, done, failed, needs-you, cancelled.
    person_accepted: True once the person ran `work accept` (stored accepted ts).
    now: accepted for signature stability; the roll-up does not depend on time.
    """
    raw = [_norm(t.get("state")) for t in agent_tasks]
    tasks = [s for s in raw if s not in _CANCELLED]
    total = len(tasks)
    done = tasks.count("done")
    open_count = total - done
    stored = _norm(work_item.get("state"))

    if stored == "backlog":
        status = BACKLOG
    elif stored in ("wontfix", "won't do"):
        status = WONT_DO
    elif stored == "done":
        status = DONE
    elif person_accepted:
        status = DONE if open_count == 0 else DOING
    elif work_item.get("reopened"):
        status = DOING
    elif total and open_count == 0:
        status = REVIEW
    elif any(s in _STARTED for s in tasks) or (done and open_count):
        status = DOING
    else:
        status = TODO

    badges = []
    if "needs-you" in raw:
        badges.append(BADGE_NEEDS_YOU)
    if any(_norm(i.get("state")) not in _CLOSED_ISSUE for i in work_item.get("blocked_by") or ()):
        badges.append(BADGE_BLOCKED)
    if any(s in _RUNNING for s in tasks):
        badges.append(BADGE_RUNNING)
    return {"status": status, "badges": badges, "progress": {"done": done, "total": total}}
