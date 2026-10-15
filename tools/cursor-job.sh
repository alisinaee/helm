#!/bin/bash
# Run one Cursor review and always close its job, even when the run is killed or fails.
# usage: tools/cursor-job.sh "<job title>" <effort> <outfile> "<prompt>"
cd /Users/ali/Works/roadmap-board || exit 1
jid=$(bin/roadmap job start "cursor: $1" cursor R7.31 --effort "$2" --engine-model grok-4.7-xhigh 2>/dev/null | awk '{print $NF}')
trap 'bin/roadmap job fail "$jid" >/dev/null 2>&1' INT TERM HUP
CURSOR_MODEL=grok-4.7-xhigh tools/cursor-review2.sh "$3" "$4"
rc=$?
if [ $rc -eq 0 ]; then bin/roadmap job done "$jid" --tokens 0 >/dev/null 2>&1; else bin/roadmap job fail "$jid" >/dev/null 2>&1; fi
exit $rc
