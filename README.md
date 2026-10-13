# roadmap-board

roadmap-board is a live roadmap dashboard and job tracker for Claude Code projects.
It reads each project's task and roadmap files, shows phases, running jobs and plan usage,
and serves the page on 127.0.0.1 only. The CLI is `roadmap`, and every command takes `--json`.
Everything is Python 3.9+ standard library, with no third-party packages.

Status: WP1 skeleton. Only `roadmap version` works; the other commands return `not_implemented`.

Run the checks:

```sh
make check        # Python and JavaScript lint, then unit tests
bin/roadmap version --json
```
