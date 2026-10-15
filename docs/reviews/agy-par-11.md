| file:line | problem | fix |
| --- | --- | --- |
| roadmap/core/secrets.py:18 | Matches sk- with hyphen, leaking Stripe secret and restricted API keys that use underscores (sk_live_, sk_test_, rk_live_). | Update regex to match r"\b[sr]k[-_][A-Za-z0-9_-]{16,}". |
| roadmap/core/secrets.py:22 | Only matches AWS IAM keys starting with AKIA, leaking AWS STS temporary credentials starting with ASIA. | Change pattern to r"\bA[KS]IA[0-9A-Z]{16}\b". |
| roadmap/core/secrets.py:26 | Only scrubs Bearer auth headers, leaking Basic authentication credentials (Authorization: Basic ...) and Token headers. | Change regex to r"(?i)\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]+". |
| roadmap/core/secrets.py:29 | Missing credential keywords like auth, authorization, creds, and credential, leaking assignments like auth = "...". | Add auth, authorization, and creds to the keyword alternation. |
| roadmap/core/secrets.py:30 | Key delimiter pattern (\"?\s*[=:]\s*) only handles double quotes, leaking single-quoted keys in Python dicts or YAML like 'password': '...'. | Change separator pattern to (['"]?\s*[=:]\s*). |
| roadmap/core/secrets.py:30 | Unquoted value pattern [^\s\"',;&]+ stops at whitespace, leaking multi-word passphrases or tokens containing spaces after the first word. | Match unquoted values up to line-end, semicolon, or comment delimiter. |
| roadmap/core/secrets.py:31 | Regex lacks case-insensitivity flag (?i), leaking phone link query keys passed with uppercase parameter K=. | Add (?i) flag to pattern: r"(?i)(?<![\w.-])k=[^\s&#]+". |
| roadmap/core/secrets.py:35 | Only matches 16-digit cards grouped as 4-4-4-4, leaking 15-digit American Express cards formatted in 4-6-5 blocks. | Add pattern matching 15-digit card grouping: r"(?<!\d)\d{4}[ -]\d{6}[ -]\d{5}(?!\d)". |
| roadmap/core/secrets.py:36 | Only matches macOS /Users/ paths, leaking Linux home directories (/home/<user>) and /root without replacing with ~. | Change pattern to r"(?:/Users|/home)/[^/\s]+|/root". |
| roadmap/core/secrets.py:43 | Exempts all 40-hex strings as git SHAs and all strings lacking digits or letters, leaking 40-hex secrets and alpha-only tokens. | Remove broad 40-hex exemption or verify commit context, and mask opaque strings regardless of digit presence. |
