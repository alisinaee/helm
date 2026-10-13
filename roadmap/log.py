"""Logging for the roadmap package. WP11 adds rotation and the redaction filter; WP1 sets the namespace only."""

import logging

ROOT_NAME = "roadmap"

_root = logging.getLogger(ROOT_NAME)
if not _root.handlers:
    _root.addHandler(logging.NullHandler())


def get_logger(name=""):
    """Return the logger for a roadmap module, for example get_logger("services.jobs")."""
    return logging.getLogger(ROOT_NAME + "." + name if name else ROOT_NAME)
