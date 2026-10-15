# UX audit R7.26 (2026-10-15)

*Italic* = ui-ux-pro-max guideline. Shots: `build/ui-smoke/alpha-<view>-<size>-dark.png` (cited `view@size`) and 5.webp.
**Stale** (14 Oct 20:19): workflow, overview, work-list/tree, research, rules, settings (no Logging), top bar (no R7.23 toggle), planner.

## 1. Per section

**Overview** (overview@1440, @500)
- M Three Stop controls (pill, top bar, banner). Checklist 9.
- M "This week: –", "0k", empty "Nothing queued ▸" cards. *Empty States*.
- M Activity Undo and `gui` tag wrap, no fixed columns. Rule 0.

**Inbox** (inbox@1440, @500)
- H Nav badge 1, panel ✉2, page 2 questions + 1 needs-you (nav.js counts needUser only). UI-SPEC §1.
- M Unequal answer widths; Needs-you row has no action. Rule 0, *Empty States*.
- M "Time expired; applying default" with no countdown or Undo. *Loading Indicators*, *Confirmation Messages*.

**Roadmap** (roadmap@1440, @500)
- H Approve floats above meta row; Up/Down mid-card on phone. Rule 0.
- M Up enabled on first card. *Disabled States*.
- M Done phases stay open; "spent – · no budget" repeats. *Empty States*.
- L Chevron ~10 px. *Target Size (Minimum)*.

**Planner** (5.webp): ragged Assign selects, "Blk/Acc" headers. H5 owns it; verify.

**Work** (work-board@1440, @500): 4 filter rows fill the phone screen (*Mobile First*); chip state by colour (*Color Only*); "Todo11"; dim strikethrough Done (*Contrast Readability*); key hint on touch. Fold into Work v2.

**Issues** (issues@1440)
- H No nav badge despite 1 blocker (countsFor). UI-SPEC §1.
- M New issue form always open. Checklist 8.
- L "1 blockers"; issue "Close" = panel "Close".

**Agents** (agents@1440, @500)
- H Running vs finished use different tracks (elapsed col 4 vs 1). Rule 0, *Table Handling*.
- M Running tokens bare "–". *Empty States*.
- M Phone: Stop floats mid-row. *Touch Friendly*.

**Tokens** (tokens@1440, @500)
- H No reading shown as red alarm; spec says grey unknown. *Color Only*.
- M Spend row: label above input, Save cap off-column. Rule 0, *Error Placement*.
- M Account meters empty bars with dashes. *Empty States*.

**Rules** (rules@1440)
- M "No rules in this group." no action. *Empty States*.
- M "Or phase:ID or task:ID" jargon; Budget field always shown; no *Inline Validation*.
- M Sync to CLAUDE.md shows no result. *Submit Feedback*.

**Research** (research@1440): L onboarding steps not links; "reload this page" beside Reload button.

**Activity** (activity@1440)
- M Raw op names ("resume", `gui`).
- M Undo on 10 h old row, no "what". *Confirmation Messages*.

**Settings** (settings@1440): M no Cmd-K mention, full-width button; L choice by outline colour (*Color Only*).

**Right panel** (overview@1440 dark/light)
- M Close filled in dark, outlined in light.
- M "2 ⑂5" icon numbers unlabelled. *Color Only*.
- L Uneven row heights. Rule 0.

## 2. Cross-cutting

- **Navigation:** phone bottom nav icons unlabelled; "⋯" near invisible (*Color Contrast*).
- **Empty values:** bare "–" in 10+ places; use one word, one sentence, one action.
- **Feedback:** every write must toast with Undo, aria-live (*Toast Notifications*).
- **Loading:** no skeleton/aria-busy on first paint (*Loading States*).
- **Errors:** no field errors with aria-describedby (*Error Placement*).
- **Focus:** no `:focus-visible` in shell.css, panel.css, planner.css (*Focus States*).
- **Touch/density:** sub-24 px chevrons; dead space on Agents, Activity.
- **Discoverability:** Cmd-K palette has no visible trigger; `log.mark()` has no button or key; copy refs in flight.

## 3. Plan block

```
P R8 todo | UX audit fixes
# A: now
T R8.1 todo 8 haiku/low | Issues nav badge for blockers # nav.js, tests/web
T R8.2 todo 6 haiku/low | Inbox badge = questions + needs-you # nav.js
T R8.3 todo 10 haiku/low | Phone bottom nav labels, More contrast # nav.js, shell.css
T R8.4 todo 10 haiku/low | Empty-value word for bare dash # overview.js, phases.js, agents.js, usage.js
T R8.5 todo 8 haiku/low | Overview: explain or hide empty cards # next.js, recent.js
T R8.6 todo 5 haiku/low | Overview: drop banner Stop # overview.js
T R8.7 todo 10 haiku/low | Activity: plain names, Undo says what, row-grid # activity.js, flow.css
T R8.8 todo 12 haiku/low | Agents: one row-grid, phone 2-line # agents.js, running.js, flow.css
T R8.9 todo 10 haiku/low | Roadmap: Approve column, Up/Down disabled at ends # roadmap.js, phases.js, plan.css
T R8.10 todo 6 haiku/low | Roadmap: collapse done phases, 24px chevron # phases.js, plan.css
T R8.11 todo 8 haiku/low | Tokens: grey unknown state # usage.js, tokens.js, admin.css
T R8.12 todo 10 haiku/low | Tokens: aligned Spend row, inline error # tokens.js, limits.js, admin.css
T R8.13 todo 10 haiku/low | Rules: empty action, budget field on demand, inline check # rules.js, admin.css
T R8.14 todo 5 haiku/low | Rules: Sync result toast # rules.js
T R8.15 todo 10 haiku/low | Inbox: equal options, Open action, countdown + Undo # inbox.js, needsyou.js, flow.css
T R8.16 todo 5 haiku/low | Research: steps link to sections # research.js
T R8.17 todo 6 haiku/low | Issues: plural, "Close issue" # issues.js
T R8.18 todo 10 haiku/low | First-load skeleton + aria-busy # dom.js, components.css
T R8.19 todo 6 haiku/low | Focus ring shell + panel # shell.css, panel.css
# B: wait
T R8.20 todo 10 haiku/low | Top-bar Cmd-K button, list in ? + Settings # topbar.js, palette.js, settings.js; after Logging commit
T R8.21 todo 8 haiku/low | Mark key + palette command # keys.js, palette.js; after R7.16
T R8.22 todo 8 haiku/low | Panel: one Close style, labelled counts, equal rows # panel.js, projects.js, panel.css; after R7.23
T R8.23 todo 6 haiku/low | Settings choice: check + aria-pressed # settings.js, components.css; after Logging commit
# C: verify spec'd work
T R8.24 todo 5 haiku/low | Verify Planner v2 rule 0 # planner.js; after H5
T R8.25 todo 5 haiku/low | Verify Work v2 filters, chip state, Done contrast # work.js, board.js; after Work v2
T R8.26 todo 5 haiku/low | Verify Issues form collapsed # issues.js; after Issues spec
T R8.27 todo 5 haiku/low | Verify map v2 labels, Show all # workflow.js; after map v2
```

## 4. UX audit routine (after every wave)

1. `make check-ui`; view changed views + right panel at 1440 dark, 1440 light, 500 dark; flag stale shots (mtime vs `git log`).
2. Skill queries (no `-I`): always empty states, focus, touch targets, color contrast; plus forms / error messages / drag and drop / loading / navigation as relevant.
3. Per view 2-4 problems: guideline + shot; skip in-flight work.
4. File as `T R8.<next>` with files and wait-for; `bin/roadmap plan import`; link feature; Haiku-sized (≤12K, one view).
5. agy (text-only, Haiku verifies): aria-labels, focus gaps, bare "–", plurals, jargon, row-grid use.
6. Opus medium or Cursor with screenshots: alignment, hierarchy, density, contrast, phone, light vs dark.
