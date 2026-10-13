"""Top-level commands serve and open: the dashboard server. Implemented in WP5, stubs until then."""

from roadmap.errors import stub


def register(sub, common):
    """Add serve and open to the root subparsers."""
    serve = sub.add_parser("serve", parents=[common], help="run the dashboard server on 127.0.0.1")
    serve.add_argument("--port", type=int, default=None, help="main listener port (default 8765)")
    serve.set_defaults(handler=stub("serve"))

    opener = sub.add_parser("open", parents=[common], help="open the dashboard in the browser")
    opener.set_defaults(handler=stub("open"))
