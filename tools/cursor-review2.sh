#!/bin/bash
# Read-only Cursor review with the PINNED working CLI (2026.08.04; 2026.10.01 returns empty output for tool-using prompts).
# usage: tools/cursor-review.sh <outfile> "<prompt>"   -> writes the final answer text; exit 0 only if >= 100 bytes. One run at a time.
V="$HOME/.local/share/cursor-agent/versions/2026.08.04-aaa8809/cursor-agent"
[ -x "$V" ] || { echo "pinned cursor-agent missing: $V" >&2; exit 2; }
cd /Users/ali/Works/roadmap-board
while pgrep -f "cursor-agent.*-p" >/dev/null; do sleep 5; done
raw=$(mktemp)
"$V" -p --trust --mode plan --model auto --output-format stream-json "Do NOT create any plan, report or markdown file and do not use any report or plan tool: your FINAL CHAT MESSAGE must itself contain the full findings list. $2" </dev/null > "$raw" 2>&1
python3 - "$raw" "$1" <<'P'
import json,sys
txt=''
for l in open(sys.argv[1]):
    try: e=json.loads(l)
    except Exception: continue
    # Keep ALL assistant text (the findings may sit in a message before the final short summary), then the result line if longer.
    if e.get('type')=='assistant':
        txt+=''.join(c.get('text','') for c in e.get('message',{}).get('content',[]) if c.get('type')=='text')+'\n\n'
    elif e.get('type')=='result' and e.get('result') and len(e['result'])>len(txt): txt=e['result']
open(sys.argv[2],'w').write(txt)
sys.exit(0 if len(txt)>=100 else 1)
P
code=$?; rm -f "$raw"; exit $code
