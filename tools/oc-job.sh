#!/bin/bash
# Run one OpenCode job and always close its job, even when the run is killed or fails.
# usage: tools/oc-job.sh <TASK> "<job title>" <effort> <outfile> "<prompt>"
# OC_MODEL picks the OpenCode model (default opencode/big-pickle). ROADMAP_ROOT overrides the project folder.
[ $# -eq 5 ] || { echo "usage: tools/oc-job.sh <TASK> \"<job title>\" <effort> <outfile> \"<prompt>\"" >&2; exit 2; }
cd "${ROADMAP_ROOT:-/Users/ali/Works/roadmap-board}" || exit 1
task="$1"; title="$2"; effort="$3"; out="$4"; prompt="$5"
model="${OC_MODEL:-opencode/big-pickle}"
jid=$(bin/roadmap job start "opencode: $title" opencode "$task" --effort "$effort" --engine-model "$model" \
  2>/dev/null | awk '{print $NF}')
log=$(mktemp)
trap 'bin/roadmap job fail "$jid" >/dev/null 2>&1' INT TERM HUP
opencode run -m "$model" "$prompt" >"$out" 2>"$log"
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
