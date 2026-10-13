"""Issues (issues.json): open, close and list. At most 200 open (open or doing); closed or wontfix issues beyond the
newest 100 move to issues-archive.jsonl. Every write runs under the directory lock and saves atomically."""

from roadmap.core.parsers import ISSUE_KINDS, ISSUE_OPEN, ISSUE_STATUSES, NOTE_MAX, TITLE_MAX
from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import records
from roadmap.store import jsonl, lock

FILE = "issues.json"
ARCHIVE = "issues-archive.jsonl"
OPEN_CAP = 200
CLOSED_KEEP = 100
TASKS_MAX = 5
CLOSED = ("closed", "wontfix")


def open_issue(data_dir, title, kind, sev=2, tasks=(), by="", note=None, now=None):
    """Open a new issue and return it. Refuses an unknown kind, a bad sev, more than 5 tasks, or a 201st open issue."""
    records.require_dir(data_dir)
    clean_title = records.text_field(title, "issue title", TITLE_MAX)
    if kind not in ISSUE_KINDS:
        raise RoadmapError("usage", "kind '" + str(kind) + "' is not valid (allowed: " + "|".join(ISSUE_KINDS) + ")",
                           EXIT_USAGE)
    if isinstance(sev, bool) or sev not in (1, 2, 3):
        raise RoadmapError("usage", "sev must be 1, 2 or 3", EXIT_USAGE)
    task_ids = [str(t).strip() for t in (tasks or ()) if str(t).strip()]
    if len(task_ids) > TASKS_MAX:
        raise RoadmapError("usage", "an issue links at most " + str(TASKS_MAX) + " tasks", EXIT_USAGE)
    clean_note = records.text_field(note, "issue note", NOTE_MAX, required=False) or None
    with lock.locked(data_dir):
        doc = records.load("issues", data_dir, FILE, "issues")
        if _open_count(doc["issues"]) >= OPEN_CAP:
            raise records.conflict("issues: " + str(OPEN_CAP) + " are open, the most allowed; close one first")
        archived = jsonl.read_objects(jsonl_path(data_dir))[0]
        issue = {"id": records.next_number("I", doc["issues"], archived), "title": clean_title, "kind": kind,
                 "sev": sev, "status": "open", "tasks": task_ids, "by": str(by or ""),
                 "created": records.now_iso(now), "closed": None, "note": clean_note}
        doc["issues"].append(issue)
        records.save("issues", data_dir, FILE, doc)
    return dict(issue)


def set_status(data_dir, issue_id, status, now=None):
    """Set an issue's status. Closing or wontfix stamps closed; reopening clears it. Returns the issue."""
    records.require_dir(data_dir)
    if status not in ISSUE_STATUSES:
        raise RoadmapError("usage", "status '" + str(status) + "' is not valid (allowed: "
                           + "|".join(ISSUE_STATUSES) + ")", EXIT_USAGE)
    with lock.locked(data_dir):
        doc = records.load("issues", data_dir, FILE, "issues")
        issue = _find(doc["issues"], issue_id)
        issue["status"] = status
        issue["closed"] = records.now_iso(now) if status in CLOSED else None
        moved = _archive_closed(data_dir, doc)
        records.save("issues", data_dir, FILE, doc)
    result = dict(issue)
    result["archived"] = moved
    return result


def close(data_dir, issue_id, now=None):
    return set_status(data_dir, issue_id, "closed", now)


def get(data_dir, issue_id):
    records.require_dir(data_dir)
    return dict(_find(records.load("issues", data_dir, FILE, "issues")["issues"], issue_id))


def list_issues(data_dir, include_closed=False):
    """Issues in file order: open and doing only, unless include_closed is true. Archived issues are not listed."""
    records.require_dir(data_dir)
    rows = records.load("issues", data_dir, FILE, "issues")["issues"]
    return [dict(i) for i in rows if include_closed or i.get("status") in ISSUE_OPEN]


def jsonl_path(data_dir):
    return records.file_of(data_dir, ARCHIVE)


def _open_count(items):
    return sum(1 for i in items if isinstance(i, dict) and i.get("status") in ISSUE_OPEN)


def _find(items, issue_id):
    for item in items:
        if isinstance(item, dict) and item.get("id") == issue_id:
            return item
    raise RoadmapError("not_found", "no issue " + str(issue_id), EXIT_NOT_FOUND)


def _archive_closed(data_dir, doc):
    """Move closed issues beyond the newest CLOSED_KEEP to the archive file. Archive first, then the caller saves."""
    closed = [i for i in doc["issues"] if isinstance(i, dict) and i.get("status") in CLOSED]
    if len(closed) <= CLOSED_KEEP:
        return 0
    newest_first = sorted(closed, key=lambda i: (i.get("closed") or i.get("created") or ""), reverse=True)
    doomed = newest_first[CLOSED_KEEP:]
    ids = {id(i) for i in doomed}
    for issue in doomed:
        jsonl.append_line(jsonl_path(data_dir), issue)
    doc["issues"] = [i for i in doc["issues"] if id(i) not in ids]
    return len(doomed)
