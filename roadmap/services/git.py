"""Git core (GIT-SPEC step 1): a safe read runner for one registered project, input validation, output parsers,
redaction and caps. Pure parsers take text; the runner is the only place that starts git.

Rules kept here: argv is a list built by us (shell=False); the cwd is the project path and must be its own canonical
repo root; the caller's GIT_* environment is dropped; reads never write the index (GIT_OPTIONAL_LOCKS=0), never run a
fsmonitor hook or a credential helper; output is capped at 2 MB (the child is killed past the cap) and stderr cut to
400 characters; remote URL passwords and tokens are redacted.
"""

import fnmatch
import math
import os
import re
import shutil
import signal
import subprocess
import threading

from roadmap.errors import EXIT_CONFLICT, EXIT_EXTERNAL, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError

READ_TIMEOUT_S = 5
WRITE_TIMEOUT_S = 30
PUSH_TIMEOUT_S = 60
STDOUT_CAP = 2 * 1024 * 1024
STDERR_CUT = 400
STDERR_KEEP = 64 * 1024
RC_TIMEOUT = 124
RC_TOO_BIG = 125
JOIN_GRACE_S = 1
DIFF_FILE_BYTES = 200 * 1024
DIFF_FILE_LINES = 2000
DIFF_RESPONSE_BYTES = 1024 * 1024
BIG_FILE_BYTES = 1024 * 1024
LOG_MAX = 100
# Fields end in NUL. Git never writes NUL inside a commit, so a message cannot shift or forge a row.
LOG_FORMAT = "%H%x00%P%x00%an%x00%at%x00%s%x00%B%x00"

REF_OK = re.compile(r"[A-Za-z0-9._/-]{1,100}")
SHA_OK = re.compile(r"[0-9a-fA-F]{7,40}")
TASK_TRAILER = re.compile(r"^Task: (R\d+(?:\.\d+)*)\s*$", re.MULTILINE)
JOB_TRAILER = re.compile(r"^Job: (j\d+)\s*$", re.MULTILINE)
# Any scheme, any case; the userinfo runs to the last '@' before the host, so 'user@name:pw@host' is fully hidden.
URL_SECRET = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s]*@")
TRACK_AHEAD = re.compile(r"ahead (\d+)")
TRACK_BEHIND = re.compile(r"behind (\d+)")
SECRET_NAMES = (".env*", "*.pem", "*key*", "id_*")
# Every GIT_* variable (dirs, exec and ssh helpers, traces, askpass, lazy fetch) is dropped; SSH_ASKPASS too.
GIT_READ_FLAGS = ["-c", "core.fsmonitor=false", "-c", "credential.helper="]
RECORD = "\x1e"
FIELD = "\x1f"

_GIT = None


def git_path():
    """The git binary, resolved once. A missing git is an external error, not a crash."""
    global _GIT
    if _GIT is None:
        found = shutil.which("git")
        if not found:
            raise RoadmapError("git_missing", "git is not installed or not on PATH", EXIT_EXTERNAL)
        _GIT = found
    return _GIT


def redact(text):
    """Hide the user and password of any URL with a scheme, e.g. https://***@host/repo."""
    return URL_SECRET.sub(r"\1***@", text or "")


def valid_ref(name):
    """A branch or ref name we accept: the check-ref-format rules we need, no leading dash, at most 100 characters."""
    text = str(name or "")
    if not REF_OK.fullmatch(text) or text.startswith("-") or text.startswith("/") or text.endswith("/"):
        raise RoadmapError("usage", "ref '" + text[:100] + "' is not a valid branch or ref name", EXIT_USAGE)
    if ".." in text or "//" in text or text.endswith(".lock") or text.endswith("."):
        raise RoadmapError("usage", "ref '" + text + "' is not a valid branch or ref name", EXIT_USAGE)
    if any(part.startswith(".") for part in text.split("/")):
        raise RoadmapError("usage", "ref '" + text + "' is not a valid branch or ref name", EXIT_USAGE)
    return text


def valid_sha(value):
    """A commit id: 7 to 40 hex characters."""
    text = str(value or "")
    if not SHA_OK.fullmatch(text):
        raise RoadmapError("usage", "'" + text[:40] + "' is not a commit id (7-40 hex characters)", EXIT_USAGE)
    return text


def valid_rel_path(project, path):
    """A path relative to the project: no absolute start, no leading '-' (it would read as a git option), no NUL or
    line break, no '..', and its real location stays inside the project (a symlink cannot point out). Returns the
    normalized relative path."""
    text = str(path or "")
    if not text or "\0" in text or "\n" in text or "\r" in text or text.startswith("-") or os.path.isabs(text):
        raise RoadmapError("usage", "path '" + text[:200] + "' must be a plain relative path", EXIT_USAGE)
    # Pathspec magic (':(glob)', ':!', ':/') and glob characters would match other files; a file name needs neither.
    if text.startswith(":") or any(ch in text for ch in "*?[]"):
        raise RoadmapError("usage", "path '" + text[:200] + "' must be a literal file path, not a glob or pathspec",
                           EXIT_USAGE)
    norm = os.path.normpath(text)
    if norm in (".", "") or norm.startswith("..") or ".." in norm.split(os.sep):
        raise RoadmapError("usage", "path '" + text[:200] + "' must stay inside the project", EXIT_USAGE)
    root = os.path.realpath(project)
    real = os.path.realpath(os.path.join(root, norm))
    if real != root and not real.startswith(root + os.sep):
        raise RoadmapError("usage", "path '" + text[:200] + "' leaves the project", EXIT_USAGE)
    return norm


def _env(optional_locks):
    """The caller's environment with no GIT_* variable (they can point git at other dirs, helpers or traces), no
    SSH_ASKPASS, plus the fixed settings for reads."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "SSH_ASKPASS"}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "PAGER": "cat", "LC_ALL": "C",
                "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0" if optional_locks else "1"})
    return env


def _pump(stream, keep, on_over=None):
    """Read a pipe to its end, keeping at most `keep` bytes. Returns (kept_bytes, went_over). Past `keep` it calls
    on_over (if given) and stops reading; without on_over it only drains the rest so git never blocks."""
    kept = bytearray()
    over = False
    try:
        while True:
            chunk = stream.read1(65536)
            if not chunk:
                break
            if over:
                continue
            kept += chunk[:keep + 1 - len(kept)]
            if len(kept) > keep:
                over = True
                if on_over is not None:
                    on_over()
                    break
    finally:
        stream.close()
    return bytes(kept[:keep]), over


def _read_into(box, key, stream, keep, on_over):
    box[key] = _pump(stream, keep, on_over)


def _kill_group(proc):
    """Kill git and everything it started (it runs in its own session)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def _git(project, args, timeout, optional_locks=True):
    """Start git with a list argv in project, after the fixed read flags. Returns (returncode, stdout_bytes,
    stderr_text). A failing git is never raised here. A timeout gives RC_TIMEOUT; stdout past STDOUT_CAP gives
    RC_TOO_BIG, and the child is killed then instead of buffering the rest. Stderr is cut to STDERR_CUT, redacted."""
    argv = [git_path()] + GIT_READ_FLAGS + list(args)
    proc = subprocess.Popen(argv, cwd=project, env=_env(optional_locks), shell=False, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    box = {}
    readers = [
        threading.Thread(target=_read_into, args=(box, "out", proc.stdout, STDOUT_CAP, lambda: _kill_group(proc)),
                         daemon=True),
        threading.Thread(target=_read_into, args=(box, "err", proc.stderr, STDERR_KEEP, None), daemon=True),
    ]
    for thread in readers:
        thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        proc.wait()
    for thread in readers:
        thread.join(JOIN_GRACE_S)
        if thread.is_alive():  # a helper that outlived git still holds the pipe
            _kill_group(proc)
            thread.join(JOIN_GRACE_S)
    out, over = box.get("out", (b"", False))
    err = redact(box.get("err", (b"", False))[0].decode("utf-8", "replace"))[:STDERR_CUT]
    if timed_out:
        return RC_TIMEOUT, b"", "git timed out after %d s" % timeout
    if over:
        return RC_TOO_BIG, b"", "git output is over 2 MB; narrow the request"
    return proc.returncode, out, err


def _raise_for(rc, err):
    """The timeout and output-cap outcomes of _git as typed errors."""
    if rc == RC_TIMEOUT:
        raise RoadmapError("git_timeout", err, EXIT_EXTERNAL)
    if rc == RC_TOO_BIG:
        raise RoadmapError("git_too_big", err, EXIT_EXTERNAL)


def run(project, args, timeout=READ_TIMEOUT_S, optional_locks=True):
    """Run git in project and return its stdout text. Raises RoadmapError on failure, a timeout or output over the
    2 MB cap. Callers pass only argv they built themselves."""
    rc, out, err = _git(project, args, timeout, optional_locks)
    _raise_for(rc, err)
    if rc != 0:
        raise RoadmapError("git_failed", (err.strip().splitlines() or ["git failed"])[0], EXIT_EXTERNAL)
    return out.decode("utf-8", "replace")


def repo_root(project):
    """The project path after the checks: absolute, canonical (realpath equals it), and the root of its own git repo.
    Raises 'not_a_repo' (exit 3) with the plain message 'Not a git repo'; git init is never run here."""
    if not project or not os.path.isabs(project):
        raise RoadmapError("usage", "project path must be absolute", EXIT_USAGE)
    real = os.path.realpath(project)
    if real != project:
        raise RoadmapError("git_path", "project path is not canonical (symlink); refused", EXIT_USAGE)
    if not os.path.isdir(project):
        raise RoadmapError("not_a_repo", "Not a git repo", EXIT_NOT_FOUND, next="git init")
    rc, out, err = _git(project, ["rev-parse", "--show-toplevel"], READ_TIMEOUT_S)
    _raise_for(rc, err)
    if rc != 0 or os.path.realpath(out.decode("utf-8", "replace").strip() or ".") != real:
        raise RoadmapError("not_a_repo", "Not a git repo", EXIT_NOT_FOUND, next="git init")
    return project


def in_progress(project):
    """'merge' or 'rebase' while one is unfinished (read-only banner; finish it in a terminal), else None."""
    git_dir = run(project, ["rev-parse", "--absolute-git-dir"]).rstrip("\n")
    base = os.path.join(project, git_dir)
    if os.path.exists(os.path.join(base, "MERGE_HEAD")):
        return "merge"
    if os.path.isdir(os.path.join(base, "rebase-merge")) or os.path.isdir(os.path.join(base, "rebase-apply")):
        return "rebase"
    return None


def check_index_free(project):
    """Writes answer 'busy, retry' while .git/index.lock exists. The lock is never deleted here."""
    lock = run(project, ["rev-parse", "--git-path", "index.lock"]).rstrip("\n")
    if os.path.exists(os.path.join(project, lock)):
        raise RoadmapError("git_busy", "busy, retry", EXIT_CONFLICT)


def read_status(project):
    """Branch, upstream, ahead/behind, detached flag, in-progress state, and staged / changed / untracked / conflict
    files for a registered project. Read-only."""
    root = repo_root(project)
    status = parse_status(run(root, ["status", "--porcelain=v2", "--branch", "-z"]))
    status["in_progress"] = in_progress(root)
    return status


def read_log(project, limit=10):
    """The newest commits (at most LOG_MAX) with task and job links. An empty repo gives []."""
    try:
        count = max(1, min(int(limit), LOG_MAX))
    except (TypeError, ValueError):
        raise RoadmapError("usage", "limit must be a whole number", EXIT_USAGE)
    root = repo_root(project)
    rc, out, err = _git(root, ["log", "--topo-order", "-n", str(count), "--format=" + LOG_FORMAT], READ_TIMEOUT_S)
    if rc != 0 and "does not have any commits" in err:
        return []
    _raise_for(rc, err)
    if rc != 0:
        raise RoadmapError("git_failed", (err.strip().splitlines() or ["git log failed"])[0], EXIT_EXTERNAL)
    return parse_log(out.decode("utf-8", "replace"))


def read_branches(project):
    """Local branches with the current one flagged, upstream, ahead/behind and last commit time. Tags are not read."""
    root = repo_root(project)
    fmt = FIELD.join(["%(refname:short)", "%(HEAD)", "%(upstream:short)", "%(upstream:track,nobracket)",
                      "%(committerdate:unix)"])
    return parse_branches(run(root, ["for-each-ref", "--format=" + fmt, "refs/heads/"]))


def parse_status(text):
    """Parse `git status --porcelain=v2 --branch -z`. Pure: text in, dict out. A short or odd record is skipped."""
    result = {"branch": None, "oid": None, "detached": False, "upstream": None, "ahead": 0, "behind": 0,
              "staged": [], "changed": [], "untracked": [], "conflicts": []}
    tokens = text.split("\0")
    index = 0
    while index < len(tokens):
        rec = tokens[index]
        index += 1
        if not rec:
            continue
        if rec.startswith("# "):
            _branch_header(result, rec)
        elif rec.startswith("1 "):
            parts = rec.split(" ", 8)
            if len(parts) == 9:
                _entry(result, parts[1], parts[8])
        elif rec.startswith("2 "):
            parts = rec.split(" ", 9)
            origin = tokens[index] if index < len(tokens) else ""
            index += 1
            if len(parts) == 10:
                _entry(result, parts[1], parts[9], origin=origin)
        elif rec.startswith("u "):
            parts = rec.split(" ", 10)
            if len(parts) == 11 and parts[10] not in result["conflicts"]:
                result["conflicts"].append(parts[10])
        elif rec.startswith("? "):
            result["untracked"].append(rec[2:])
    return result


def _branch_header(result, rec):
    if rec.startswith("# branch.oid "):
        result["oid"] = rec[len("# branch.oid "):]
    elif rec.startswith("# branch.head "):
        head = rec[len("# branch.head "):]
        if head == "(detached)":
            result["detached"] = True
        else:
            result["branch"] = head
    elif rec.startswith("# branch.upstream "):
        result["upstream"] = rec[len("# branch.upstream "):]
    elif rec.startswith("# branch.ab "):
        parts = rec[len("# branch.ab "):].split(" ")
        if (len(parts) == 2 and parts[0][:1] == "+" and parts[1][:1] == "-"
                and parts[0][1:].isdecimal() and parts[1][1:].isdecimal()):
            result["ahead"] = int(parts[0][1:])
            result["behind"] = int(parts[1][1:])


def _entry(result, xy, path, origin=None):
    """One changed entry: X is the staged state, Y the worktree state, '.' means unchanged."""
    row = {"path": path, "code": xy}
    if origin is not None:
        row["from"] = origin
    if xy[0:1] not in (".", ""):
        result["staged"].append(dict(row))
    if xy[1:2] not in (".", ""):
        result["changed"].append(dict(row))


def parse_log(text):
    """Parse the records written by read_log (LOG_FORMAT). Each row: sha, parents (list), author, time
    (unix), subject, task, job.
    Fields are NUL-ended, so a message cannot start a new row. Author and subject are redacted."""
    tokens = text.split("\0")
    rows = []
    for start in range(0, len(tokens) - 5, 6):
        sha, parents, author, at, subject, body = tokens[start:start + 6]
        sha = sha.strip()  # the newline git writes between records sits before every sha after the first
        if not sha:
            continue
        task = TASK_TRAILER.search(body)
        job = JOB_TRAILER.search(body)
        kept = [p for p in parents.split() if SHA_OK.fullmatch(p)]
        rows.append({"sha": sha, "parents": kept, "author": redact(author),
                     "time": int(at) if at.isdecimal() else None,
                     "subject": redact(subject), "task": task.group(1) if task else None,
                     "job": job.group(1) if job else None})
    return rows


def parse_branches(text):
    """Parse the for-each-ref rows written by read_branches."""
    rows = []
    for line in text.split("\n"):
        parts = line.split(FIELD)
        if len(parts) < 5 or not parts[0]:
            continue
        name, head, upstream, track, when = parts[:5]
        ahead = TRACK_AHEAD.search(track)
        behind = TRACK_BEHIND.search(track)
        rows.append({"name": name, "current": head == "*", "upstream": upstream or None,
                     "ahead": int(ahead.group(1)) if ahead else 0,
                     "behind": int(behind.group(1)) if behind else 0,
                     "gone": track == "gone", "time": int(when) if when.isdecimal() else None})
    return rows


def is_secret_path(path):
    """True when the file name matches a secret pattern (.env*, *.pem, *key*, id_*). Its diff is hidden."""
    name = os.path.basename(str(path or "")).lower()
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAMES)


def is_binary(data):
    """A NUL byte in the first 8000 bytes means binary."""
    return b"\0" in data[:8000]


def diff_skip_reason(path, size, data=None):
    """Why a file's diff is not shown, or None. Secret names are hidden; binary or over 1 MB shows 'binary, N MB'."""
    if is_secret_path(path):
        return "hidden (secret pattern)"
    binary = data is not None and is_binary(data)
    if binary or size > BIG_FILE_BYTES:
        return "binary, %d MB" % max(1, math.ceil(size / (1024.0 * 1024)))
    return None


def cap_text(text, max_bytes=DIFF_FILE_BYTES, max_lines=DIFF_FILE_LINES):
    """Cut text to max_bytes and max_lines. Returns (text, truncated)."""
    truncated = False
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    cut = "\n".join(lines)
    raw = cut.encode("utf-8")
    if len(raw) > max_bytes:
        cut = raw[:max_bytes].decode("utf-8", "ignore")
        truncated = True
    return cut, truncated
