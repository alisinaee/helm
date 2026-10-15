| file:line | cause | fix |
| --- | --- | --- |
| roadmap/services/head.py:132 | _append_entry_locked appends entry to head.jsonl via jsonl.append_line without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:136 | _append_entry_locked appends entry text to head-text.jsonl via jsonl.append_line without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:190 | _spool_append writes entry payload to head-spool.jsonl via fh.write without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:255 | _adopt_locked calls _append_entry_locked to adopt spooled entries without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:265 | _adopt_locked writes remaining spooled entries to head-spool.jsonl via fh.write without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:340 | update appends update record to head.jsonl via jsonl.append_line without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:358 | session appends session record to head.jsonl via jsonl.append_line without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:407 | set_reply appends reply to head-text.jsonl via jsonl.append_line without notifying snapshot consumers | UNKNOWN |
| roadmap/services/head.py:444 | forget_text rewrites head-text.jsonl via atomic.write_text without notifying snapshot consumers | UNKNOWN |
