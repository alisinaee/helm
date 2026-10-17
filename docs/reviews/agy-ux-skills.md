# UI/UX Review & Testing Skills for Claude Code (Haiku)

## Skill Comparison
| name | repo url | license | stars/last update | what it checks | fits vanilla JS? | install |
|---|---|---|---|---|---|---|
| **ui-ux-pro-max** | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | MIT | 136.4k / 2026-10-15 | 119 UX guidelines, 10 rule categories (contrast >=4.5:1, touch >=44px, spacing, layout shifts, tokens, forms, navigation) | Yes (use UX guidelines & references; skip palette/style generators) | Pre-installed at `~/.claude/skills/ui-ux-pro-max` |
| **web-design-guidelines** | https://github.com/vercel-labs/agent-skills | UNKNOWN | 32.5k / 2026-10-16 | Terse file:line lint: semantic HTML (<button> vs <a>), :focus-visible, aria-label on icon buttons, form attributes, touch targets | Yes (100% web standards & DOM checks, zero framework lock-in) | `npx skills add vercel-labs/agent-skills --skill web-design-guidelines` |
| **frontend-design** | https://github.com/anthropics/skills | UNKNOWN | 181.5k / 2026-10-16 | Aesthetic direction, distinctive typography, avoiding AI tropes (cream/terracotta/purple gradients); no automated audit checklist | No (generative/subjective; conflicts with custom design systems) | `npx skills add anthropics/skills --skill frontend-design` |
| **impeccable** | https://github.com/pbakaus/impeccable | Apache-2.0 | 81.8k / 2026-10-16 | 59 deterministic detector rules + LLM design critique/audit (visual hierarchy, alignment, contrast, spacing, anti-slop) | Partially (rules fit HTML/CSS, but full CLI setup adds token/tool overhead) | `npx impeccable install` |
| **accessibility-skills** | https://github.com/mgifford/accessibility-skills | AGPL-3.0 | 54 / 2026-10-15 | Comprehensive WCAG 2.2 AA audits (aria-live, contrast, keyboard, focus, touch-pointer, forms, tables) across 30+ skills | Yes (pure a11y standards, but excessive prompt overhead for Haiku) | `git clone https://github.com/mgifford/accessibility-skills.git` |

## Recommended Combo (Max 2)
1. **`ui-ux-pro-max` (offline)**: Authoritative UX interaction rules (touch >=44px, spacing >=8px, feedback/toasts, reduced motion, priority ordering) without network dependency.
2. **`web-design-guidelines` (Vercel)**: High signal-to-noise linter rules for semantic HTML, focus rings, keyboard accessibility, and terse `file:line` issue formatting.
*Why for Haiku:* Low prompt footprint, zero hallucinated aesthetic redesigns, strictly enforces existing vanilla CSS tokens and HTML structure.

## Haiku Worker Tester Recipe
### 1. Rules Files to Read
- `docs/UI-CHECKLIST.md` (Project authoritative rules 0–10, CSS budget <= 72 KB, `.row-grid` tracks).
- `~/.claude/skills/ui-ux-pro-max/references/quick-reference.md` (§1 a11y, §2 touch, §5 responsive layout, §8 forms).
- Vercel `command.md` rules (`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`).

### 2. Ordered Audit & Fix Sequence
1. **Rule 0 Row Alignment:** Verify every list/data row uses `.row-grid` (`web/css/components.css`) with fixed column tracks: chip, title (1fr, ellipsis), task, elapsed, tabular-nums tokens, fixed action. Run `pytest tests/web/test_rows.py`.
2. **Semantic HTML & Focus:** Ensure `<button>` for actions, `<a>` for navigation, `:focus-visible` ring on every control (never unstyled `outline: none`), `aria-label` on icon-only buttons, SVG sprite only (no emoji), form inputs have labels, `autocomplete`, no paste blocking.
3. **Design System & Tokens:** Verify no raw hex in `web/css/*.css` outside `tokens.css`. Run `python3 tools/contrast.py` (contrast >= 4.5:1). Check total CSS <= 72 KB (`wc -c web/css/*.css`).
4. **Interaction & Touch:** Targets >= 44x44 px (mobile) / >= 24 px (desktop), 8px+ spacing, toasts auto-dismiss in 3–5 s with Undo, drag has keyboard/button alternative (WCAG 2.2), `prefers-reduced-motion` respected.
5. **Multi-Viewport Screenshot Matrix:** Capture screenshots across 4 breakpoints and 2 themes (8 captures total):
   - Breakpoints: **500px** (mobile compact), **768px** (tablet/collapsed row), **1440px** (desktop standard), **2560px** (wide display).
   - Themes: **Dark** (`--force-prefers-color-scheme=dark`) and **Light** (`--blink-settings=preferredColorScheme=1`).
   - Command: `python3 tools/ui_smoke.py` (or headless Chrome `--window-size=W,H --screenshot=build/ui-smoke/<view>-<W>-<theme>.png`).
   - Visual checks: horizontal overflow (`overflow-x`), text clipping, row track alignment, contrast, and layout shift.
6. **Pre-Delivery Gate:** Confirm zero console errors, clean CSP, and test suite green (`pytest tests/web/test_shell.py tests/web/test_rows.py`).
