PY ?= python3

.PHONY: check check-ui check-all test

check:
	$(PY) tools/check.py

test:
	$(PY) -m unittest discover -s tests -t .

check-ui:
	$(PY) tools/ui_smoke.py

check-all: check check-ui
