# CLAUDE.md for roadmap-board (read docs/HANDOVER.md first)

You are continuing a project the person has been building across a very long chat. docs/HANDOVER.md has every feature, rule, decision, state and open item. Key rules in short:
- Answer short and spartan (the person has limited tokens and likes only the answer).
- No workers/agents/agy/Cursor/Opus jobs run now: the person said STOP. Start tasks only when asked.
- UI rule 0: numbers and actions aligned in fixed grid columns; full-width UI; own design system; follow docs/UI-CHECKLIST.md.
- Head plans/verifies; Haiku 5.5 does edits; Opus 5.5 (medium/low) for design advice/review; Cursor Auto for reviews; agy (weak, unlimited) for audits only, always verified. Workers: strict file lists, stage own files by path, never run service/serve/usage sync/hooks install, temp ROADMAP_HOME, never touch port 8780 or the person's tabs.
- Weekly usage stop 95%; usage is pushed by hand (`bin/roadmap usage push`); keep the board in sync (see HANDOVER section 0).
- Tests: `python3 -m unittest discover -s tests -t . -q`; `make check`; `make check-ui`.
