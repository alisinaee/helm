"""Number formatting for the dashboard. Mirrors web/js/format.js; both are tested against format_cases.json.

Every function takes a number and returns a string. None (missing) gives the en dash.
Rounding is half up, as JavaScript's Math.round does, so the two sides agree.
"""

import math

MISSING = "–"


def _round_half_up(x):
    return int(math.floor(x + 0.5))


def fmt_tokens(k):
    """Token count given in thousands. Under 1000k: '840k'. From 1000k: '1.2M'."""
    if k is None:
        return MISSING
    n = _round_half_up(k)
    if n < 1000:
        return "%dk" % n
    return "%.1fM" % (n / 1000.0)


def fmt_percent(p):
    """Percent in 0-100 units. Whole numbers, '<1%' for 0 < p < 1, and '0%' for zero."""
    if p is None:
        return MISSING
    if 0 < p < 1:
        return "<1%"
    return "%d%%" % _round_half_up(p)


def fmt_duration(seconds):
    """Duration in seconds: '45s', '4m 12s', '1h 05m', '1d 3h'. Negative values count as 0."""
    if seconds is None:
        return MISSING
    total = max(0, _round_half_up(seconds))
    if total < 60:
        return "%ds" % total
    if total < 3600:
        return "%dm %02ds" % (total // 60, total % 60)
    if total < 86400:
        return "%dh %02dm" % (total // 3600, (total % 3600) // 60)
    return "%dd %dh" % (total // 86400, (total % 86400) // 3600)


def fmt_count(n):
    """Whole count with thousands grouping: '1,234'."""
    if n is None:
        return MISSING
    return "{:,}".format(_round_half_up(n))
