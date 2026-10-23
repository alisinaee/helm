"""Start queue (queue.json): tasks waiting to be started, at most 50 entries, oldest first."""

import threading

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import launcher, notify, presence, records
from roadmap.store import lock

FILE = "queue.json"
CAP = 50


def enqueue(data_dir, task, by="", now=None):
    """Add a task to the end of the queue. A task already queued, or a 51st entry, is a conflict."""
    records.require_dir(data_dir)
    task_id = str(task or "").strip()
    if not records.ID_OK.match(task_id):
        raise RoadmapError("usage", "queue entry '" + task_id + "' is not a task id", EXIT_USAGE)
    with lock.locked(data_dir):
        doc = records.load("queue", data_dir, FILE, "entries")
        if any(e.get("task") == task_id for e in doc["entries"]):
            raise records.conflict(task_id + " is already queued; not changed")
        if len(doc["entries"]) >= CAP:
            raise records.conflict("the queue holds " + str(CAP) + " entries, the most allowed; dequeue one first")
        entry = {"task": task_id, "by": str(by or ""), "at": records.now_iso(now)}
        doc["entries"].append(entry)
        records.save("queue", data_dir, FILE, doc)
    # outside the lock: the notification never holds up the queue (it never raises either)
    _notify_start(data_dir, task_id)
    return dict(entry)


def _launch_quietly(data_dir):
    """Run the opt-in launch. It never raises, and it runs off the caller's thread so the Start is not delayed."""
    try:
        launcher.maybe_launch(data_dir)
    except Exception:
        pass


def _spawn(target, arg):
    """Start target(arg) on a daemon thread. Tests replace this with a synchronous fake."""
    threading.Thread(target=target, args=(arg,), daemon=True).start()


def _notify_start(data_dir, task_id):
    """Show the Start notification, and when no session is open and the project opted in, launch one. Never raises."""
    try:
        idle = presence.state(data_dir) == presence.NONE

        def body(name):
            # the project name is in the title; the folder path stays in the GUI's Copy command
            if not idle:
                return "Start " + task_id + " queued. Open a Claude session or run: roadmap watch"
            return "Start " + task_id + " queued; no session open. Open a Claude session or run: roadmap watch"

        notify.notify_dir(data_dir, "start", "Start queued", body)
        if idle:
            _spawn(_launch_quietly, data_dir)
    except Exception:  # fail open: the queue entry is already saved
        pass


def dequeue(data_dir, task):
    """Remove a task from the queue. Returns True when it was there."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = records.load("queue", data_dir, FILE, "entries")
        kept = [e for e in doc["entries"] if e.get("task") != task]
        if len(kept) == len(doc["entries"]):
            return False
        doc["entries"] = kept
        records.save("queue", data_dir, FILE, doc)
    return True


def list_queue(data_dir):
    records.require_dir(data_dir)
    return [dict(e) for e in records.load("queue", data_dir, FILE, "entries")["entries"]]
