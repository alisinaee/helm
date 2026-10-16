"""The checks behind `roadmap doctor`. Each check returns a row: id, title, status (ok, warn or fail), detail, and fix
(plain words, only when the status is not ok). run() returns every row and a summary.

Checks are read-only. launchctl, lsof, security and plutil go through the runner (see services/launchd.py), and the
health probe goes through an injectable function, so tests never run them for real. The keychain check asks
`security` for the item's metadata only (no -w), so the token is never read or shown.
"""

import http.client
import json
import os
import shutil
import stat
import sys

from roadmap.errors import EXIT_DOCTOR, RoadmapError
from roadmap.services import hooks_install, launchd, projects, usage
from roadmap.store import config as config_store
from roadmap.store import paths

OK, WARN, FAIL = "ok", "warn", "fail"
MIN_PYTHON = (3, 9)
KEYCHAIN_SERVICE = usage.KEYCHAIN_SERVICE
KEYCHAIN_NOT_FOUND = usage.KEYCHAIN_ITEM_NOT_FOUND
DEFAULT_PORT = 8780
# The legacy split-net dashboard port. Read at call time, so tests can point the check at a free port.
LEGACY_PORT = 8765
LEGACY_FIX = ("The old split-net dashboard may still run on 8765; Helm uses 8780 (set in the global config). "
              "Stop the old one only after the cutover checklist (docs/RELEASE.md).")
HEALTH_TIMEOUT_S = 1.0
HEALTH_PATH = "/api/v1/health"
LAUNCHD_LOG_LIMIT = 5 * 1024 * 1024
DIR_CHECKS = ("config", "state", "logs")
FILE_CHECKS = ("config.json", "phone.token", "usage.json")


def _row(check_id, title, status, detail, fix=None):
    row = {"id": check_id, "title": title, "status": status, "detail": detail}
    row["fix"] = None if status == OK else fix
    return row


def _repo_and_shim():
    repo = launchd.repo_root()
    return repo, os.path.join(repo, "bin", "roadmap")


def check_python():
    have = sys.version_info[:3]
    text = "%d.%d.%d" % have
    if tuple(have[:2]) >= MIN_PYTHON:
        return _row("python", "Python", OK, "Python " + text)
    return _row("python", "Python", FAIL, "Python " + text + " is too old (3.9 or newer is needed)",
                "Run roadmap with Python 3.9 or newer (python3 --version shows the one in use).")


def check_repo():
    repo, _ = _repo_and_shim()
    if os.path.isfile(os.path.join(repo, "roadmap", "__init__.py")):
        return _row("repo", "Repo path", OK, repo)
    return _row("repo", "Repo path", FAIL, "the roadmap package is not at " + repo,
                "Clone Helm again and run the service install from that folder.")


def check_shim():
    _, shim = _repo_and_shim()
    if not os.path.isfile(shim) or not os.access(shim, os.X_OK):
        return _row("shim", "bin/roadmap shim", FAIL, shim + " is missing or not executable",
                    "Run: chmod +x " + shim)
    if shutil.which("roadmap") is None:
        return _row("shim_path", "roadmap on PATH", WARN, "the roadmap command is not on PATH",
                    "Add " + os.path.dirname(shim) + " to PATH to run roadmap by name. Hooks use the full path anyway.")
    return _row("shim", "bin/roadmap shim", OK, shim)


def check_config():
    try:
        cfg = config_store.load()
    except RoadmapError as exc:
        return _row("config", "Global config", FAIL, exc.message,
                    "Fix or move the file named above. roadmap never overwrites a file it cannot read.")
    return _row("config", "Global config", OK, "%d project(s), port %s" % (len(cfg["projects"]), cfg["port"]))


def check_plist(runner):
    path = launchd.plist_path()
    if not os.path.isfile(path):
        return _row("plist", "launchd plist", WARN, "not installed yet (" + path + ")",
                    "Run: roadmap service install")
    ok, message = launchd.lint_plist(path, runner)
    if ok:
        return _row("plist", "launchd plist", OK, path + " (plutil lint ok)")
    return _row("plist", "launchd plist", FAIL, path + " does not lint: " + message,
                "Run: roadmap service install, which writes the plist again.")


def check_service(state):
    if state["loaded"]:
        return _row("service", "Service loaded", OK, "launchd has the job (pid %s, %s)"
                    % (state["pid"] or "none", state["state"] or "state unknown"))
    fix = "Run: roadmap service start" if state["plistInstalled"] else "Run: roadmap service install"
    return _row("service", "Service loaded", WARN, "launchd does not have the job loaded", fix)


def probe_health(port, timeout=HEALTH_TIMEOUT_S):
    """(answered, detail) for GET /api/v1/health on 127.0.0.1:port. Only the loopback address is used."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", HEALTH_PATH, headers={"Host": "127.0.0.1:%d" % port, "Accept": "application/json"})
        resp = conn.getresponse()
        body = resp.read(65536)
        if resp.status != 200:
            return False, "answered with HTTP %d" % resp.status
        data = json.loads(body.decode("utf-8", "replace"))
        if isinstance(data, dict) and data.get("ok") is True:
            return True, "answered on 127.0.0.1:%d" % port
        return False, "answered, but not with ok"
    except (OSError, ValueError, http.client.HTTPException) as exc:
        return False, "no answer (" + type(exc).__name__ + ")"
    finally:
        conn.close()


def check_health(port, state, probe):
    answered, detail = probe(port)
    if answered:
        return _row("health", "Health endpoint", OK, detail)
    if state["loaded"]:
        return _row("health", "Health endpoint", FAIL, "the service is loaded but " + detail,
                    "Run: roadmap service restart. If it still fails: roadmap service logs")
    return _row("health", "Health endpoint", WARN, "the service is not running (" + detail + ")",
                "Run: roadmap service install (or roadmap service start)")


def check_port(port, state, runner):
    rc, out, _ = runner(["lsof", "-nP", "-iTCP:%d" % int(port), "-sTCP:LISTEN", "-Fpc"])
    if rc == 127:
        return _row("port", "Port %d" % port, WARN, "lsof is missing, so the port could not be checked",
                    "Install the Xcode command line tools, or check the port by hand.")
    owner = launchd.parse_lsof(out) if rc == 0 else None
    if owner is None:
        return _row("port", "Port %d" % port, OK, "free")
    if state["loaded"] and state["pid"] is not None and owner["pid"] == state["pid"]:
        return _row("port", "Port %d" % port, OK, "used by the roadmap service (pid %s)" % owner["pid"])
    return _row("port", "Port %d" % port, FAIL, "used by %s (pid %s), not by roadmap" % (owner["name"], owner["pid"]),
                "Stop that process, or change \"port\" in " + paths.config_file() + " and run roadmap service restart.")


def check_legacy_port(state, runner, port=None):
    """Warn when something other than the roadmap service listens on the legacy split-net port (8765). Nothing
    listening, or only the roadmap service, is ok. Read-only: it uses the lsof helper in services/launchd."""
    port = LEGACY_PORT if port is None else port
    owner = launchd.listener_on(port, runner=runner)
    if owner is None:
        return _row("port_legacy", "Port %d" % port, OK, "free")
    if state["loaded"] and state["pid"] is not None and owner["pid"] == state["pid"]:
        return _row("port_legacy", "Port %d" % port, OK, "used by the roadmap service (pid %s)" % owner["pid"])
    return _row("port_legacy", "Port %d" % port, WARN, "used by %s (pid %s), not by roadmap"
                % (owner["name"], owner["pid"]), LEGACY_FIX)


def _mode_problems():
    problems = []
    dirs = {"config": paths.config_dir(), "state": paths.state_dir(), "logs": paths.logs_dir()}
    for name in DIR_CHECKS:
        target = dirs[name]
        if os.path.isdir(target) and _mode(target) != 0o700:
            problems.append((target, 0o700))
    files = {"config.json": paths.config_file(), "phone.token": paths.phone_token_file(),
             "usage.json": paths.usage_file()}
    for name in FILE_CHECKS:
        target = files[name]
        if os.path.isfile(target) and _mode(target) != 0o600:
            problems.append((target, 0o600))
    return problems


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def check_modes():
    problems = _mode_problems()
    if not problems:
        return _row("modes", "File and folder modes", OK, "folders 0700, files 0600")
    detail = "; ".join("%s is %04o" % (path, _mode(path)) for path, _ in problems)
    fix = "; ".join("chmod %04o %s" % (want, path) for path, want in problems)
    return _row("modes", "File and folder modes", FAIL, detail, "Run: " + fix)


def check_keychain(runner):
    rc, _, _ = runner(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE])
    if rc == 0:
        return _row("keychain", "Claude Code keychain item", OK, "found (the token is not read by doctor)")
    if rc == KEYCHAIN_NOT_FOUND:
        return _row("keychain", "Claude Code keychain item", WARN, "not found",
                    "Sign in to Claude Code on this Mac, then run roadmap usage sync once.")
    return _row("keychain", "Claude Code keychain item", WARN, "access denied or the keychain is locked",
                "macOS asks once for access. Click Always Allow when the Keychain prompt appears, then "
                "run roadmap usage sync.")


def check_usage():
    try:
        view = usage.show()
    except RoadmapError as exc:
        return _row("usage", "Plan usage", FAIL, exc.message, "Fix or move the usage.json file named above.")
    if view.get("lastError"):
        return _row("usage", "Plan usage", WARN, "last read failed: " + str(view["lastError"]),
                    "Run: roadmap usage sync. The keychain item check above says why it may fail.")
    if view.get("weeklyPercent") is None:
        return _row("usage", "Plan usage", WARN, "no usage stored yet", "Run: roadmap usage sync")
    if view.get("stale"):
        age = view.get("ageS")
        when = "%d min ago" % (age // 60) if isinstance(age, int) else "at an unknown time"
        return _row("usage", "Plan usage", WARN, "stale (last good reading " + when + ")",
                    "Run: roadmap usage sync, or check the service with roadmap service status.")
    return _row("usage", "Plan usage", OK, "fresh (week %s%%)" % view["weeklyPercent"])


def project_rows(project):
    pid = project["id"]
    rows = []
    try:
        report = projects.check_projects(pid)[0]
        bad = [f for f in report["files"] if f["status"] == "error"]
        missing = [f["file"] for f in report["files"] if f["status"] == "missing"]
        detail = ", ".join("%s v%s" % (f["file"], f["schemaVersion"]) for f in report["files"]
                           if f["status"] == "ok") or "no data files"
        if bad:
            rows.append(_row("project:" + pid + ":files", "Project " + pid + " files", FAIL,
                             bad[0]["file"] + ": " + str(bad[0]["error"]),
                             "Run: roadmap project check " + pid + " for the full list, then fix the file named."))
        elif missing:
            rows.append(_row("project:" + pid + ":files", "Project " + pid + " files", WARN,
                             "missing " + ", ".join(missing), "Run: roadmap project init " + project["path"]))
        else:
            rows.append(_row("project:" + pid + ":files", "Project " + pid + " files", OK, detail))
    except RoadmapError as exc:
        rows.append(_row("project:" + pid + ":files", "Project " + pid + " files", FAIL, exc.message,
                         "Run: roadmap project check " + pid))
    try:
        state = hooks_install.status(pid)
        if state["installed"]:
            rows.append(_row("project:" + pid + ":hooks", "Project " + pid + " hooks", OK, "installed"))
        else:
            stale = any(row["state"] == "stale" for row in state["events"].values())
            detail = "hooks point to another copy of roadmap" if stale else "hooks are not installed"
            rows.append(_row("project:" + pid + ":hooks", "Project " + pid + " hooks", WARN, detail,
                             "Run: roadmap hooks install " + pid))
    except RoadmapError as exc:
        rows.append(_row("project:" + pid + ":hooks", "Project " + pid + " hooks", WARN, exc.message,
                         "Run: roadmap hooks install " + pid))
    return rows


def check_projects():
    try:
        entries = config_store.list_projects()
    except RoadmapError:
        return []  # the config check already reports it
    if not entries:
        return [_row("projects", "Projects", OK, "none registered yet (roadmap project add <path>)")]
    rows = []
    for entry in entries:
        rows.extend(project_rows(entry))
    return rows


def check_logs():
    folder = paths.logs_dir()
    names = ("launchd.out", "launchd.err", "server.log")
    sizes = {}
    for name in names:
        target = os.path.join(folder, name)
        if os.path.isfile(target):
            sizes[name] = os.path.getsize(target)
    detail = ", ".join("%s %d KB" % (name, size // 1024) for name, size in sorted(sizes.items())) or "no log files"
    big = [name for name in ("launchd.out", "launchd.err") if sizes.get(name, 0) > LAUNCHD_LOG_LIMIT]
    if big:
        return _row("logs", "Log sizes", WARN, detail + " (over 5 MB)",
                    "roadmap trims launchd logs when the service starts. Run: roadmap service restart")
    return _row("logs", "Log sizes", OK, detail)


def run(runner=None, probe=None, port=None):
    """Run every check and return {"checks": [...], "summary": {ok, warn, fail}, "exitCode": 0 or 10}."""
    run_with = runner or launchd.RUNNER
    probe = probe or probe_health
    try:
        port = port if port is not None else config_store.load()["port"]
    except RoadmapError:
        port = DEFAULT_PORT
    state = launchd.status(run_with)
    rows = [check_python(), check_repo(), check_shim(), check_config(), check_plist(run_with),
            check_service(state), check_health(port, state, probe), check_port(port, state, run_with),
            check_legacy_port(state, run_with), check_modes(), check_keychain(run_with), check_usage()]
    rows.extend(check_projects())
    rows.append(check_logs())
    summary = {OK: 0, WARN: 0, FAIL: 0}
    for row in rows:
        summary[row["status"]] += 1
    return {"checks": rows, "summary": summary, "exitCode": EXIT_DOCTOR if summary[FAIL] else 0}
