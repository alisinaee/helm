"""Markdown helpers for the roadmap files: table rows, table iteration, level-2 sections and status classification.

Pure functions over text. Nothing here touches the filesystem.
"""

import re

SEP_CELL = re.compile(r"^:?-{3,}:?$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")

STATUS_MARKS = (("✅", "done"), ("\U0001F7E1", "partial"), ("⏸", "hold"), ("⬜", "todo"), ("💡", "backlog"))


def split_row(line):
    """Split one markdown table row into stripped cells. Escaped pipes (backslash-pipe) stay inside a cell."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT.split(s)]


def cell(row, i):
    """Cell i of a row, or '' when the row is shorter (ragged rows are allowed)."""
    return row[i] if 0 <= i < len(row) else ""


def iter_tables(text):
    """Yield (header, rows) for every markdown table in text. A table needs a valid separator row."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if (lines[i].lstrip().startswith("|") and i + 1 < len(lines)
                and lines[i + 1].lstrip().startswith("|")):
            head = split_row(lines[i])
            sep = split_row(lines[i + 1])
            if sep and all(SEP_CELL.match(c) for c in sep):
                rows, j = [], i + 2
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    rows.append(split_row(lines[j]))
                    j += 1
                yield head, rows
                i = j
                continue
        i += 1


def section(text, prefix):
    """Text under the first level-2 heading whose title starts with prefix (given without '## ')."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if on:
                break
            on = line[3:].startswith(prefix)
            continue
        if on:
            out.append(line)
    return "\n".join(out)


def classify(text):
    """Status from a cell. The first status emoji wins; words are the fallback."""
    best = None
    for mark, state in STATUS_MARKS:
        i = text.find(mark)
        if i != -1 and (best is None or i < best[0]):
            best = (i, state)
    if best:
        return best[1]
    low = text.lower()
    if "backlog" in low:
        return "backlog"
    if "hold" in low or "parked" in low:
        return "hold"
    if any(w in low for w in ("passed", "done", "researched", "supported")):
        return "done"
    if "partial" in low or "progress" in low:
        return "partial"
    return "todo"
