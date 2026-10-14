# Release and cutover checklist

This is the checklist for roadmap-board 1.0.0 and for moving split-net from its old dashboard and `jobs_auto.py`
hooks to roadmap-board. Run the steps in order. Each step lists its rollback. Nothing here pushes or publishes: the
tag is yours to create when every step is done.

Paths: `<rb>` is the roadmap-board clone (for example `~/Works/roadmap-board`), `<split-net>` is the split-net project
folder (for example `~/Works/split-net`).

## 0. Pre-checks

1. `cd <rb> && make release-check`. It runs lint and the unit tests (`tools/check.py`), the Chrome UI smoke
   (`tools/ui_smoke.py`, which skips without Google Chrome), the documented commands (`tools/check_docs.py`), and a
   dry run of the skill install against a temporary folder. It must end with every stage ok.
2. `python3 -m unittest discover -s tests -t . -q` passes with no failures.
3. `git status` in `<rb>` is clean: every change is committed, nothing is staged by accident.
4. `roadmap doctor` shows no `fail` line. A `fail` on port 8765 is expected until step 3.

Rollback: none. These steps only read.

## 1. Register split-net

```sh
roadmap project init <split-net>
roadmap project add <split-net> --name "split-net"
roadmap project check split-net
```

`project init` writes the template data files only where they are missing, so existing `docs/` files stay as they are.
`project check` must print a schema version for each file and no error.

Rollback: `roadmap project remove split-net`. The files are kept.

## 2. Hooks, with the settings file backed up

Before the swap, note the settings file: `<split-net>/.claude/settings.local.json` holds the three `jobs_auto.py`
entries. Then run:

```sh
roadmap hooks install split-net --replace-legacy
roadmap hooks status split-net
```

`--replace-legacy` removes only the old `jobs_auto.py` entries. The reply has two fields to note: `backup`, the folder
where the old file was copied before the change, and `legacyRemoved`, how many old entries were removed. The backup is
kept under `~/Library/Application Support/roadmap-board/backups/split-net/<timestamp>/settings.local.json`. Running the
install again changes nothing.

Rollback: `roadmap hooks uninstall split-net`, then copy the backed-up file back over the original:
`cp <backup folder>/settings.local.json <split-net>/.claude/settings.local.json`.

## 3. Free port 8765 from the old dashboard

The old split-net server holds port 8765. roadmap's default port is 8780, so this step only matters if the old server
blocks 8765 and you choose to move roadmap onto 8765. While the old server holds it, `roadmap doctor` reports a `fail`
for the port, and the page cannot bind.

1. Find the process: `lsof -nP -iTCP:8765 -sTCP:LISTEN`. Write down its command line and pid.
2. If a launchd job or another tool starts it, stop it there first, so it does not come back.
3. Stop it: `kill <pid>`. Then `lsof` again must print nothing.

Decision needed before this step: `docs/GAP-ANALYSIS.md` (step 6) plans to keep the new service on 8780 and not move
roadmap onto 8765. If you keep 8780, set `"port": 8780` in the global config and skip the port part of this step.
Either way, the page and every bookmark must agree with the port you pick.

Rollback: start the old server again the same way you noted in step 1. Its data is untouched by roadmap.

## 4. Install the background service

```sh
cd <rb>
bin/roadmap service install
roadmap service status
roadmap doctor
```

`service status` must show the agent loaded and answering. `doctor` must show no `fail`.

Rollback: `roadmap service uninstall`. The launchd agent is removed. Data files are not touched.

## 5. Install the skills

```sh
cd <rb>
python3 tools/install-skills.py --dry-run
python3 tools/install-skills.py
```

The tool installs `roadmap-dashboard`, `roadmap-update` and `roadmap-plan-new` into `~/.claude/skills`. It checks each
draft and every `roadmap` command in it first. If a skill folder already exists, the run refuses. Re-run with `--yes`
only when you want the old folder moved aside: it is renamed to `<name>.bak-<timestamp>` before the new copy is written.

Rollback: delete `~/.claude/skills/<name>` and rename its `<name>.bak-<timestamp>` folder back to `<name>`.

## 6. Delete `web/legacy.html` (a separate change, after the cutover is stable)

This is not part of the 1.0.0 commit. `web/legacy.html` is still served at `/legacy.html`, with a CSP exception
(`CSP_LEGACY`), until this change lands. The files that refer to it are:

| File | What refers to it |
|---|---|
| `roadmap/http/static.py` | `LEGACY_FILE`; the `/` fallback to `legacy.html` when there is no `index.html` |
| `roadmap/http/security.py` | `CSP_LEGACY` and its `TODO(WP8)` comment (the only CSP exception) |
| `roadmap/http/server.py` | line 110: picks `CSP_LEGACY` for `entry.legacy` |
| `tests/api/support.py` | `REPO_LEGACY`, copied into each test web folder |
| `tests/api/test_static.py` | `test_legacy_page_gets_the_only_csp_exception`, `test_slash_falls_back_to_legacy_when_there_is_no_index` |
| `tests/web/test_assets.py` | excludes `legacy.html` from the source walk (line 56 to 57) |
| `tests/web/test_shell.py` | excludes `legacy.html` from the source walk (line 43) |
| `docs/API.md` | line 298, the temporary CSP exception for `/legacy.html` |
| `docs/SECURITY.md` | line 178, the CSP row that excepts the legacy page |
| `docs/ARCHITECTURE.md` | line 74, the file list |

Order: remove the code paths and the test support first (static, security, server, tests, docs), run
`make release-check`, then delete `web/legacy.html` in the same commit. The fallback code in `static.py` goes with it.

Rollback: `git revert` of that commit.

## 7. Version and tag

1. `roadmap/__init__.py` already reads `__version__ = "1.0.0"` in the 1.0.0 commit. Confirm with `roadmap version`.
2. In `CHANGELOG.md`, replace `- Unreleased` in the `## [1.0.0]` heading with the release date.
3. Create the tag locally: `git tag -a v1.0.0 -m "roadmap-board 1.0.0"`. Do not push it until you decide to.

Rollback: `git tag -d v1.0.0`. To undo the version, `git revert` the 1.0.0 commit.

## 8. Final check

- `roadmap service status` shows the agent answering on the port you chose.
- Open the page on that port. Split-net shows its phases and tasks, and the Overview shows the usage band.
- `roadmap hooks status split-net` shows the three roadmap entries and no `jobs_auto.py` entries.
- `roadmap job list --project split-net` shows the jobs from the next Claude Code run, and nothing is counted twice.

## Rollback summary

| Step | Undo |
|---|---|
| 1 Register | `roadmap project remove split-net` |
| 2 Hooks | `roadmap hooks uninstall split-net`, restore the backed-up `settings.local.json` |
| 3 Port | restart the old server the same way |
| 4 Service | `roadmap service uninstall` |
| 5 Skills | delete the new folders, rename the `.bak-<timestamp>` folders back |
| 6 legacy.html | `git revert` |
| 7 Tag | `git tag -d v1.0.0` |
