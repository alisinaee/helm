# UI/UX Review Skills & Haiku Tester Recipe

| name | repo url | license | stars/last update | what it checks | fits vanilla JS? | install |
|---|---|---|---|---|---|---|
| ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | MIT | ~135k / 2026-10 | Priority 1-10 UX/a11y/layout hierarchy (WCAG contrast, touch >=44px, no horiz scroll, form labels, focus rings, 119 UX guidelines) | Yes (pure markdown guidelines + local zero-dep python CLI) | Installed at `~/.claude/skills/ui-ux-pro-max` |
| web-design-guidelines | https://github.com/vercel-labs/agent-skills | MIT | ~34k / UNKNOWN | Web Interface Guidelines: a11y, focus rings, icon button aria-labels, textarea submit, tabular numbers, reduced motion | Yes (standards-based DOM/CSS linting; outputs terse file:line) | `npx skills add vercel-labs/agent-skills --skill web-design-guidelines` |
| frontend-design | https://github.com/anthropics/skills | Apache-2.0 / UNKNOWN | ~175k / UNKNOWN | Anti-slop creative design direction: custom 4-6 color palettes, distinctive fonts, asymmetric layout before code generation | No (generative tool for greenfield UIs; clobbers existing custom tokens/design systems) | `npx skills add anthropics/skills --skill frontend-design` |
| uxui-evaluator | https://github.com/uxuiprinciples/agent-skills | CC-BY-NC-SA-4.0 | UNKNOWN / UNKNOWN | 168 academic UX heuristics, user flow friction, cognitive load, interface smells | Partial (high-level heuristics fit, but actionable remediation needs paid API) | `npx skills add uxuiprinciples/agent-skills` |
| taste-skill | https://github.com/Leonxlnx/taste-skill | MIT | ~25k+ / UNKNOWN | Anti-slop design system generation, Awwwards-style aesthetics, typography pairings | No (generative for new apps; overrides existing design systems) | `npx skills add Leonxlnx/taste-skill` |

## Recommended Combo (Max 2)
1. **ui-ux-pro-max (UX domain subset)**: Local zero-token-overhead guidance for structural UX (WCAG contrast, touch targets >=44px, row alignment, responsive collapsing) via static references and local CLI without palette generation.
2. **web-design-guidelines (Vercel Labs)**: Lightweight web-standards checklist for micro-interaction and accessibility hygiene (visible focus rings, aria-labels on icon buttons, form submit states, tabular numbers, reduced-motion).

## Haiku Tester Recipe

### Rules Files to Read
1. `docs/UI-CHECKLIST.md` (local repo rules: Priority 0 row alignment, contrast >=4.5:1, touch targets >=44px, mobile-first, semantic tokens, SVG sprites, CSS <=72KB).
2. `~/.claude/skills/ui-ux-pro-max/references/quick-reference.md` (§1 a11y, §2 touch/interaction, §5 responsive layout).
3. On-demand search: `python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<topic>" --domain ux -n 3` (do NOT run `--design-system`).

### Checks & Execution Order
1. **Screenshot Matrix (8 States)**: Capture section screenshots across 4 widths (500px mobile, 768px tablet, 1440px desktop, 2560px ultrawide) in both `dark` and `light` themes.
2. **Step 1 - Row Alignment & Dead Space (Priority 0)**:
   - Measure `.row-grid` columns via `getBoundingClientRect()`.
   - Verify action and numeric columns align across cards and rows within <=2px delta.
   - Detect dead space (>40% unused width in numeric or title tracks).
3. **Step 2 - Responsive Layout & Overflow (Rule 5)**:
   - Verify `document.documentElement.scrollWidth <= clientWidth` at 500, 768, 1440, and 2560px (zero horizontal scroll).
   - Verify tables collapse into stacked cards at 500px while retaining visible field labels.
4. **Step 3 - Accessibility & Touch Targets (Rules 1 & 2)**:
   - Check text contrast >=4.5:1; verify visible `:focus-visible` rings on all interactive elements.
   - Assert all icon buttons have non-empty `aria-label`; verify `prefers-reduced-motion` compliance.
   - Ensure interactive touch targets are >=44x44px at 500px width with >=8px separation.
5. **Step 4 - Tokens, Icons & Hygiene (Rules 6, 7 & Limits)**:
   - Enforce `tabular-nums` on numbers; verify 0 raw hex values outside `web/css/tokens.css`.
   - Verify SVG sprites only (no emojis as UI icons); verify empty states have 1 sentence + 1 action.
   - Confirm browser console has 0 errors, CSP clean, and total CSS `wc -c web/css/*.css` <= 72 KB.
6. **Step 5 - Output Findings**: Format output table: `# | section | width | theme | rule | measured evidence | fix`.
