PY ?= python3

.PHONY: check check-ui check-all test release-check

check:
	$(PY) tools/check.py

test:
	$(PY) -m unittest discover -s tests -t .

check-ui:
	$(PY) tools/ui_smoke.py

check-all: check check-ui

# The release gate: lint and unit tests, the Chrome UI smoke, the documented commands, and a dry run of the skill install.
release-check:
	$(PY) tools/check.py
	$(PY) tools/ui_smoke.py
	$(PY) tools/check_docs.py
	T=$$(mktemp -d) && $(PY) tools/install-skills.py --dry-run --target "$$T/skills"; rc=$$?; rm -rf "$$T"; exit $$rc
