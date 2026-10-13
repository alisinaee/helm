# Security

**Status: draft.** This describes what roadmap-board protects, against whom, and how. Items marked *built* are in the
code and tested. Items marked *planned* come with WP13 (security hardening) and are not in the code yet. The review
gate at the end of this file (WP13/R1) must be signed before the 1.0.0 release (WP14).

## What is worth protecting

| Asset | Where | Why it matters |
|---|---|---|
| Claude Code sign-in (OAuth access token) | the login keychain, item `Claude Code-credentials`. roadmap reads it only for a usage read | it can act for your account |
| Plan usage numbers | `usage.json` in the state folder, and `docs/autonomy.json` in each project | they are not secret, but they drive your agents' stop rules |
| Project data | each project's `docs/` folder | it is your roadmap; roadmap reads it and writes only the job registry, usage mirror and migrations |
| Phone token (planned) | `~/.config/roadmap-board/phone.token` | it would open the dashboard from another device |
| Logs | `~/Library/Logs/roadmap-board/` | logs must never contain a token or a query-string secret |

## Who could attack it

1. **Another website in your browser** that makes requests to `127.0.0.1` (cross-site request forgery, or a page that
   tries to read the dashboard).
2. **A DNS-rebinding page**: a hostile name that resolves to `127.0.0.1` so the browser treats the server as the
   name's own origin.
3. **Other software on this Mac** that connects to the port. Anything running as you can read your files anyway, so
   the goal here is to keep the dashboard from becoming a way in, not to defend against code running as you.
4. **Content in a project**: task descriptions, job titles and hook input come from files and from Claude Code. They
   are data, and they are shown escaped.
5. **Someone on the network**: the server is not reachable from the network. Only the planned phone listener and its
   tunnel would be.
6. **Someone who reads your logs or your shell history.**

## Controls

### Built

- **Loopback only.** The server binds `127.0.0.1`. There is no option to change that.
- **Host allowlist.** Every request's `Host` must be `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets
  `421`. This is the DNS-rebinding guard.
- **CSRF token and same-origin check on the one write route.** `POST /api/v1/usage/sync` needs `Sec-Fetch-Site:
  same-origin` (or an `Origin` of this server), the `X-Roadmap-CSRF` token of this process (32 random bytes, compared
  in constant time), `Content-Type: application/json`, and a body of at most 4096 bytes. The token is served only in
  `<meta name="csrf">` on the HTML page.
- **Content Security Policy on every reply**: scripts and styles only from `'self'`, no framing (`frame-ancestors 'none'`), no
  `base-uri`, no `form-action`. `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Resource-Policy: same-origin`.
- **No file access from URLs.** Pages come from an allowlist built at start-up. A URL path is never turned into a
  file path, so `..`, encoded dots and double slashes give `404`.
- **No query strings in logs.** The access log writes method, path, status and time. Log lines also pass a redaction
  filter for `Bearer ...`, `sk-ant-...` and `k=...`.
- **The keychain token** is read by running `security find-generic-password -s "Claude Code-credentials" -w` as an
  argument list (no shell). It is held in memory for one request, is sent only in an HTTPS `GET` to
  `api.anthropic.com`, and redirects are refused. Failures carry a plain reason and the exception type, never the
  message of a library error, which could contain the token.
- **`doctor` does not read the secret.** It checks that the keychain item exists, without `-w`.
- **Files and folders are private.** Folders are created with mode 0700 and files with 0600. The launchd plist is
  0644 because launchd must read it, and it holds no secret.
- **Atomic writes and locks.** Data files are written through a temp file and `os.replace`, under a directory lock, so
  a crash cannot leave a half-written file, and two writers cannot interleave.
- **Newer files are never overwritten.** A data file written by a newer roadmap-board gives an error and is left alone.
- **Hooks never fail a tool call.** The hook entry prints nothing and exits 0, whatever it reads.
- **Subprocesses are argument lists.** `shell=True` is refused by the lint. Only `services/` runs subprocesses.
- **Standard library only.** No third-party code runs in the server or the CLI.

### Planned (WP13)

- **Phone listener** on `127.0.0.1:8766`, read-only (GET routes only), and only with a token. Without
  `phone.token` it answers `503`.
- **Phone token** from `secrets.token_urlsafe(32)`, file mode 0600, rotated on `roadmap phone start`, deleted on
  `roadmap phone stop`.
- **Cookie** holds `HMAC(token, "cookie")`, not the token. Attributes: `HttpOnly; Secure; SameSite=Strict`, seven
  days. A `?k=` parameter is removed by a redirect after it is used.
- **Rate limit**: 10 failed attempts per minute per process.
- **Tunnel**: `ssh -R 80:127.0.0.1:8766 nokey@localhost.run`, with its pid in the state folder. The tunnel host is
  the only extra allowed `Host` value, and only on the phone listener.
- **Write routes need all of the rules** above on the phone listener too. The phone listener has no write routes.

## Known limits

- The usage endpoint and its beta header are not a documented public API. A change on Anthropic's side fails the read
  with a plain reason; it cannot widen what roadmap sends.
- Hook jobs are inferred from tool calls and output file names. A wrong guess shows a wrong job; it cannot change any
  project file other than the job registry (`jobs.json`) and the usage mirror.
- The keychain prompt is the operating system's. Choosing Always Allow lets the `security` tool read that item without
  asking again. Revoke it in Keychain Access if you no longer want the usage feature.
- A process running as you can read the same files. roadmap does not add a boundary between you and your own code.

## Reporting a problem

If you find a way to read the token, to make a write the user did not ask for, to reach the server from another host, or
to get a secret into a log or a reply, please report it to the maintainer privately, not in a public issue. Include the
version (`roadmap version`), the request or command, and what you saw. Do not include your token or your keychain
entry. If a secret has already leaked, rotate it in Claude Code first, then report.

---

## Review checklist (WP13/R1)

_To be filled by the WP13 review at gate R1. Nothing here is signed yet. Each row needs a result and the name of the
reviewer before WP14 starts. No merge until the review is signed._

Expected results come from the WP13 acceptance tests in `tests/api/test_security.py`.

- [ ] Foreign `Host` gives 421 on every route (pending)
- [ ] A write without `X-Roadmap-CSRF` gives 403 (pending)
- [ ] A cross-site `Sec-Fetch-Site` gives 403 (pending)
- [ ] A phone-listener request without the token gives 401 (planned, pending)
- [ ] `?k=` never appears in `server.log` (pending)
- [ ] The phone token never appears in CLI output, logs or replies (planned, pending)
- [ ] The keychain secret never appears in CLI output, logs or replies (pending)
- [ ] Every header in the CSP list is sent on every reply, including errors (pending)
- [ ] Reviewer: __________   Date: __________   Result: __________
