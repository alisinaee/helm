"""Top-level command version: prints the package version. The one implemented command in WP1."""

from roadmap import __version__


def register(sub, common):
    """Add the version command to the root subparsers."""
    parser = sub.add_parser("version", parents=[common], help="print the roadmap version")
    parser.set_defaults(handler=handle)


def handle(args):
    """Return the version data; print it in plain mode."""
    if not getattr(args, "json", False):
        print("roadmap " + __version__)
    return {"version": __version__}
