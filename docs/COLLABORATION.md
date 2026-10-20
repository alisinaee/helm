# Working on Helm as a team

This page is for people who join the project: how to get access, run Helm on your own Mac, change it, and send
the change back. Rules for the code itself are in [CONTRIBUTING.md](../CONTRIBUTING.md). The design is in
[ARCHITECTURE.md](ARCHITECTURE.md).

Repository: https://github.com/alisinaee/helm (public).

## 1. Get access

The owner decides who may push. Two ways:

- **Collaborator (can push branches).** The owner opens the repository on GitHub, then Settings, Collaborators,
  Add people, and enters the GitHub user name. The person accepts the invite by e-mail.
- **Fork (no push access needed).** Anyone can fork the repository on GitHub, push to the fork and open a pull
  request.

The repository is public, so never commit a token, a key, a password or a customer's data. Claude logins stay in
the macOS keychain or in a `~/.claude-*` folder on your own Mac; they are not part of the repository.

Suggested GitHub settings for the owner (Settings, Branches): protect `main`, require a pull request and one
approval before merging.

## 2. Set up your own copy

You need macOS, Python 3.9 or newer, `make` and `git`. There are no packages to install.

```sh
git clone https://github.com/alisinaee/helm.git ~/Works/helm
cd ~/Works/helm
make check
```

`make check` must pass before you start, so you know a later failure is yours.

Run the dashboard on your own Mac with `bin/roadmap serve`. Each person has their own Helm, their own board data
and their own port. Helm does not share data between Macs.

## 3. Use your own Claude account

Helm reads usage for the Claude login you choose, so each person connects their own:

1. Log in once in a terminal. For a second account on the same Mac, give it its own folder:
   `CLAUDE_CONFIG_DIR=~/.claude-work claude auth login`.
2. Open Tokens, then Account. A logged-in `~/.claude-*` folder that Helm does not list yet shows up as
   "Found a logged-in account". Click **Add account**.
3. Click **Use** on the account you want. Only the active account is read live; the other keeps its last reading.

The usage stops (Tokens, then Limits) apply to the active account's numbers. If a stop blocks you by mistake,
check that the right account is active, then press **Sync now**.

Details: [USAGE-SOURCES.md](USAGE-SOURCES.md).

## 3b. Skills in the repository

The project skills live in `.claude/skills/` and travel with the repository, so Claude Code finds them when you
open the Helm folder (no copying into `~/.claude`):

| Skill | Use |
|---|---|
| `/helm` | everyone: set up Helm and ask how far to go. It never duplicates an existing setup. |
| `/head` | maintainer: resume from `docs/HANDOVER.md`, plan, run workers, verify, commit. `/head save` before you stop. `/head status` for a short state. |
| `roadmap-dashboard` | install and run the dashboard for a project, keep usage and jobs in sync |
| `roadmap-plan-new` | research first, then fill the board for a new project |
| `roadmap-update` | record task progress on the board |

If `/head` is "not found": open Claude Code in the Helm repository folder itself (the one that holds `bin/roadmap`),
pull the latest `main`, and start a new Claude Code session. Skills are read when a session starts.

`ui-ux-pro-max` (UI design search, used by the UI rules in `docs/UI-CHECKLIST.md`) is a third-party skill and is not
in the repository. Install it in your own `~/.claude/skills` if you do UI work.

`/head` writes your own board data and hooks, so run it in your own clone, not in someone else's.

## 4. The workflow

1. Start from the latest `main`: `git pull`, then `git switch -c <short-name>`.
2. Make a small change. One topic per branch.
3. Run `make check`. It runs the lint and every test. `make check-ui` runs the browser smoke test.
4. Update the doc that describes what you changed (README for users, API.md for routes, ARCHITECTURE.md for layout).
5. Commit with the area first, for example `accounts: list logged-in folders`. Keep the first line under 72
   characters.
6. Push the branch and open a pull request. Say what changed and how you checked it.
7. Someone else reviews. The author merges after the approval.

UI changes also follow [UI-CHECKLIST.md](UI-CHECKLIST.md): numbers and actions in aligned columns, content-sized
controls, no dead space.

## 5. Board files in `docs/`

The board files in `docs/` (`tasks.json`, `jobs.json`, `activity.jsonl`, `head*.jsonl`, `budget.json` and similar)
are local to each Mac. They are git-ignored, so they are never committed and never pushed.

- A fresh clone starts with an empty board. Run the setup skill `/helm`, or `bin/roadmap init`.
- If you cloned an older version and saw someone else's board, run `git pull`. Then remove that project from your
  board with `bin/roadmap project remove <id>`, typed by hand (it is not run by the docs check).
- Add your files by path (`git add <your files>`), never `git add -A`.

## 6. Where things are

| You want to | Read |
|---|---|
| Understand the layers and where code goes | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Add a command or an HTTP route | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Know the HTTP contract | [API.md](API.md) |
| Know the security rules | [SECURITY.md](SECURITY.md) |
| See the current state and open work | [HANDOVER.md](HANDOVER.md), section 0 |
| Check a UI change | [UI-CHECKLIST.md](UI-CHECKLIST.md) |

## 7. Rules that bite

- No dependencies outside the Python standard library (no npm, no CDN, no new fonts).
- Python 3.9 syntax only.
- Every test sets `ROADMAP_HOME` to a temporary folder. A test never touches your real board, keychain or network.
- Secrets never appear in output, logs or test failures.
- Do not run `roadmap service`, `usage sync` or `hooks install` from a script or a test; they change your real Mac.
