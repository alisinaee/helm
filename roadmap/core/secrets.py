"""Secret scrubbing (HEAD-SPEC section 7): masks credentials, personal data and long opaque runs in text before it is
written to a file or summarised. Pure: no I/O and no import from the project. Standard library only.

scrub() applies the rules in a fixed order, so a value masked by an earlier rule is never matched again. The masks are
"[secret]", "[email]", "[number]" and "~" for the home folder. Git commit shas (40 hex characters) and short ids such
as R7.31, P1.2 or H2 are kept, because the head's text refers to them all the time.
"""

import re

SECRET = "[secret]"
EMAIL = "[email]"
NUMBER = "[number]"
GIT_SHA1 = re.compile(r"[0-9a-fA-F]{40}")

_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]+-----.*?(?:-----END [A-Z0-9 ]+-----|\Z)", re.DOTALL)
_VENDOR = tuple(re.compile(p) for p in (
    r"\bsk-[A-Za-z0-9_-]{16,}",                  # OpenAI and Anthropic keys (sk-..., sk-ant-...)
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",             # GitHub tokens
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",           # GitHub fine-grained tokens
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",           # Slack tokens
    r"\bAKIA[0-9A-Z]{16}\b",                     # AWS access key ids
    r"\bAIza[0-9A-Za-z_-]{35}",                  # Google API keys
    r"\beyJ[\w-]{8,}\.[\w-]{8,}\.?[\w-]*",       # JWTs
    r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}",  # Stripe secret and restricted keys
    r"\bglpat-[A-Za-z0-9_-]{20,}",               # GitLab personal access tokens
))
# A short id such as H2, R7.31, P1.2 or j104 is a task or job id, never a secret, even after a credential-looking name.
_TASK_VALUE = re.compile(r"[A-Za-z]\d{1,4}(?:\.\d{1,4})*")
_BEARER = re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]+")
# A name ending in a credential word (AWS_SECRET_ACCESS_KEY, db_password, api-key) followed by = or :. The value is
# a quoted string to its closing quote (so a value with spaces is masked whole) or a run up to a space or ;,&,quote.
_KEYED = re.compile(r"(?i)\b((?:[A-Za-z0-9]+[_-])*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|key))"
                    r"(\"?\s*[=:]\s*)(\"[^\"\n]*\"?|'[^'\n]*'?|[^\s\"',;&]+)")
_PHONE_KEY = re.compile(r"(?<![\w.-])k=[^\s&#]+")  # the ?k= query key of the phone link
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CARD_PLAIN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
_CARD_GROUPED = re.compile(r"(?<!\d)\d{4}(?:[ -]\d{4}){3}(?!\d)")
_HOME = re.compile(r"/Users/[^/\s]+")
_OPAQUE = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{32,}={0,2}(?![A-Za-z0-9+/_-])")


def _opaque(match):
    """Keep git shas and words or paths without both a digit and a letter; mask the rest (hex, base64, tokens)."""
    run = match.group(0)
    if GIT_SHA1.fullmatch(run) or not re.search(r"\d", run) or not re.search(r"[A-Za-z]", run):
        return run
    return SECRET


def _keyed_mask(match):
    """Keep the name and the separator, mask the value; a quoted value keeps its quotes. Task ids pass."""
    value = match.group(3)
    if _TASK_VALUE.fullmatch(value.strip("\"'")):
        return match.group(0)
    if value[:1] in ("\"", "'"):
        quote = value[0]
        return match.group(1) + match.group(2) + quote + SECRET + quote
    return match.group(1) + match.group(2) + SECRET


def scrub(text):
    """Return text with secrets, credentials, e-mail addresses, card-like numbers and home paths masked."""
    out = "" if text is None else str(text)
    out = _PEM.sub(SECRET, out)
    for pattern in _VENDOR:
        out = pattern.sub(SECRET, out)
    out = _BEARER.sub(r"\1 " + SECRET, out)
    out = _KEYED.sub(_keyed_mask, out)
    out = _PHONE_KEY.sub("k=" + SECRET, out)
    out = _URL_CREDS.sub(lambda m: m.group(1) + SECRET + "@", out)
    out = _EMAIL.sub(EMAIL, out)
    out = _CARD_PLAIN.sub(NUMBER, out)
    out = _CARD_GROUPED.sub(NUMBER, out)
    out = _HOME.sub("~", out)
    return _OPAQUE.sub(_opaque, out)
