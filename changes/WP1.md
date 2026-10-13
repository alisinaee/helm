# WP1: skeleton

- CLI skeleton: `bin/roadmap` shim, argparse command table, `--json` envelope, exit codes 0-6 and 10.
- `version` works. Every other command returns `not_implemented` (exit 1) until its package lands.
- `make check` runs the Python lint, the JavaScript lint and the unit tests.
