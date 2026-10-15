| file:line | problem | fix |
|---|---|---|
| head.py:223 | `"ok %s. next: %s"` — "ok" and "next:" lowercase; inconsistent with sentence case | `"OK %s. Next: %s"` |
| head.py:227 | `"next: " + text` — "next:" lowercase; not a sentence | `"Next: " + text` |
| head.py:289 | `"logged, numbered after the next head write (spooled)"` — "numbered after" is awkward/ungrammatical | `"logged; number assigned on next head write (spooled)"` |
| head.py:291 | `"%s %s %s" % (data["id"], data["kind"], status)` — three nouns concatenated without prepositions | `"%s %s %s" % (data["id"], data["kind"], status)` → `"%s: %s %s" % (data["id"], data["kind"], status)` |
| head.py:316 | `"%s set %s"` — "set" as bare past participle; reads as imperative | `"%s: set %s" % (args.id, ...)` or `"%s fields set: %s"` |
| head.py:322 | `"%s bound %s"` — "bound" bare past participle; missing auxiliary | `"%s: bound %s" % (args.id, bound)` |
| head.py:328 | `"%s unbound %s"` — same issue | `"%s: unbound %s" % (args.id, removed)` |
| head.py:334 | `"%s split into %s"` — "split" bare past participle | `"%s: split into %s" % (args.id, into)` |
| head.py:339 | `"%s merged into %s"` — "merged" bare past participle | `"%s: merged into %s" % (args.id, args.into)` |
| head.py:358 | `"%s confirmed done"` — "confirmed done" ungrammatical; "done" not an object | `"%s: confirmed as done" % args.id` |
| head.py:364 | `"%s accepted"` — "accepted" bare past participle | `"%s: accepted" % args.id` |
| head.py:369 | `"%s verbatim forgotten"` — "forgotten" bare past participle; "verbatim" misplaced | `"%s: verbatim text forgotten" % args.id` |
| head.py:390 | `"import %d logged, %d skipped"` — "import" reads as verb but is noun; "logged/skipped" bare participles | `"imported: %d logged, %d skipped" % (len(logged), skipped)` |
| head.py:409 | `"ok claim %s, %d carried. next: %s"` — "ok"/"next:" lowercase; "carried" bare participle | `"OK: claimed %s, %d carried. Next: %s" % (model, len(carried), BRIEF)` |
| head.py:426 | `"no entries match (" + args.which + ")"` — "match" should be "matching" or "for" | `"no entries matching (%s)" % args.which` |
| head.py:492 | `"ok nothing pending"` — "ok" lowercase; fragment | `"OK: nothing pending"` |
| head.py:495 | `"continue: " + item` — "continue:" lowercase; not a sentence | `"Continue: " + item` |
| head.py:504 | `_ok("head paused: the gate stays silent", ...)` — "ok" lowercase in _ok output | (fixed by line 223 change) |
| head.py:514 | `_ok("head resumed" if was else "head was not paused", ...)` — same | (fixed by line 223 change) |
