"""Command group phone: start, stop, link and status for the read-only phone listener's tunnel (WP13).

start rotates the phone token and starts ssh to localhost.run. stop kills only that ssh and deletes the token. link
prints the private link, which grants read access. status reports whether the tunnel runs. Plain output goes to
stdout; the warning about the link goes to stderr, so the link can be captured with command substitution.
"""

import sys

from roadmap.services import tunnel

LINK_WARNING = ("This link gives read access to your dashboard. Keep it private: anyone who has it can read the "
                "dashboard until roadmap phone stop.")


def register(sub, common):
    """Add the phone group and its actions."""
    group = sub.add_parser("phone", parents=[common], help="read-only access from a phone")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text, handler in (
        ("start", "rotate the phone token and start the tunnel", handle_start),
        ("stop", "stop the tunnel and delete the token", handle_stop),
        ("link", "print the private phone link", handle_link),
        ("status", "show whether the tunnel is running", handle_status),
    ):
        actions.add_parser(name, parents=[common], help=text).set_defaults(handler=handler)


def _say(args, text, stream=None):
    if not getattr(args, "json", False):
        print(text, file=stream) if stream is not None else print(text)


def handle_start(args):
    """Rotate the token and start the tunnel. Exit 4 when a tunnel already runs, 6 when ssh gives no address."""
    result = tunnel.start()
    _say(args, "phone tunnel started at " + result["url"])
    _say(args, "run roadmap phone link for the private link")
    return result


def handle_stop(args):
    """Stop our tunnel and delete the token and the saved address."""
    result = tunnel.stop()
    _say(args, "phone tunnel stopped; the phone token is deleted")
    return result


def handle_link(args):
    """Print the private link, with a warning that it grants read access."""
    result = tunnel.link()
    _say(args, result["url"])
    _say(args, LINK_WARNING, stream=sys.stderr)
    if not result["running"]:
        _say(args, "the tunnel is not running, so this link will not open until roadmap phone start", stream=sys.stderr)
    return result


def handle_status(args):
    """Report whether the tunnel runs, with its pid and address."""
    result = tunnel.status()
    if result["running"]:
        _say(args, "running (pid %d) at %s" % (result["pid"], result["url"]))
    else:
        _say(args, "not running")
    return result
