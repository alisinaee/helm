"""Typed errors shared by the CLI and the HTTP layer, with the CLI exit codes."""

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_CONFLICT = 4
EXIT_INVALID_DATA = 5
EXIT_EXTERNAL = 6
EXIT_DOCTOR = 10


class RoadmapError(Exception):
    """An error with a stable machine code, a plain-words message and a CLI exit code."""

    def __init__(self, code, message, exit=EXIT_ERROR):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit = exit


def not_implemented(name):
    """Return the error for a command that has not been built yet."""
    return RoadmapError("not_implemented", name + " is not implemented yet", EXIT_ERROR)


def stub(name):
    """Return a command handler that reports the command as not implemented yet."""

    def handler(args):
        raise not_implemented(name)

    return handler
