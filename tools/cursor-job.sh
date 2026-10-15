#!/bin/bash
# Run one Cursor review and always close its job, even when the run is killed or fails.
# usage: tools/cursor-job.sh <TASK> "<job title>" <effort> <outfile> "<prompt>"
# Old form without a task id first (title effort outfile prompt) still works and binds to R7.31.
# ROADMAP_ROOT overrides the project folder (tests use a stub folder).
cd "${ROADMAP_ROOT:-/Users/ali/Works/roadmap-board}" || exit 1
if [[ "$1" =~ ^[A-Z]+[0-9]+(\.[0-9a-z]+)*$ ]]; then
  task="$1"; shift
else
  task="R7.31"
fi
title="$1"; effort="$2"; out="$3"; prompt="$4"
jid=$(bin/roadmap job start "cursor: $title" cursor "$task" --effort "$effort" --engine-model grok-4.7-xhigh \
  2>/dev/null | awk '{print $NF}')
log=$(mktemp)
trap 'bin/roadmap job fail "$jid" >/dev/null 2>&1' INT TERM HUP
CURSOR_MODEL=grok-4.7-xhigh tools/cursor-review2.sh "$out" "$prompt" 2>"$log"
rc=$?
if [ $rc -eq 0 ]; then
  bin/roadmap job done "$jid" --tokens 0 >/dev/null 2>&1
else
  reason=$(grep -iE 'error|insufficient|403|cannot connect|failed' "$log" | head -n 1 | cut -c1-80)
  [ -n "$reason" ] || reason=$(grep -v '^[[:space:]]*$' "$log" | head -n 1 | cut -c1-80)
  bin/roadmap job fail "$jid" --reason "${reason:-exit $rc}" >/dev/null 2>&1
fi
rm -f "$log"
exit $rc
