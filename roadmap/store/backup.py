"""Timestamped copies of data files under the state directory. Keeps the newest 14 backups per project."""

import datetime
import os
import shutil
import stat

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.store import paths

KEEP = 14
STAMP = "%Y%m%dT%H%M%S%fZ"


def backup_files(project_id, files, now=None):
    """Copy the files that exist into backups/<project>/<timestamp>/, then prune. Returns the new folder."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    sources = []
    for src in files:
        try:
            mode = os.lstat(src).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise RoadmapError("invalid_data", "refusing to back up a symlink: " + src, EXIT_INVALID_DATA)
        if stat.S_ISREG(mode):
            sources.append(src)
    root = paths.backups_dir(project_id)
    paths.ensure_dir(root)
    while True:
        dest = os.path.join(root, now.strftime(STAMP))
        try:
            os.mkdir(dest, paths.DIR_MODE)
            break
        except FileExistsError:
            now = now + datetime.timedelta(microseconds=1)
    os.chmod(dest, paths.DIR_MODE)
    for src in sources:
        target = os.path.join(dest, os.path.basename(src))
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)  # never follows a link that appeared after the check
        with os.fdopen(fd, "rb") as inp, open(target, "wb") as out:
            shutil.copyfileobj(inp, out)
        os.chmod(target, paths.FILE_MODE)
    prune(project_id, KEEP)
    return dest


def prune(project_id, keep=KEEP):
    """Delete all but the newest keep backup folders for a project. Returns the names deleted."""
    root = paths.backups_dir(project_id)
    if not os.path.isdir(root):
        return []
    names = sorted(n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)))
    doomed = names[:-keep] if keep > 0 else names
    for name in doomed:
        shutil.rmtree(os.path.join(root, name))
    return doomed
