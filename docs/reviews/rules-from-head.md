# Rules from Head (R7.103)

Review of the 41 rule-kind Head entries (H1 to H152, open and done). Read with `head list --kind rule` and the full
text in docs/head.jsonl. Nothing was proposed in the real data dir; the head runs `roadmap rules propose` after review.

## Proposed rules (plain words)

Each line: the rule, then its source Head ids.

1. Head never idles: start ready tasks now, and act on work the person already asked for. [H5, H11, H59, H91, H94, H95, H103]
2. Parallel workers only on disjoint file lists; file overlap is the only limit. [H4, H11]
3. Keep replies short; the person has few tokens. [H1]
4. Start a fresh session at about 70% context; `/head` resumes as head without re-tuning. [H9, H106]
5. Model roles: Haiku 5.5 does edits; Opus 5.5 low or medium does hard review; agy does read-only audits, verified;
   agy runs at max effort. [H3, H51, H99, H103]
6. Show the model and effort of every job on the Agents list. [H28, H46]
7. Register every job on the dashboard (job start and done). [H6, H59]
8. Workers never run usage sync, read the keychain, use the network, touch the person's dashboard tab or port 8780. [H7, H8]
9. UI rule 0: numbers and actions in fixed grid columns; review the UI after each wave with the ui-ux-pro-max skill. [H2, H16]
10. Head shows every captured item; lazy load must reach all of them. [H29, H30, H32, H34, H56, H133]
11. Every message from the person is captured in Head; the head checks each rule-kind item and proposes rules. [H19, H152]
12. No secrets in Head, the ledger or logs. [H23]

## Needs the person (to review, not a rule yet)

- Usage stop numbers conflict. H99 says go to 80% of the 5-hour limit; CLAUDE.md says 90%. H111 says the weekly stop is
  85%; CLAUDE.md says 95%. Ask which numbers stand; then add one usage rule.

## Small context, not worth a rule

- H10 split-net project rules: already in that project's memory.
- H12 Issues as Work cards, H14 Rules shows both projects, H17 side panel reopenable: done (R7.97 and others).
- H13 Tokens section stays simple: a UI spec, keep in the feature docs.
- H15 Git section, H21 GUI Head section, H22 auto-summarise and auto-suggest: feature specs, not rules.
- H45 search for tools with agy or cursor, H90 use the dashboard for progress, H91 start tasks with a reference,
  H140 diagram ask: one-off instructions, done or in the task list.
- H50 "do we really use gemini as default?": a question to the person, answer it in chat.
- H113 focus on roadmap-board, split-net paused: a status note for this session.
- H152 is the request that started this review; it is covered by rule 11.
