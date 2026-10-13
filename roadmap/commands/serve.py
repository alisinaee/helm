"""Top-level commands serve and open. serve runs the dashboard server on 127.0.0.1 and, unless --no-usage-loop,
the usage refresh loop in a daemon thread. open is still a stub."""

import errno
import json
import logging
import signal
import sys
import threading

from roadmap import log as rlog
from roadmap.errors import EXIT_CONFLICT, EXIT_USAGE, RoadmapError, stub
from roadmap.http import server as http_server
from roadmap.services import launchd, loader, usage
from roadmap.store import config as config_store
from roadmap.store import paths

DEFAULT_PORT = 8765


def register(sub, common):
    """Add serve and open to the root subparsers."""
    serve = sub.add_parser("serve", parents=[common], help="run the dashboard server on 127.0.0.1")
    serve.add_argument("--port", type=int, default=None, help="listener port (default: config port, 8765)")
    serve.add_argument("--no-usage-loop", action="store_true", help="do not refresh plan usage in the background")
    serve.set_defaults(handler=run)

    opener = sub.add_parser("open", parents=[common], help="open the dashboard in the browser")
    opener.set_defaults(handler=stub("open"))


def run(args):
    """Bind, start the usage loop, serve until SIGINT or SIGTERM, then shut down. Exit 4 when the port is busy."""
    cfg = config_store.load()
    port = args.port if args.port is not None else cfg.get("port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise RoadmapError("invalid_input", "port must be a whole number from 0 to 65535", EXIT_USAGE)
    try:
        httpd = http_server.make_server(port)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        owner = loader.port_owner(port)
        who = "another process" if owner is None else "%s, pid %s" % (owner["name"], owner["pid"])
        raise RoadmapError("conflict", "port %d is busy (used by %s)" % (port, who), EXIT_CONFLICT)

    _log_to_stderr()
    rlog.setup_file_logging(paths.logs_dir())
    launchd.prepare_launchd_logs()
    bound = httpd.server_address[1]
    url = "http://127.0.0.1:%d/" % bound
    stop_usage = threading.Event()
    if not args.no_usage_loop:
        threading.Thread(target=usage.run_loop, args=(stop_usage,), name="usage-loop", daemon=True).start()

    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "data": {"port": bound, "url": url, "usage_loop": not args.no_usage_loop}}),
              flush=True)
        args.json = False  # the start line above is the envelope; cli.main must not print a second one
    else:
        print("roadmap: serving " + url, flush=True)

    stopping = threading.Event()

    def ask_to_stop(signum, frame):
        stopping.set()

    signal.signal(signal.SIGINT, ask_to_stop)
    signal.signal(signal.SIGTERM, ask_to_stop)
    worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5}, name="http", daemon=True)
    worker.start()
    stopping.wait()
    httpd.shutdown()
    worker.join(5)
    httpd.server_close()
    stop_usage.set()
    print("roadmap: stopped", file=sys.stderr, flush=True)
    return None


def _log_to_stderr():
    """Send roadmap log lines (the access log included) to stderr at INFO, once per process."""
    logger = logging.getLogger("roadmap")
    if any(getattr(h, "roadmap_stderr", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    handler.roadmap_stderr = True
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
