"""System v2: which board (agent) tasks and Work items belong to which component (docs/SYSTEM-V2-SPEC.md section 3).

bind(mapped, commits, tasks, work, declared) -> {component id: {"board": [...], "work": [...], "progress": {...}}}.
Rules, all unioned: (1) tasks / work ids declared on the component in docs/system.json; (2) task ids in the subjects of
commits that touch the component's files; (3) tasks whose refs hold a `file:<path>` the component's globs match, or
whose title / note holds such a path, or the component id / name as a whole word (4+ characters); (4) Work items that
bind any of those tasks. Pure: no file or git access here.
"""

import re

from roadmap.services import system, systemheat

CAP = 40
MIN_WORD = 4
ORDER = {"doing": 0, "partial": 0, "todo": 1, "hold": 2, "done": 3}
PATH_RE = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+")


def _is_done(status):
    return str(status or "").lower() in ("done", "accepted")


def _words(comp):
    """Case-insensitive whole-word pattern for the component id and name (each 4+ characters), or None."""
    names = {n for n in (comp.get("id"), comp.get("name")) if isinstance(n, str) and len(n.strip()) >= MIN_WORD}
    if not names:
        return None
    alt = "|".join(re.escape(n.strip()) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"(?<![\w-])(?:" + alt + r")(?![\w-])", re.IGNORECASE)


def _paths_in(text):
    return PATH_RE.findall(text) if isinstance(text, str) else []


def _matches_globs(comp, paths):
    if not paths or not comp.get("files"):
        return False
    got, _ = system.assign_files(list(paths), [{"id": comp["id"], "files": comp["files"]}])
    return bool(got[comp["id"]])


def _progress(done, total):
    return {"done": done, "total": total, "pct": int(round(100.0 * done / total)) if total else 0}


def _board_row(task, work_of):
    return {"id": task["id"], "title": str(task.get("title") or "")[:120], "status": str(task.get("status") or "todo"),
            "phase": task.get("phase"), "model": task.get("model"), "work": work_of.get(task["id"])}


def _sorted_board(rows):
    return sorted(rows, key=lambda r: (ORDER.get(r["status"].lower(), 4), r["id"]))


def bind(mapped, commits, tasks, work, declared=None):
    """See the module text. mapped is system.load(); commits are systemheat.history()["commits"]; tasks are the
    tasks.json task dicts; work the work_svc.list_views() items; declared the raw docs/system.json object (or {}),
    used for explicit tasks / work lists the mapped components may not carry."""
    comps = [c for c in (mapped or {}).get("components", []) if isinstance(c, dict) and c.get("id")]
    task_by_id = {t["id"]: t for t in tasks or [] if isinstance(t, dict) and isinstance(t.get("id"), str)}
    work_by_id = {w["id"]: w for w in work or [] if isinstance(w, dict) and isinstance(w.get("id"), str)}
    work_of = {}
    for item in work_by_id.values():
        for tid in item.get("tasks") or []:
            work_of.setdefault(tid, item["id"])
    explicit = {}
    raw_comps = (declared or {}).get("components") if isinstance(declared, dict) else None
    for raw in raw_comps if isinstance(raw_comps, list) else []:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            explicit[raw["id"]] = raw
    commit_files = sorted({f for cm in commits or [] for f in cm.get("files") or []})
    assigned, _ = system.assign_files(commit_files, [{"id": c["id"], "files": c.get("files", [])} for c in comps])
    owner = {}
    for cid, paths in assigned.items():
        for p in paths:
            owner[p] = cid
    from_commits = {c["id"]: set() for c in comps}
    for cm in commits or []:
        ids = cm.get("tasks")
        if ids is None:
            ids = systemheat.TASK_RE.findall(cm.get("subject") or "")
        for cid in {owner[f] for f in cm.get("files") or [] if f in owner}:
            from_commits[cid].update(ids)
    texts = {}
    for tid, task in task_by_id.items():
        refs = [str(r)[5:] for r in task.get("refs") or [] if isinstance(r, str) and r.startswith("file:")]
        body = " ".join(str(task.get(k) or "") for k in ("title", "note"))
        texts[tid] = (refs + _paths_in(body), body)
    out = {}
    for comp in comps:
        cid = comp["id"]
        found = set()
        ex_tasks = list(comp.get("tasks") or []) + list((explicit.get(cid) or {}).get("tasks") or [])
        ex_work = list(comp.get("work") or []) + list((explicit.get(cid) or {}).get("work") or [])
        found.update(t for t in ex_tasks if isinstance(t, str) and t in task_by_id)
        found.update(t for t in from_commits[cid] if t in task_by_id)
        word = _words(comp)
        for tid, (paths, body) in texts.items():
            if tid in found:
                continue
            if _matches_globs(comp, paths) or (word is not None and word.search(body)):
                found.add(tid)
        board = _sorted_board([_board_row(task_by_id[t], work_of) for t in found])
        wids = []
        for wid in ex_work:
            if isinstance(wid, str) and wid in work_by_id and wid not in wids:
                wids.append(wid)
        for wid in sorted(w for w, item in work_by_id.items() if set(item.get("tasks") or []) & found):
            if wid not in wids:
                wids.append(wid)
        wrows = [{"id": w, "title": str(work_by_id[w].get("title") or "")[:120],
                  "status": str(work_by_id[w].get("status") or ""), "kind": work_by_id[w].get("kind")} for w in wids]
        if board:
            progress = _progress(sum(1 for r in board if _is_done(r["status"])), len(board))
        else:
            progress = _progress(sum(1 for r in wrows if _is_done(r["status"])), len(wrows))
        out[cid] = {"board": board[:CAP], "work": wrows[:CAP], "progress": progress}
    return out


def union(parts):
    """Merge the bound rows of several components (a container): union by id, same order and cap, progress over the
    union (board tasks, else Work items)."""
    board, work = {}, {}
    for part in parts:
        for row in part.get("board", []):
            board.setdefault(row["id"], row)
        for row in part.get("work", []):
            work.setdefault(row["id"], row)
    rows = _sorted_board(list(board.values()))
    wrows = sorted(work.values(), key=lambda r: r["id"])
    src = rows if rows else wrows
    return {"board": rows[:CAP], "work": wrows[:CAP],
            "progress": _progress(sum(1 for r in src if _is_done(r["status"])), len(src))}
