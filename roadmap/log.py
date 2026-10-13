"""Logging for the roadmap package: the namespace, the file handler with rotation, the redaction filter and the
access-log line. Standard library only, and it imports nothing from the project (see the layering rule).

server.log is a RotatingFileHandler: 1 MB per file, 5 backups, mode 0600. Every record passes the redaction filter,
which hides Bearer tokens, Anthropic keys (sk-ant-...) and any k=<value> pair (the phone token parameter).
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler

ROOT_NAME = "roadmap"
SERVER_LOG = "server.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
FILE_MODE = 0o600
_FILE_TAG = "roadmap_file"

_REDACTIONS = (
    (re.compile(r"Bearer\s+\S+"), "Bearer [redacted]"),
    (re.compile(r"sk-ant-\S+"), "sk-ant-[redacted]"),
    (re.compile(r"k=\S+"), "k=[redacted]"),
)

_root = logging.getLogger(ROOT_NAME)
if not _root.handlers:
    _root.addHandler(logging.NullHandler())


def get_logger(name=""):
    """Return the logger for a roadmap module, for example get_logger("services.jobs")."""
    return logging.getLogger(ROOT_NAME + "." + name if name else ROOT_NAME)


def redact(text):
    """Return text with bearer tokens, Anthropic keys and k=<value> pairs replaced by a placeholder."""
    out = str(text)
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out


class RedactingFilter(logging.Filter):
    """Formats each record, redacts the message and keeps the record. It never drops a record."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # a bad format string must not leak the raw arguments
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        return True


class _OwnerOnlyRotatingHandler(RotatingFileHandler):
    """RotatingFileHandler that creates each file with mode 0600, including the files made after a rollover."""

    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
        return os.fdopen(fd, self.mode, encoding=self.encoding)


def setup_file_logging(logs_dir, logger=None):
    """Attach the rotating server.log handler (with the redaction filter) to the roadmap logger. Calling it again
    for the same directory adds nothing. Returns the log file path."""
    os.makedirs(logs_dir, mode=0o700, exist_ok=True)
    target = logger if logger is not None else logging.getLogger(ROOT_NAME)
    path = os.path.join(logs_dir, SERVER_LOG)
    for handler in target.handlers:
        if getattr(handler, _FILE_TAG, None) == path:
            return path
    handler = _OwnerOnlyRotatingHandler(path, mode="a", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                        encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())
    setattr(handler, _FILE_TAG, path)
    target.addHandler(handler)
    if target.level == logging.NOTSET or target.level > logging.INFO:
        target.setLevel(logging.INFO)
    return path


def access_line(method, path, status, elapsed_ms):
    """One access-log line: method, the path without its query string or fragment, status and milliseconds."""
    bare = str(path).split("#", 1)[0].split("?", 1)[0]
    return redact("%s %s %d %dms" % (method, bare, int(status), int(elapsed_ms)))
