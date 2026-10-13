"""Chrome smoke test for the dashboard (stdlib only). Skips with a message when Chrome is not installed.

It starts `bin/roadmap serve --port 0 --no-usage-loop --json` on 127.0.0.1 against a temporary ROADMAP_HOME that
registers a copy of tests/fixtures/splitnet. For each of 1280x900 and 375x812, in light and dark, headless Chrome
dumps the DOM of the project route, the home route and web/dev/tests.html. The checks: no data-render-error, every
project section is non-empty and has no "could not be shown" banner, the home sections are non-empty, and the
self-test page reports PASS (it checks the format cases and that the page does not scroll sideways). Screenshots of
the project route go to build/ui-smoke/. The server is stopped in a finally block. Exit 1 on any failure.
"""

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
FIXTURE = os.path.join(REPO, "tests", "fixtures", "splitnet")
OUT_DIR = os.path.join(REPO, "build", "ui-smoke")
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_NAMES = ("chromium", "chromium-browser", "google-chrome")
SIZES = ((1280, 900), (375, 812))
THEMES = ("dark", "light")
# Chrome's flag that forces prefers-color-scheme. "dark" has its own flag; "light" is set through blink-settings
# because --force-prefers-color-scheme=light is ignored by this Chrome. scheme_probe checks that each one took effect.
SCHEME_FLAGS = {
    "dark": "--force-prefers-color-scheme=dark",
    "light": "--blink-settings=preferredColorScheme=1",
}
PROJECT_SECTIONS = ("phases", "running", "needs", "next", "recent", "extras", "legend")
HOME_SECTIONS = ("projects", "running")
REGIONS = ("proj-main", "proj-side")  # class names of the two columns of the project view
ERROR_TEXT = "This section could not be shown."
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
    """Collects, for every element id, the text inside it, and whether any element carries data-render-error."""

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


def check_project(scan, label):
    problems = []
    if scan.render_error:
        problems.append("%s: data-render-error is set" % label)
    if ERROR_TEXT in " ".join(scan.texts.values()):
        problems.append("%s: a section shows '%s'" % (label, ERROR_TEXT))
    for region in tuple("." + name for name in REGIONS) + tuple("sec-%s-body" % name for name in PROJECT_SECTIONS):
        if not scan.text_of(region):
            problems.append("%s: region %s is empty or missing" % (label, region))
    return problems


def check_home(scan, label):
    problems = []
    if scan.render_error:
        problems.append("%s: data-render-error is set" % label)
    for name in HOME_SECTIONS:
        if not scan.text_of("sec-%s-body" % name):
            problems.append("%s: section %s is empty or missing" % (label, name))
    return problems


def check_selftest(scan, label):
    result = scan.text_of("result")
    if result == "PASS":
        return []
    report = scan.text_of("report")[:300]
    return ["%s: dev/tests.html reports %r %s" % (label, result or "nothing", report)]


def write_home(home):
    """A ROADMAP_HOME with the fixture registered; returns the project id the CLI assigned."""
    project_root = os.path.join(os.path.dirname(home), "split_net")
    shutil.copytree(FIXTURE, os.path.join(project_root, "docs"))
    env = dict(os.environ, ROADMAP_HOME=home)
    done = subprocess.run([BIN, "project", "add", project_root, "--name", "split-net", "--json"], env=env,
                          capture_output=True, text=True, timeout=60, check=False)
    try:
        return json.loads(done.stdout)["data"]["project"]["id"]
    except (ValueError, KeyError, TypeError):
        raise SmokeError("project add failed: " + (done.stderr or done.stdout).strip()[:300])


def start_server(home, work):
    """Starts the server and returns (process, port). The caller must stop the process."""
    env = dict(os.environ, ROADMAP_HOME=home)
    err_path = os.path.join(work, "serve-stderr.log")
    with open(err_path, "w", encoding="utf-8") as err:
        proc = subprocess.Popen([BIN, "serve", "--port", "0", "--no-usage-loop", "--json"], env=env,
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


def run_checks(chrome, base, project_id, work, failures, shots):
    """Every size and theme: the project route, the home route and the self-test page. Returns the run count."""
    runs = 0
    for scheme in THEMES:
        try:
            scheme_probe(chrome, work, scheme)
        except SmokeError as exc:
            failures.append(str(exc))
    for width, height in SIZES:
        for scheme in THEMES:
            tag = "%dx%d-%s" % (width, height, scheme)
            os.makedirs(OUT_DIR, exist_ok=True)
            shot = os.path.join(OUT_DIR, "shot-%s-project.png" % tag)
            jobs = [
                ("project", base + "/#/p/" + project_id, check_project, shot),
                ("home", base + "/#/", check_home, None),
                ("self-test", base + "/dev/tests.html", check_selftest, None),
            ]
            for name, url, checker, screenshot in jobs:
                label = "%s %s" % (name, tag)
                profile = tempfile.mkdtemp(prefix="profile-", dir=work)
                try:
                    dom = chrome_run(chrome, url, width, height, scheme, profile, screenshot)
                    scan = DomScan()
                    scan.feed(dom)
                    failures.extend(checker(scan, label))
                    runs += 1
                except SmokeError as exc:
                    failures.append("%s: %s" % (label, exc))
                finally:
                    shutil.rmtree(profile, ignore_errors=True)
            if os.path.exists(shot):
                shots.append(shot)
    return runs


def main():
    chrome = find_chrome()
    if chrome is None:
        print("SKIP: Chrome not found")
        return 0
    work = tempfile.mkdtemp(prefix="rb-ui-smoke-")
    home = os.path.join(work, "home")
    failures = []
    shots = []
    runs = 0
    proc = None
    try:
        project_id = write_home(home)
        proc, port = start_server(home, work)
        runs = run_checks(chrome, "http://127.0.0.1:%d" % port, project_id, work, failures, shots)
    except SmokeError as exc:
        failures.append(str(exc))
    finally:
        stop_server(proc)
        shutil.rmtree(work, ignore_errors=True)
    for path in shots:
        print("screenshot: " + path)
    for reason in failures:
        print("FAIL: " + reason)
    if failures:
        return 1
    print("ui smoke: ok (%d page runs, %d screenshots)" % (runs, len(shots)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
