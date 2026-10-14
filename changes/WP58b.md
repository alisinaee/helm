# WP58b: FACTS.md generator

- `tools/gen_facts.py` (stdlib) writes `docs/facts/FACTS.md`: command help for every top-level command (temp ROADMAP_HOME, CLAUDECODE unset, 2000-char cap each), HTTP routes, /cmd ops, cap constants, module tree with first docstring lines, data-file tables from ARCHITECTURE.md, last 30 commit subjects, UI checklist rules.
- Sorted and deterministic apart from the date line; hard cap 60 KB (the generator fails above it).
- `tests/unit/test_gen_facts.py`: every top-level command has a section, two runs match apart from the date, size cap, sections present.
- Known gap: most route handlers have no docstring, so their purpose column reads "-".
