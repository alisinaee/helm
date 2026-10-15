"""Chrome smoke test for the dashboard shell (stdlib only). Skips with a message when Chrome is not installed.

It starts `bin/roadmap serve --port 0 --no-usage-loop --no-phone --json` on 127.0.0.1 against a temporary ROADMAP_HOME
that registers the demo projects alpha, beta and gamma (fixtures/demo) and tests/fixtures/splitnet. The routes are
every section of alpha (the three Work views are separate routes), overview, inbox, work and tokens of beta and gamma,
and the global routes #/all/overview, #/all/inbox and #/all/tokens. Each route runs in headless Chrome at five sizes
and themes; each run dumps the DOM and checks it: no data-render-error, a non-empty main region, the left nav and the
right panel, no "Coming soon" in main, and a marker of the section (for example the board columns on Work > Board).
Five routes (overview, work board, roadmap, tokens, agents of alpha) also run at 1920x1080 and 2560x1080 in dark.
Alpha's routes also save a screenshot to build/ui-smoke/. The self-test page must report PASS once per run. The server
is stopped in a finally block. Exit 1 on any failure.
"""

import concurrent.futures
import html.parser
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin", "roadmap")
FIXTURES = os.path.join(REPO, "fixtures", "demo")
SPLITNET = os.path.join(REPO, "tests", "fixtures", "splitnet")
OUT_DIR = os.path.join(REPO, "build", "ui-smoke")
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_NAMES = ("chromium", "chromium-browser", "google-chrome")
# Every section of the router's registry (web/js/routes.js) in nav order, settings last. The unit test in
# tests/web/test_ui_smoke_sections.py requires this list to match routes.js, so a new section must be added here.
SECTIONS = ("overview", "inbox", "head", "roadmap", "planner", "work", "agents", "workflow", "tokens", "rules",
            "research", "activity", "git", "settings")
WORK_VIEWS = ("board", "list", "tree")
# (width, height, theme). Headless Chrome cannot go below about 500 px.
COMBOS = ((1440, 900, "dark"), (1440, 900, "light"), (1024, 768, "dark"), (768, 1024, "dark"), (500, 900, "dark"))
# Very wide screens (WP36): dark only, and only for the routes that WIDE_LABELS names (the rest would only repeat them).
WIDE_COMBOS = ((1920, 1080, "dark"), (2560, 1080, "dark"))
WIDE_LABELS = ("alpha overview", "alpha work/board", "alpha roadmap", "alpha tokens", "alpha agents")
# Chrome's flag that forces prefers-color-scheme. "light" goes through blink-settings because
# --force-prefers-color-scheme=light is ignored by this Chrome. scheme_probe checks that each one took effect.
SCHEME_FLAGS = {
    "dark": "--force-prefers-color-scheme=dark",
    "light": "--blink-settings=preferredColorScheme=1",
}
# Each route checks for one of these class names inside the page: the section's own markup.
PAGE_MARK = "page-title"
MARKERS = {"overview": "ov-card", "work/board": "wk-col", "work/list": "wk-table", "work/tree": "wk-tree",
           "roadmap": "lane", "issues": "iss-form", "tokens": "met-row"}
COMING_SOON = "Coming soon"
ERROR_TEXT = "This section could not be shown."
# Runs are one at a time: with several Chrome instances at once, the virtual-time budget ends before the page's module
# graph is fetched, and most dumps show the placeholder shell. Even alone, about one dump in twelve misses the graph,
# so a dump that is not ready is taken again, up to ATTEMPTS times; the last try is the one checked.
WORKERS = 1
ATTEMPTS = 3
VIRTUAL_BUDGET_MS = 5000
RUN_TIMEOUT_S = 120
SERVE_TIMEOUT_S = 20
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class SmokeError(Exception):
    """A failure that stops one step; the run goes on with the other steps where it can."""


def find_chrome():
    """The Chrome binary, or None when it is not installed."""
    if os.path.exists(CHROME_APP):
        return CHROME_APP
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


class DomScan(html.parser.HTMLParser):
    """Collects the text inside every element id (as "name") and class (as ".name"), and notes data-render-error."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.texts = {}
        self.render_error = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "data-render-error" in attributes:
            self.render_error = True
        if tag in VOID:
            return
        keys = []
        if attributes.get("id") is not None:
            keys.append(attributes["id"])
        keys.extend("." + name for name in (attributes.get("class") or "").split())
        for key in keys:
            self.texts.setdefault(key, "")
        self.stack.append((tag, keys))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        for _tag, keys in self.stack:
            for key in keys:
                self.texts[key] = self.texts.get(key, "") + data

    def text_of(self, ident):
        return " ".join(self.texts.get(ident, "").split())

    def has(self, ident):
        return ident in self.texts


def chrome_run(chrome, url, width, height, scheme, profile_dir, screenshot=None):
    """One headless run in the given colour scheme. Returns the dumped DOM as text."""
    args = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--user-data-dir=" + profile_dir,
        "--window-size=%d,%d" % (width, height), SCHEME_FLAGS[scheme],
        "--virtual-time-budget=%d" % VIRTUAL_BUDGET_MS,
    ]
    if screenshot:
        args.append("--screenshot=" + screenshot)
    args.extend(["--dump-dom", url])
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise SmokeError("Chrome did not finish %s within %d s" % (url, RUN_TIMEOUT_S))
    if not done.stdout.strip():
        raise SmokeError("Chrome dumped nothing for %s (exit %d)" % (url, done.returncode))
    return done.stdout


def scheme_probe(chrome, work, scheme):
    """Checks that --force-prefers-color-scheme really changes matchMedia, so the light and dark runs differ."""
    page = os.path.join(work, "probe-" + scheme + ".html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><html><body><p id=\"out\">x</p><script>document.getElementById('out')"
                 ".textContent = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';"
                 "</script></body></html>\n")
    dom = chrome_run(chrome, "file://" + page, 800, 600, scheme, os.path.join(work, "probe-profile-" + scheme))
    scan = DomScan()
    scan.feed(dom)
    got = scan.text_of("out")
    if got != scheme:
        raise SmokeError("colour scheme %s did not take effect in Chrome (the probe saw %r)" % (scheme, got))


def check_shell(scan, label):
    """The checks every route shares: no render error, the shell regions and no placeholder in the main region."""
    problems = []
    if scan.render_error:
        problems.append("%s: data-render-error is set" % label)
    if ERROR_TEXT in " ".join(scan.texts.values()):
        problems.append("%s: a section shows '%s'" % (label, ERROR_TEXT))
    if not scan.text_of("nav"):
        problems.append("%s: the left nav is empty or missing" % label)
    if not scan.text_of("side") or COMING_SOON in scan.text_of("side"):
        problems.append("%s: the right panel is empty, missing or still the placeholder" % label)
    if not scan.text_of("main"):
        problems.append("%s: the main region is empty" % label)
    if COMING_SOON in scan.text_of("main"):
        problems.append("%s: main shows 'Coming soon' for a built section" % label)
    return problems


def check_route(scan, label, marker):
    """Shell checks plus the section's own marker: its page title, or a class only that section renders."""
    problems = check_shell(scan, label)
    wanted = marker or PAGE_MARK
    if not scan.has("." + wanted):
        problems.append("%s: section marker .%s is missing" % (label, wanted))
    return problems


def check_selftest(scan, label):
    result = scan.text_of("result")
    if result == "PASS":
        return []
    report = scan.text_of("report")[:300]
    return ["%s: dev/tests.html reports %r %s" % (label, result or "nothing", report)]


def write_home(work, home):
    """A ROADMAP_HOME with the four projects registered. Returns the project ids by name."""
    env = dict(os.environ, ROADMAP_HOME=home)
    ids = {}
    sources = [(name, os.path.join(FIXTURES, name)) for name in ("alpha", "beta", "gamma")]
    sources.append(("split-net", SPLITNET))
    for name, source in sources:
        root = os.path.join(work, "projects", name)
        if name == "split-net":
            shutil.copytree(source, os.path.join(root, "docs"))
        else:
            shutil.copytree(source, root)
        done = subprocess.run([BIN, "project", "add", root, "--name", name, "--json"], env=env,
                              capture_output=True, text=True, timeout=60, check=False)
        try:
            ids[name] = json.loads(done.stdout)["data"]["project"]["id"]
        except (ValueError, KeyError, TypeError):
            raise SmokeError("project add %s failed: %s" % (name, (done.stderr or done.stdout).strip()[:300]))
    return ids


def start_server(home, work):
    """Starts the server and returns (process, port). The caller must stop the process."""
    env = dict(os.environ, ROADMAP_HOME=home)
    err_path = os.path.join(work, "serve-stderr.log")
    with open(err_path, "w", encoding="utf-8") as err:
        proc = subprocess.Popen([BIN, "serve", "--port", "0", "--no-usage-loop", "--no-phone", "--json"], env=env,
                                stdout=subprocess.PIPE, stderr=err, text=True)
    ready, _w, _x = select.select([proc.stdout], [], [], SERVE_TIMEOUT_S)
    line = proc.stdout.readline() if ready else ""
    try:
        return proc, json.loads(line)["data"]["port"]
    except (ValueError, KeyError, TypeError):
        stop_server(proc)
        raise SmokeError("the server did not start (see %s)" % err_path)


def stop_server(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def routes(ids):
    """(label, hash path, marker, screenshot name or None) for every route the smoke checks."""
    alpha = ids["alpha"]
    out = []
    for section in SECTIONS:
        if section == "work":
            for view in WORK_VIEWS:
                path = "p/%s/work/%s" % (alpha, view)
                out.append(("alpha work/" + view, path, MARKERS["work/" + view], "alpha-work-" + view))
        else:
            path = "p/%s/%s" % (alpha, section)
            out.append(("alpha " + section, path, MARKERS.get(section), "alpha-" + section))
    for name in ("beta", "gamma"):
        pid = ids[name]
        for section, marker in (("overview", MARKERS["overview"]), ("inbox", None), ("work/board",
                                MARKERS["work/board"]), ("tokens", MARKERS["tokens"])):
            out.append(("%s %s" % (name, section), "p/%s/%s" % (pid, section), marker, None))
    for section, marker in (("overview", MARKERS["overview"]), ("inbox", None), ("tokens", MARKERS["tokens"])):
        out.append(("all " + section, "all/" + section, marker, None))
    return out


def dump_ready(chrome, url, combo, work, screenshot, ready):
    """Dumps the page until ready(scan) is true or the attempts run out. Returns the last scan."""
    width, height, scheme = combo
    scan = None
    for _attempt in range(ATTEMPTS):
        profile = tempfile.mkdtemp(prefix="profile-", dir=work)
        try:
            dom = chrome_run(chrome, url, width, height, scheme, profile, screenshot)
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        scan = DomScan()
        scan.feed(dom)
        if ready(scan):
            break
    return scan


def app_ready(scan):
    return bool(scan.text_of("nav"))


def run_one(chrome, base, route, combo, work):
    """One route at one size and theme. Returns (failures, screenshot path or None)."""
    label, path, marker, shot_name = route
    tag = "%dx%d-%s" % (combo[0], combo[1], combo[2])
    screenshot = None
    if shot_name:
        screenshot = os.path.join(OUT_DIR, "%s-%s.png" % (shot_name, tag))
    try:
        scan = dump_ready(chrome, base + "/#/" + path, combo, work, screenshot, app_ready)
        return check_route(scan, "%s %s" % (label, tag), marker), screenshot
    except SmokeError as exc:
        return ["%s %s: %s" % (label, tag, exc)], None


def run_checks(chrome, base, ids, work, failures, shots):
    """Every route at every size and theme, plus the self-test page. Returns the number of page runs."""
    for scheme in ("dark", "light"):
        try:
            scheme_probe(chrome, work, scheme)
        except SmokeError as exc:
            failures.append(str(exc))
    jobs = []
    all_routes = routes(ids)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for route in all_routes:
            # Alpha routes take screenshots at every size; the others only check the DOM, at the first combo.
            is_alpha = route[0].startswith("alpha")
            combos = COMBOS if is_alpha else COMBOS[:1]
            if route[0] in WIDE_LABELS:
                combos = COMBOS + WIDE_COMBOS
            for combo in combos:
                jobs.append(pool.submit(run_one, chrome, base, route, combo, work))
        for combo in COMBOS:
            jobs.append(pool.submit(self_test_job, chrome, base, combo, work))
        for job in concurrent.futures.as_completed(jobs):
            problems, shot = job.result()
            failures.extend(problems)
            if shot and os.path.exists(shot):
                shots.append(shot)
    return len(jobs)


def self_test_job(chrome, base, combo, work):
    label = "self-test %dx%d-%s" % (combo[0], combo[1], combo[2])
    try:
        scan = dump_ready(chrome, base + "/dev/tests.html", combo, work, None,
                          lambda found: found.text_of("result") not in ("", "Running"))
        return check_selftest(scan, label), None
    except SmokeError as exc:
        return ["%s: %s" % (label, exc)], None


def clear_old_shots():
    """Removes the PNGs of an earlier run so the count printed is this run's."""
    if not os.path.isdir(OUT_DIR):
        return
    for name in os.listdir(OUT_DIR):
        if name.endswith(".png"):
            os.remove(os.path.join(OUT_DIR, name))


def main():
    chrome = find_chrome()
    if chrome is None:
        print("SKIP: Chrome not found")
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    clear_old_shots()
    work = tempfile.mkdtemp(prefix="rb-ui-smoke-")
    home = os.path.join(work, "home")
    os.makedirs(home)
    failures = []
    shots = []
    runs = 0
    proc = None
    try:
        ids = write_home(work, home)
        proc, port = start_server(home, work)
        runs = run_checks(chrome, "http://127.0.0.1:%d" % port, ids, work, failures, shots)
    except SmokeError as exc:
        failures.append(str(exc))
    finally:
        stop_server(proc)
        shutil.rmtree(work, ignore_errors=True)
    for reason in sorted(failures):
        print("FAIL: " + reason)
    if failures:
        return 1
    print("ui smoke: ok (%d page runs, %d screenshots in %s)" % (runs, len(shots), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
