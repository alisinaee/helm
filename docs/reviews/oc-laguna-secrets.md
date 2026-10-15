| file:line | problem | fix |
|-----------|---------|-----|
| secrets.py:36 | `/Users/[^/\s]+` masks macOS home paths only; leaks `/home/`, `/root` | Add `/(?:home|root)/[^/\s]+` or broaden to `(?:/Users|/home|/root)/[^/\s]+` |
| secrets.py:22 | `AKIA[0-9A-Z]{16}` matches permanent IAM keys only; leaks AWS STS temp keys (`ASIA…`) | Add `ASIA` or broaden to `(?:AKIA\|ASIA)[0-9A-Z]{16}` |
| secrets.py:26 | `_BEARER` matches `Bearer` scheme only; short `Basic` base64 tokens (<32 chars) also slip past `_OPAQUE` | Add Basic/Digest scheme patterns or lower `_OPAQUE` min from 32 |
| secrets.py:43 | `_opaque()` keeps runs with no digit (`not re.search(r"\d", run)`); all-letter 32+ char tokens leak | Drop the no-digit early-return or mask regardless |
| secrets.py:24 | JWT regex requires `{8,}` chars per segment; very short JWTs not matched | Lower min segment length or use a generic 3-segment `eyJ….eyJ….` pattern |
| secrets.py:32 | `_URL_CREDS` requires `://` scheme; `user:pass@host.com` without scheme leaks | Add a scheme-less `user:pass@host` variant |
| secrets.py:29 | Credential-word alternation lacks `passphrase`; `passphrase=value` leaks | Add `passphrase` to the alternation |
| secrets.py:29 | Alternation lacks OAuth `code`; `code=value` leaks | Add `code` to the alternation |
| secrets.py:29 | Alternation lacks `credentials`; `credentials=value` leaks | Add `credential` to the alternation |
| secrets.py:29 | camelCase keys (`secretKey`, `dbPassword`, `apiKey`) not matched — `(?:[A-Za-z0-9]+[_-])*` requires `_`/`-` before the credential word | Allow camelCase via alternation with explicit long-form names or relaxed separator logic |
| secrets.py:17 | `_VENDOR` tuple has no Slack webhook URL pattern; `hooks.slack.com/services/...` leaks | Add a Slack webhook URL pattern to `_VENDOR` |
| secrets.py:35 | `_CARD_GROUPED` matches 16-digit 4×4 groups only; 15-digit Amex (`1234 123456 12345`) leaks | Add Amex 4-6-5 grouping pattern or extend card regex |
