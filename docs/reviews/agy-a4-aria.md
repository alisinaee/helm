# Job staffer-mv7n573e-3ad6d5f5 (staffer, done)

| file:line | element | accessible name present? (text, aria-label or labelledby) | aria-expanded/aria-controls present if it toggles? | problem |
|---|---|---|---|---|
| [limits.js:170](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L170) | `<button>` (`.btn`) | Yes (`+ Add limit` text) | No | Toggles add preset buttons (`addOpen`), but lacks `aria-expanded` and `aria-controls` |
| [nav.js:77](file:///Users/ali/Works/roadmap-board/web/js/views/nav.js#L77) | `<button>` (`.nav-collapse`) | Yes (`aria-label` and text) | No | Toggles navigation rail between mini and full (`ui.navMini`), but lacks `aria-expanded` and `aria-controls="nav"` |
| [topbar.js:22](file:///Users/ali/Works/roadmap-board/web/js/views/topbar.js#L22) | `<button>` (`.crumb-proj`) | Yes (project name + `.sr-only` text) | No | Toggles side panel open/closed (`ui.panelOpen`), but lacks `aria-expanded` and `aria-controls="side"` |

**OK elements count:** 124

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  M README.md
   M docs/autonomy.json
   M tools/ui_smoke.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
