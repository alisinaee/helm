"""Git write ops (GIT-SPEC step 3): git.commit, git.push, git.branch, git.switch and git.revert, plus two internal
inverses that undo runs (git.uncommit, git.branch.drop). Each op runs through commands.run, so it is validated, adds
one activity line and stores its inverse where one exists.

Guards (roadmap/services/git.py does the running; this module decides):
- commit: explicit paths only (git add -- paths, then git commit --only -- paths; never -A). An empty list is refused.
  A path that a different running job owns (its files in docs/jobs.json) is refused. A detached HEAD, an unfinished
  merge or rebase, and a busy .git/index.lock are refused.
- push: never forced. Agents need the project policy (docs/git.json, push: off | after-check | task-done) to allow
  it, never push a protected branch, and after-check needs checked true (the caller ran a green check). The person
  may push any branch.
- branch: an agent creates only agent/<name>. Undo drops the branch when it has no new commits and is not current.
- switch: clean tree only (no staged, changed, untracked or conflicted files), local branches only. Undo switches back.
- revert: person only (agentguard.refuse_if_agent). A new commit; undo is the same soft reset as commit.
Never offered: discard, reset --hard, clean, path checkout, amend, merge, rebase, force push.
"""

import fnmatch
import os
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import agentguard, commands, jobs, records
from roadmap.services import head as head_svc
from roadmap.services import git
from roadmap.store import config as config_store
from roadmap.store import lock, schema

POLICY_FILE = "git.json"
PUSH_MODES = ("off", "after-check", "task-done")
DEFAULT_POLICY = {"push": "off", "protected": ["main", "master", "release/*"]}
PROTECTED_MAX = 50
PATHS_MAX = 500
MESSAGE_MAX = 4000
TASK_ID = re.compile(r"R\d+(?:\.\d+)*")
JOB_ID = re.compile(r"j\d+")
AGENT_BRANCH = "agent/"
NEXT_STATUS = "roadmap git status"


# ---------------------------------------------------------------- shared helpers

def _usage(message, next_cmd=NEXT_STATUS):
    return RoadmapError("usage", message, EXIT_USAGE, next=next_cmd)


def _conflict(message, next_cmd=NEXT_STATUS):
    return RoadmapError("conflict", message, EXIT_CONFLICT, next=next_cmd)


def _is_agent():
    """True when the op runs for an agent (activity source agent, or an agent's shell). The person's GUI and a
    plain terminal are not agents."""
    return agentguard.is_agent(commands.current_source())


def _project_path(data_dir):
    """The registered project path whose data folder is data_dir (the same match cmdops uses)."""
    for entry in config_store.list_projects():
        project = config_store.get_project(entry["id"])
        if jobs.data_dir_of(project) == data_dir:
            return project["path"]
    raise RoadmapError("not_found", "no registered project for this data folder", EXIT_NOT_FOUND)


def _root(data_dir):
    """The project's repo root after git.repo_root's checks (canonical path, its own repo, else Not a git repo)."""
    return git.repo_root(_project_path(data_dir))


def _write(root, args):
    """Run one write git command with the write timeout and normal locks."""
    return git.run(root, args, timeout=git.WRITE_TIMEOUT_S, optional_locks=False)


def _head(root):
    return git.run(root, ["rev-parse", "--verify", "HEAD^{commit}"]).strip()


def _ref_exists(root, ref):
    """True when a full ref exists. A missing ref is a normal answer here, not an error."""
    rc, _, _ = git._git(root, ["rev-parse", "--verify", "--quiet", ref], git.READ_TIMEOUT_S)
    return rc == 0


def _clean_tree(st, root, data_dir):
    """No staged, changed, untracked or conflicted file. The roadmap data folder (docs/ by default) is written by
    every roadmap command, so its changes do not count; git switch still refuses a switch that would overwrite them."""
    rel = os.path.relpath(data_dir, root)
    prefix = "" if rel in (".", "") or rel.startswith("..") else rel.replace(os.sep, "/") + "/"

    def mine(path):
        return not prefix or not path.startswith(prefix)

    rows = [r["path"] for r in st["staged"] + st["changed"] if mine(r["path"])]
    untracked = [p for p in st["untracked"] if mine(p)]
    return not (rows or untracked or st["conflicts"])


def _writable(root, what):
    """Refuse a commit-like write on a detached HEAD or during a merge or rebase."""
    st = git.read_status(root)
    if st["in_progress"]:
        raise _conflict(what + " refused: a " + st["in_progress"] + " is unfinished; finish it in a terminal",
                        "roadmap git status")
    if st["detached"]:
        raise _conflict(what + " refused: detached HEAD; check out a branch first", "roadmap git branch")
    return st


def _policy(data_dir):
    """The project's git policy from docs/git.json. A missing file gives the defaults (push off)."""
    path = records.file_of(data_dir, POLICY_FILE)
    data, error = schema.read_data("git", path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    if data is None:
        return {"push": DEFAULT_POLICY["push"], "protected": list(DEFAULT_POLICY["protected"])}
    mode = data.get("push", DEFAULT_POLICY["push"])
    protected = data.get("protected", DEFAULT_POLICY["protected"])
    if mode not in PUSH_MODES:
        raise RoadmapError("invalid_data", "git.json push must be one of " + "|".join(PUSH_MODES), EXIT_INVALID_DATA)
    if (not isinstance(protected, list) or len(protected) > PROTECTED_MAX
            or not all(isinstance(p, str) and p for p in protected)):
        raise RoadmapError("invalid_data", "git.json protected must be a list of branch names or patterns",
                           EXIT_INVALID_DATA)
    return {"push": mode, "protected": protected}


def _is_protected(branch, patterns):
    return any(fnmatch.fnmatchcase(branch, pattern) for pattern in patterns)


def _opt_text_id(a, key, pattern, label):
    value = a.get(key)
    if value is None or value == "":
        return None
    text = str(value)
    if not pattern.fullmatch(text):
        raise _usage(label + " '" + text[:40] + "' is not valid", "roadmap git log")
    return text


def _opt_bool(a, key):
    value = a.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _usage(key + " must be true or false")
    return value


def _sha_arg(a, key="sha"):
    return git.valid_sha(a.get(key))


# ---------------------------------------------------------------- git.commit

def _check_commit(a):
    paths = a.get("paths")
    if not isinstance(paths, (list, tuple)) or not paths:
        raise _usage("commit needs at least one path; commit never takes everything (-A)", "roadmap git status")
    if len(paths) > PATHS_MAX:
        raise _usage("commit takes at most " + str(PATHS_MAX) + " paths")
    message = a.get("message")
    if not isinstance(message, str) or not message.strip():
        raise _usage("commit message is empty (allowed: text)")
    message = message.strip()
    if len(message) > MESSAGE_MAX or "\0" in message:
        raise _usage("commit message is over " + str(MESSAGE_MAX) + " characters or has a NUL byte")
    task = _opt_text_id(a, "task", TASK_ID, "task")
    job = _opt_text_id(a, "job", JOB_ID, "job")
    return {"paths": [str(p) for p in paths], "message": message, "task": task, "job": job}


def _message_with_trailers(message, task, job):
    lines = []
    if task and not git.TASK_TRAILER.search(message):
        lines.append("Task: " + task)
    if job and not git.JOB_TRAILER.search(message):
        lines.append("Job: " + job)
    return message if not lines else message + "\n\n" + "\n".join(lines)


def _owners(data_dir):
    """Path -> id of the running job that owns it (its files list in docs/jobs.json). Jobs without files own nothing."""
    owners = {}
    for job in jobs.list_jobs(data_dir):
        if job.get("status") != "running":
            continue
        for name in job.get("files") or []:
            if isinstance(name, str):
                owners.setdefault(name, job.get("id"))
    return owners


_PATH_BAD = set("*?[]{}")


def _commit_path(root, path):
    """One explicit repo-relative file: no glob character, no pathspec magic (leading ':'), no '--', no '..', no
    absolute path, and it resolves to a real file inside the repo (or a tracked file, so a deletion can be committed)."""
    text = str(path or "")
    if text.startswith(":") or text == "--" or _PATH_BAD & set(text):
        raise RoadmapError("usage", "path '" + text[:200] + "' must be an explicit file, not a glob or pathspec",
                           EXIT_USAGE)
    norm = git.valid_rel_path(root, text)
    if not os.path.isfile(os.path.join(root, norm)):
        rc, out, _ = git._git(root, ["--literal-pathspecs", "ls-files", "--", norm], git.READ_TIMEOUT_S)
        if rc != 0 or not out.strip():
            raise RoadmapError("usage", "path '" + text[:200] + "' is not a file in the repo", EXIT_USAGE)
    return norm


MSG_TASK_ID = re.compile(r"\bR\d+\.\d+\b")


def bind_message_commit(data_dir, sha, message, task=None):
    """Bind a commit to the known tasks its message names (R<n>.<n>) and to their running jobs, then fold the asks
    whose tasks are all done. Returns the bound task ids, which the caller reports as done candidates."""
    ids = set(MSG_TASK_ID.findall(message or ""))
    if task:
        ids.add(task)
    bound = jobs.bind_commit(data_dir, sha, sorted(ids)) if ids else []
    if bound:
        head_svc.fold_asks(data_dir)
    return bound


def _h_commit(data_dir, a, now):
    root = _root(data_dir)
    paths = sorted(set(_commit_path(root, p) for p in a["paths"]))
    _writable(root, "commit")
    owners = _owners(data_dir)
    for path in paths:
        owner = owners.get(path)
        if owner and owner != a["job"]:
            raise _conflict("commit refused: " + path + " belongs to running job " + owner,
                            "roadmap git status")
    text = _message_with_trailers(a["message"], a["task"], a["job"])
    with lock.locked(data_dir):
        git.check_index_free(root)
        _write(root, ["add", "--"] + paths)
        _write(root, ["commit", "--only", "-m", text, "--"] + paths)
    sha = _head(root)
    candidates = bind_message_commit(data_dir, sha, a["message"], a["task"])
    data = {"sha": sha, "files": len(paths), "task": a["task"], "job": a["job"], "candidates": candidates}
    summary = "commit " + sha[:7] + " " + str(len(paths)) + " file(s)"
    if candidates:
        summary += "; done candidate: " + ", ".join(candidates)
    return data, summary, {"op": "git.uncommit", "args": {"sha": sha}}


# ---------------------------------------------------------------- git.uncommit (internal, undo of commit and revert)

def _check_uncommit(a):
    return {"sha": _sha_arg(a)}


def _pushed(root, sha):
    """True when sha is already in the upstream branch. No upstream means not pushed."""
    rc, out, _ = git._git(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], git.READ_TIMEOUT_S)
    upstream = out.decode("utf-8", "replace").strip()
    if rc != 0 or not upstream:
        return False
    rc, _, _ = git._git(root, ["merge-base", "--is-ancestor", sha, upstream], git.READ_TIMEOUT_S)
    return rc == 0


def _h_uncommit(data_dir, a, now):
    """Soft reset HEAD back one commit, only while HEAD is that commit and it is not pushed. Never a hard reset."""
    root = _root(data_dir)
    with lock.locked(data_dir):
        git.check_index_free(root)
        head = _head(root)
        full = git.run(root, ["rev-parse", "--verify", "--quiet", a["sha"] + "^{commit}"]).strip()
        if full != head:
            raise _conflict("undo refused: that commit is no longer HEAD", "roadmap git log")
        if _pushed(root, head):
            raise _conflict("undo refused: the commit is pushed (no rewrite of pushed history)", "roadmap git log")
        if not _ref_exists(root, "HEAD^"):
            raise _conflict("undo refused: the commit has no parent", "roadmap git log")
        _write(root, ["reset", "--soft", "HEAD^"])
    return {"sha": head, "undone": True}, "uncommit " + head[:7], None


# ---------------------------------------------------------------- git.revert (person only)

def _check_revert(a):
    return {"sha": _sha_arg(a)}


def _h_revert(data_dir, a, now):
    agentguard.refuse_if_agent("git.revert", commands.current_source())
    root = _root(data_dir)
    _writable(root, "revert")
    full = git.run(root, ["rev-parse", "--verify", "--quiet", a["sha"] + "^{commit}"]).strip()
    with lock.locked(data_dir):
        git.check_index_free(root)
        _write(root, ["revert", "--no-edit", full])
    new = _head(root)
    summary = "revert " + full[:7] + " -> " + new[:7]
    return {"sha": new, "reverted": full}, summary, {"op": "git.uncommit", "args": {"sha": new}}


# ---------------------------------------------------------------- git.push

def _check_push(a):
    remote = _opt_text_id(a, "remote", re.compile(r"[A-Za-z0-9._-]{1,60}"), "remote")
    return {"remote": remote, "checked": _opt_bool(a, "checked")}


def _remote_for(root, branch, given):
    if given:
        return given
    rc, out, _ = git._git(root, ["config", "--get", "branch." + branch + ".remote"], git.READ_TIMEOUT_S)
    name = out.decode("utf-8", "replace").strip()
    if rc == 0 and name:
        return name
    return "origin"


def _h_push(data_dir, a, now):
    root = _root(data_dir)
    st = git.read_status(root)
    if st["in_progress"]:
        raise _conflict("push refused: a " + st["in_progress"] + " is unfinished", "roadmap git status")
    if st["detached"] or not st["branch"]:
        raise _conflict("push refused: detached HEAD; check out a branch first", "roadmap git branch")
    branch = st["branch"]
    if not git.valid_ref(branch):  # a branch name the ref rules would never accept
        raise _usage("branch name is not valid")
    policy = _policy(data_dir)
    if _is_agent():
        if policy["push"] == "off":
            raise RoadmapError("forbidden", "push is off for this project (docs/git.json); ask the person",
                               EXIT_CONFLICT, next='roadmap ask "push ' + branch + '?"')
        if _is_protected(branch, policy["protected"]):
            raise RoadmapError("forbidden", "branch " + branch + " is protected; the person pushes it",
                               EXIT_CONFLICT, next='roadmap ask "push ' + branch + '?"')
        if policy["push"] == "after-check" and not a["checked"]:
            raise RoadmapError("forbidden", "after-check push needs a green make check (checked true)",
                               EXIT_CONFLICT, next="make check")
    remote = git.valid_ref(_remote_for(root, branch, a["remote"]))
    ref = "refs/heads/" + branch
    git.run(root, ["push", remote, ref + ":" + ref], timeout=git.PUSH_TIMEOUT_S, optional_locks=False)
    return {"remote": remote, "branch": branch}, "push " + branch + " to " + remote, None


# ---------------------------------------------------------------- git.branch (create; undo drops)

def _check_branch(a):
    return {"name": git.valid_ref(a.get("name"))}


def _h_branch(data_dir, a, now):
    root = _root(data_dir)
    name = a["name"]
    if _is_agent() and not name.startswith(AGENT_BRANCH):
        raise RoadmapError("forbidden", "agents create only " + AGENT_BRANCH + "<task> branches", EXIT_CONFLICT,
                           next='roadmap git branch new ' + AGENT_BRANCH + '<task>')
    sha = _head(root)
    with lock.locked(data_dir):
        git.check_index_free(root)
        _write(root, ["branch", name, sha])
    return {"name": name, "sha": sha}, "branch " + name, {"op": "git.branch.drop",
                                                          "args": {"name": name, "sha": sha}}


# ---------------------------------------------------------------- git.branch.drop (internal, undo of branch)

def _check_drop(a):
    return {"name": git.valid_ref(a.get("name")), "sha": _sha_arg(a)}


def _h_drop(data_dir, a, now):
    root = _root(data_dir)
    if git.read_status(root)["branch"] == a["name"]:
        raise _conflict("undo refused: " + a["name"] + " is the current branch", "roadmap git branch")
    ref = "refs/heads/" + a["name"]
    if not _ref_exists(root, ref):
        raise _conflict("undo refused: branch " + a["name"] + " is already gone", "roadmap git branch")
    tip = git.run(root, ["rev-parse", "--verify", ref]).strip()
    if tip != a["sha"]:
        raise _conflict("undo refused: " + a["name"] + " has new commits", "roadmap git log")
    with lock.locked(data_dir):
        git.check_index_free(root)
        _write(root, ["branch", "-D", a["name"]])
    return {"name": a["name"], "dropped": True}, "drop branch " + a["name"], None


# ---------------------------------------------------------------- git.switch

def _check_switch(a):
    return {"name": git.valid_ref(a.get("name"))}


def _h_switch(data_dir, a, now):
    root = _root(data_dir)
    st = git.read_status(root)
    if st["in_progress"]:
        raise _conflict("switch refused: a " + st["in_progress"] + " is unfinished", "roadmap git status")
    if not _clean_tree(st, root, data_dir):
        raise _conflict("switch refused: the working tree has changes; commit or stash them first",
                        "roadmap git status")
    prior = st["branch"]
    name = a["name"]
    if not _ref_exists(root, "refs/heads/" + name):
        raise RoadmapError("not_found", "no local branch " + name, EXIT_NOT_FOUND, next="roadmap git branch")
    if name == prior:
        return {"name": name, "changed": False}, "switch " + name + " (already here)", None
    with lock.locked(data_dir):
        git.check_index_free(root)
        _write(root, ["switch", name])
    inverse = {"op": "git.switch", "args": {"name": prior}} if prior else None
    return {"name": name, "changed": True, "was": prior}, "switch " + name, inverse


# ---------------------------------------------------------------- registry

def _register(name, check, handler, public=True):
    commands.OPS[name] = commands._Op(check, handler, public=public)


_register("git.commit", _check_commit, _h_commit)
_register("git.push", _check_push, _h_push)
_register("git.branch", _check_branch, _h_branch)
_register("git.switch", _check_switch, _h_switch)
_register("git.revert", _check_revert, _h_revert)
_register("git.uncommit", _check_uncommit, _h_uncommit, public=False)
_register("git.branch.drop", _check_drop, _h_drop, public=False)
