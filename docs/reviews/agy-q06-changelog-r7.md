| bullet | source file:line |
|---|---|
| Track session presence in state dir via presence-<hash>.json updated every 30s during watch polling or hook events | docs/R7.1-SPEC.md:14-16 |
| Display real-time session presence as "watching", "open", or "none" in the Run status | docs/R7.1-SPEC.md:17-21 |
| Offer a one-click button to copy the watch launch command when waiting for a session and include command in notifications | docs/R7.1-SPEC.md:21-22 |
| Support optional launchOnStart configuration to open Terminal with claude when no session is active (rate-limited to 10m) | docs/R7.1-SPEC.md:23 |
| Add copy reference buttons across all section headers and data rows to copy unique board refs and one-line status | docs/R7.12-SPEC.md:1 |
| Standardize board reference URI format rb:<project>/<kind>/<id> producing a concise two-line summary under 200 characters | docs/R7.12-SPEC.md:7-25 |
| Introduce roadmap ref <ref> CLI command returning structured item details in at most 10 lines | docs/R7.12-SPEC.md:34-38 |
| Align copy buttons in a fixed 1.5rem grid column with accessible fallback input when clipboard API is unavailable | docs/R7.12-SPEC.md:60-64 |
| Redesign workflow map with left-to-right progression from Start pill through collapsible phase frames to Now flag and End pill | docs/WORKFLOW-V2-SPEC.md:14-18 |
| Render orthogonal edges distinguishing sequence, dependency (after), handoff, and blocker connections | docs/WORKFLOW-V2-SPEC.md:22-26 |
| Display concurrent active tasks as stacked parallel branches and highlight current progress with a "You are here" flag | docs/WORKFLOW-V2-SPEC.md:27-34 |
| Provide an interactive 160x90 minimap with viewport overview, click-to-pan navigation, and keyboard shortcuts | docs/WORKFLOW-V2-SPEC.md:50-60 |
| Support inline adding and renaming of feature items in Planner ⋯ menu with Enter to save and Esc to cancel | docs/PLANNER-V2-SPEC.md:52 |
| Trigger an undo toast notification upon completing inline feature edits for rapid reversal | docs/PLANNER-V2-SPEC.md:52 |
| Organize Planner into a 3-level plan tree (phase > sub-plan > item) with parent chain depth ≤ 2 | docs/PLANNER-V2-SPEC.md:13 |
| Support feature reordering among siblings via feature.move operation and Move up/down menu actions | docs/PLANNER-V2-SPEC.md:14-52 |
| Tag user-requested features with ask: true ("you asked" badge) and preserve acceptance criteria until accepted | docs/PLANNER-V2-SPEC.md:15-48 |
| Derive dynamic outline numbering (P0, P0.0, P0.0.1), rollup gaps counts, and feature tree CLI output | docs/PLANNER-V2-SPEC.md:16-57 |
| Record structured JSON-lines debug log to <state dir>/logs/debug.jsonl with 5 MB × 3 rotation and 0600 permissions | docs/LOGGING-SPEC.md:19-20 |
| Strip auth tokens, cookies, CSRF tokens, query strings, and normalize home paths to ~ via built-in redaction | docs/LOGGING-SPEC.md:21 |
| Transport batched client logs via POST /api/v1/log guarded by CSRF checks, 16 KB body limit, and session rate limits | docs/LOGGING-SPEC.md:27-28 |
| Add roadmap logs CLI command to filter warnings/errors and header Mark button to record test checkpoints | docs/LOGGING-SPEC.md:34-47 |
| Provide right-side panel (<aside>) containing Projects overview and selection Details tabs | docs/facts/FACTS.md:739 |
| Open Details panel and activate focus mode upon clicking or tapping any workflow node or task | docs/WORKFLOW-V2-SPEC.md:52 |
| Dedicated side panel toggle button or hotkey outside item selection and routing: UNKNOWN | docs/HANDOVER.md:16 |
| Enforce UI Rule 0 aligning numbers and action buttons in fixed grid columns so layouts never shift | docs/HANDOVER.md:20 |
| Standardize Planner on a fixed 12-column grid keeping level indentation strictly inside the title cell | docs/PLANNER-V2-SPEC.md:36-47 |
| Allocate a fixed 1.5rem grid column on all row grids to maintain alignment across table rows | docs/R7.12-SPEC.md:64 |
| Align rows consistently across tokens and phases views (R7.5 A) | docs/facts/FACTS.md:788 |
| Harden web views, log endpoint, redaction, and rate limiting based on Cursor R3.6 and R3.7 reviews | docs/FINISH-PLAN.md:6-43 |
| Resolve 25 findings and 4 bugs across core, auth, and HTTP layers from security reviews R1, R2, and R3 | docs/HANDOVER.md:38 |
| Protect mutating endpoints with strict write guards checking CSRF header, Sec-Fetch-Site/Origin, and body caps | docs/LOGGING-SPEC.md:28 |
| Enforce fail-open PreToolUse hook blocking token limit overrides from agent shells | docs/HANDOVER.md:33 |
