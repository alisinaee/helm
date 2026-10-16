# Contributing

Thanks for working on Helm. This file says how to check a change, what the rules are, and what "done" means.
The design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The HTTP contract is in [docs/API.md](docs/API.md).

## Setup

You need macOS, Python 3.9 or newer, and `make`. Nothing else. There are no packages to install and no
network access is needed for the checks.

```sh
git clone <this repo> ~/Works/helm
cd ~/Works/helm
make check
```

## The checks

| Command | What it runs | Status |
|---|---|---|
| `make check` | `tools/check.py`: the Python lint, the JavaScript lint, then every unit, API and web test (`unittest discover`) | must pass before every commit |
| `make test` | the tests only, without the lint | for a quick loop |
| `make check-ui` | the Chrome smoke test (`tools/ui_smoke.py`) | not built yet (WP9); prints "not implemented yet" |
| `make check-all` | `check` and `check-ui` | after `check-ui` exists |

`make check` includes `tests/unit/test_docs.py`, which runs `tools/check_docs.py`. That tool runs every
`roadmap ...` line that the docs show, so a documented command that is unknown or broken fails the build.

To run only the docs check, use `python3 tools/check_docs.py`. It prints each command it ran and its result.

### What the lint checks

`tools/lint_py.py` (stdlib only, no third-party tools):

- every file compiles, has a module docstring, uses LF line endings and ends with a newline;
- lines are at most 120 columns;
- imports are standard library or `roadmap`, `tests` or `tools`;
- the layering rule holds: `core` imports nothing from the project; `store` imports only `core`, `errors` and `log`;
  `services` imports `store` and `core`; `http` and `commands` import `services`. The table is in
  `ARCHITECTURE.md`;
- no `shell=True`;
- `subprocess` is used only in `roadmap/services/`;
- no bare `except:` outside `roadmap/commands/hook.py`;
- no `print()` outside `roadmap/commands/` and `roadmap/cli.py`.

`tools/lint_js.py` checks the web code: no `var`, no `innerHTML` outside `web/js/dom.js`, no `console.log`, no
`eval` or `Function`, lines at most 120 columns. It also runs `node --check` when `node` is installed.

`tests/web/test_assets.py` checks the page: every file a page refers to exists, every JavaScript import resolves,
the markup has no inline `<script>`, no `on*=` attributes and no `style=` attributes (the Content Security Policy
forbids them), every `var(--x)` is defined in `web/css/tokens.css`, and no colour appears outside that file.

`tools/contrast.py` checks the contrast of every text and surface pair in light and dark themes: 4.5:1 for text,
3:1 for borders and meters.

## Rules

- **No dependencies.** The code uses the Python standard library only. A new import from outside it is a rejected
  change, not a discussion. The same goes for npm packages, CDN scripts and fonts from other hosts.
- **Python 3.9.** macOS ships 3.9 in `/usr/bin/python3`. Do not use `match`, `X | Y` type hints or other
  newer syntax. Use `typing` names or no annotations.
- **Layering.** Put code in the lowest layer that can hold it. A pure function that takes text and returns data
  belongs in `core/`. Anything that touches files goes in `store/` or `services/`. The HTTP layer and the CLI
  command modules are thin: they parse input, call a service and format the reply.
- **`cli.py` is a fixed table.** Each command group is a module in `roadmap/commands/` with a
  `register(sub, common)` function, and its name is listed in `COMMAND_MODULES` in `roadmap/cli.py`. The list already
  names every group. Do not add commands to `cli.py` itself.
- **Every test sets `ROADMAP_HOME`.** Tests must never touch the real config, state, logs, keychain, launchd or
  network. Use the fakes that the existing tests use: a fake `security` runner, a fake `launchctl` runner, a fake
  HTTP opener. `ROADMAP_LAUNCH_AGENTS` points the plist at a temporary folder.
- **Plain words in messages.** A message says what happened and what to do, in words a person outside the code can
  follow. Errors are `RoadmapError(code, message, exit)`; the code is stable and the message may change.
- **Secrets never reach output.** No token, key or keychain value appears in a message, a log line, a reply or a
  test failure. A test that checks this uses a fake token and asserts that it is absent from every output.
- **Writes are atomic and locked.** Use `store/atomic.write_json` for JSON and `store/lock.locked` around the
  read-change-write. Re-read the file inside the lock.
- **Schema versions.** A data file keeps its `schemaVersion`. A change to a file's shape comes with a migration in
  `store/migrations.py` and a test for it. A file newer than the code is refused, never overwritten.
- **Within v1 of the API, only add fields.** Existing keys do not change name or meaning. New keys are snake_case.
- **Docs commands are checked.** In README, CONTRIBUTING and `docs/*.md`, a line in a ```` ```bash ```` block that
  starts with `roadmap ` is run by `tools/check_docs.py`. Commands that touch launchd, the keychain, the network, a
  live port or stdin are run with `--help` only; the list is `HELP_ONLY` in `tools/check_docs.py`. Use the
  placeholder `<project-path>` for a project folder. Show examples that are not meant to run in another block
  language or inline.
- **Write what you change.** A change to a command, a route, a file or a setting updates the doc that describes it
  (README for users, API.md for routes, ARCHITECTURE.md for layout, SKILL draft for the skill).

## Definition of done

A change (a work package, or any other change) is done when all of these hold:

1. `make check` passes, with the new tests counted in the output.
2. Only the files the package lists have changed. `git status` shows nothing else.
3. No import from outside the standard library was added.
4. A change fragment exists: `changes/WPn.md` (or the package's name), see below.
5. Any command, route or file that changed is described in the doc that covers it, and `python3 tools/check_docs.py`
   passes.
6. The result of the acceptance command is pasted into the job note (`roadmap job done <id> "<summary>"`).

## Change fragments and the changelog

Each work package writes one fragment, `changes/WPn.md`, in plain Markdown: a short title and a bullet list of what
changed, one line each. Fragments are not edited by other packages.

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The release package merges the
fragments into a version section and keeps the fragments. Until a release, the fragments are merged under
`## [Unreleased]`. Parallel workers never edit `CHANGELOG.md` together.

Versions follow [SemVer](https://semver.org/). `roadmap/__init__.py` holds `__version__`, the single source. Tags are
`vX.Y.Z`.

## Adding a command

1. Write the logic in `services/` (or `core/` if it is pure). Return data or raise `RoadmapError`.
2. Add a module in `roadmap/commands/` with `register(sub, common)`. Give every subcommand `parents=[common]` so it
   takes `--json`, and add `--project` where the command acts on a project.
3. Print in plain mode and return data in `--json` mode. Return `None` from a handler that prints its own output.
4. Add tests in `tests/unit/test_<name>.py`: the service logic, and the command through `cli.main` with
   `ROADMAP_HOME` set to a temporary folder.
5. Add the command to the README command table, and to `HELP_ONLY` in `tools/check_docs.py` if it touches the
   machine outside its own folder.

## Adding an API route

1. Add the handler and its table row in `roadmap/http/routes.py`. A read route never writes. A write route runs
   `_write_guard` before anything else.
2. Add a schema in `tests/api/schemas/` and a test in `tests/api/test_routes.py`.
3. Describe the route and an example reply in `docs/API.md`.

## Adding a project extra or detector

- An extra is a parser in `roadmap/core/extras.py` and a registry entry. The config names the file.
- A hook detector is a class in `roadmap/services/hooks.py` with `on_tool` and `reap`, added to `DETECTORS`. A
  project turns it on with `hookDetectors`. Test it with a sample hook JSON, sent through `run_hook`, in
  `tests/unit/test_hooks.py`.

## Commit messages

Start with the package or area: `WP12: docs and skill draft`, or `http: reject foreign Host with 421`. Keep the
first line under 72 characters, and explain the why in the body when it is not obvious.
