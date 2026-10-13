PY ?= python3

.PHONY: check check-ui check-all test

check:
	$(PY) tools/check.py

test:
	$(PY) -m unittest discover -s tests -t .

check-ui:
	@echo "not implemented yet"

check-all: check check-ui
