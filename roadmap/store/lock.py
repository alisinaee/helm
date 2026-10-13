"""Exclusive directory lock: flock on an fd of the data directory itself, the same mechanism as split_net jobs.py."""

import errno
import fcntl
import os
import time
from contextlib import contextmanager

from roadmap.errors import EXIT_CONFLICT, RoadmapError

POLL_S = 0.05
_BUSY = (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK)


@contextmanager
def locked(directory, timeout=10.0):
    """Hold the exclusive lock on directory. Waits up to timeout seconds, then raises locked (exit 4).
    No lock file is created, so nothing is left behind in the directory."""
    directory = os.path.abspath(directory)
    os.makedirs(directory, exist_ok=True)
    fd = os.open(directory, os.O_RDONLY)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in _BUSY:
                    raise
                if time.monotonic() >= deadline:
                    raise RoadmapError("locked", "another writer holds the lock on " + directory
                                       + "; try again in a moment", EXIT_CONFLICT)
                time.sleep(POLL_S)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
