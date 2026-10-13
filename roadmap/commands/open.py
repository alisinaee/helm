"""Top-level command open: opens the dashboard at http://127.0.0.1:<port>/ with the macOS open command (WP13).

The runner is injectable: RUNNER takes an argv list and returns (returncode, stdout, stderr). Tests replace it, so no
browser is started. The command is built with its own register() and is not yet listed in cli.COMMAND_MODULES, because
the stub `open` is still registered by commands/serve.py.
"""

import subprocess

from roadmap.errors import EXIT_EXTERNAL, RoadmapError
from roadmap.store import config as config_store

DEFAULT_PORT = 8765
OPEN_TOOL = "open"
TIMEOUT_S = 15


def _default_runner(argv):
    """Run argv without a shell and return (returncode, stdout, stderr). A missing tool gives 127."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except FileNotFoundError:
        return 127, "", argv[0] + " not found"
    except subprocess.TimeoutExpired:
        return 124, "", argv[0] + " timed out"
    return proc.returncode, proc.stdout, proc.stderr


RUNNER = _default_runner


def dashboard_url(port=None):
    """The loopback URL of the main listener. The port comes from config (port) unless one is given."""
    use_port = port if port is not None else config_store.load().get("port", DEFAULT_PORT)
    return "http://127.0.0.1:%d/" % use_port


def open_dashboard(port=None, runner=None):
    """Open the dashboard in the default browser. Exit 6 when the open command fails."""
    url = dashboard_url(port)
    rc, _, _ = (runner or RUNNER)([OPEN_TOOL, url])
    if rc != 0:
        raise RoadmapError("external", "could not open the browser at " + url, EXIT_EXTERNAL)
    return {"url": url, "opened": True}


def register(sub, common):
    """Add the open command."""
    opener = sub.add_parser("open", parents=[common], help="open the dashboard in the browser")
    opener.set_defaults(handler=handle)


def handle(args):
    """Open the dashboard and print its address."""
    result = open_dashboard()
    if not getattr(args, "json", False):
        print("opened " + result["url"])
    return result
