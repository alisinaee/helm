# CLAUDE.md for Helm (formerly roadmap-board; repo alisinaee/helm, dir ~/Works/helm; CLI `bin/helm` = `bin/roadmap`) (read docs/HANDOVER.md first)

> **mjp-labs Linux server (branch mahdi-remote-control):** this checkout is ~/StudioProjects/helm, served at
> https://helm.mjplabs.ir by `helm.service` (systemd --user). The board was emptied on 2026-10-19, so the
> HANDOVER/RUNBOOK history below is Ali's old Mac setup, kept for reference only. On `/head` follow
> `~/.claude/skills/head/SKILL.md` (source: deploy/linux/skills/head/SKILL.md): usage is read automatically, so do not
> ask for percentages; hooks are installed. Server details: deploy/linux/README.md.


You are continuing a project the person has been building across a very long chat. docs/HANDOVER.md has every feature, rule, decision, state and open item. Key rules in short:
- Answer short and spartan (the person has limited tokens and likes only the answer). Top-priority new feature: the HEAD section (docs/HEAD-SECTION-REQUEST.md, R7.31).
- NEW CHAT / NEW ACCOUNT: the person sends `/head` (skill in ~/.claude/skills/head). Then read docs/HANDOVER.md section 0 (state, WIP, queue), docs/HEAD-RUNBOOK.md, docs/FINISH-PLAN.md and act as the head: parallel workers on disjoint files, verify, register jobs (`bin/roadmap job start|done`), commit, push. FIRST ask the person for the current 5-hour and weekly usage % (hard stops: 5h 90%, weekly 95%; usage is not automatic here).
- UI rule 0: numbers and actions aligned in fixed grid columns; full-width UI; own design system; follow docs/UI-CHECKLIST.md.
- Head plans/verifies; Haiku 5.5 does edits; Opus 5.5 (medium/low) for design advice/review; Cursor Auto for reviews; agy (weak, unlimited) for audits only, always verified. Workers: strict file lists, stage own files by path, never run service/serve/usage sync/hooks install, temp ROADMAP_HOME, never touch port 8780 or the person's tabs.
- Weekly usage stop 95%; usage is pushed by hand (`bin/roadmap usage push`); keep the board in sync (see HANDOVER section 0).
- Tests: `python3 -m unittest discover -s tests -t . -q`; `make check`; `make check-ui`.
