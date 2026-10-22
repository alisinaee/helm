# Helm design system (R12.1 proposal)

Status key: **[exists]** already in `web/css/tokens.css`, `components.css` or `web/icons.svg`; **[proposed]** new, not wired into the app. Preview: `docs/ux/design-preview.html` (open from file://).

## Palette
The table is the classic palette (`:root` dark, `:root[data-mode="light"]` light). Each of the 3 palettes has its own light mode (see Themes below). All **[exists]**; no new hues.

| Role | Token | Dark | Light |
|---|---|---|---|
| Page | `--surface-0` | #0e1116 | #f4f5f7 |
| Card | `--surface-1` | #161b22 | #ffffff |
| Raised / hover | `--surface-2` | #1e2530 | #e9ecf1 |
| Border | `--line` | #78839a | #7b8496 |
| Track / divider | `--track` | #2b3342 | #d5dae3 |
| Text primary | `--text-1` | #e6e9ef | #15191f |
| Text secondary | `--text-2` | #b4bcca | #3d4553 |
| Text muted | `--text-3` | #97a1b3 | #566072 |
| Accent | `--accent` | #8ab4ff | #1d4fd1 |
| On accent | `--on-accent` | #0e1116 | #ffffff |
| Focus ring | `--focus` | #8ab4ff | #1d4fd1 |
| Success | `--success` | #6fd6a0 | #13703a |
| Warning | `--warning` | #f2be5c | #7a4d00 |
| Danger | `--danger` | #ff8a8a | #b3261e |
| Info | `--info` | #86cdf5 | #0a5f8f |
| Defer | `--defer` | #c4aeff | #5b3fb8 |
| Unknown | `--unknown` | #8b94a6 | #5f6878 |
| Model haiku | `--m-haiku` | #7fe0d0 | #0b6b5f |
| Model sonnet | `--m-sonnet` | #9bb8ff | #1f4fa8 |
| Model opus | `--m-opus` | #f0a0ff | #8a2b9e |
| Model cursor | `--m-cursor` | #ffd08a | #7a4a00 |
| Model agy | `--m-agy` | #a6e88a | #3d6e12 |

Also **[exists]**: `--scrim`, `--sel`, `--drop`, shadows, spacing `--sp-*`, radii `--r-control` 10px / `--r-card` 14px.

## Buttons
- **[exists]** `.btn` (default), `.btn-primary` (accent fill, `--on-accent` text), `.btn-small` (24px), `.btn[aria-pressed="true"]`, `:disabled`.
- **[proposed]** `.btn-ghost` (transparent, no border until hover), `.btn-danger` (`--danger` text and border, fills on hover), `.btn-icon` (square, icon only).
- Sizes: small 24px (`--h-small`), control 28px (`--h-control`), touch 44px on phone (`max-width: 700px`).
- States: hover = `--surface-2` background; `:focus-visible` = 2px `--focus` outline, 2px offset; active = scale 0.98; disabled = `--text-3`, no pointer, no hover; pressed = `aria-pressed="true"` (accent text + border).
- **[proposed]** Loading: while an async action runs, the button is `disabled` (no double submit), keeps its width, and shows the 16px spinner in place of its icon, with the label kept or "Saving…". It re-enables when the request settles (success or error). Source: ui-ux-pro-max "Loading Buttons" (High).
- Icon-only buttons must have `aria-label` (and a `title` where useful). Icon next to a label is `aria-hidden`.
- Destructive actions use danger and need confirm or undo.

## Icons
- **[exists]** sprite `web/icons.svg`, 24x24 grid, stroke 2px, round caps and joins, `currentColor`, symbols carry no fill or stroke; consumer CSS sets `fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round`.
- Sizes: 16 (dense rows), 20 (buttons, default), 24 (nav, headers).
- Usage: `<svg class="i" aria-hidden="true"><use href="#i-x"/></svg>`.
- One icon per action across the app (trash = delete, x = close or dismiss, refresh = reload, edit = rename or modify). No emoji as icons.
- **[proposed]** 22 new ids: i-play, i-pause, i-stop, i-refresh, i-plus, i-x, i-search, i-filter, i-edit, i-trash, i-undo, i-arrow-up, i-arrow-down, i-chevron-right, i-external, i-bell, i-link, i-lock, i-warning, i-info, i-error, i-clock. (Added to the sprite; unused by the app until wired.)
- Status icons pair with colour: warning/info/error/check/clock, never colour alone.

## Motion
- Durations: fast 120ms (`--t-fast` **[exists]**), base 180ms, slow 260ms **[proposed]**.
- Easing: `cubic-bezier(.2,.8,.2,1)` **[proposed]** for all transitions.
- Hover and colour changes: fast. Panels, menus: base. Toast slide-in, sheet open: slow.
- Press: `transform: scale(.98)` on `:active`. Spinner: 1s linear rotate. Toast: translateY(12px) + fade in.
- Every animation and transition is disabled under `@media (prefers-reduced-motion: reduce)` (state still changes, instantly). Spinner becomes a static icon plus text "Loading".

## Rules
- No raw hex or rgb outside `tokens.css`; use tokens.
- Text contrast at least 4.5:1 against its surface (tokens already meet this in both themes); UI borders and icons at least 3:1.
- Status is never colour alone: pair with an icon, text label or shape.
- Touch targets at least 44px on phone; at least 24px with spacing on desktop.
- Visible `:focus-visible` ring on every interactive element; never `outline: none` without a replacement.
- Layout: 16px gutter on phone, no horizontal scroll at 375px.
- Wiring plan (later task): add `.btn-ghost/.btn-danger/.btn-icon` and motion tokens to `tokens.css`/`components.css`, then migrate pages one by one.

## Themes
3 palettes x 2 modes = 6 looks. Two attributes on `<html>`, set by JS:
- `data-theme`: `obsidian` (Obsidian & Lime, the default), `classic` (the blue look, `:root`), `black` (plain black, flat glass).
- `data-mode`: `dark` (default) or `light`. `auto` (match system) is resolved by JS, so the CSS only sees dark or light.

Selectors in `web/css/tokens.css`: `:root` = classic dark; `:root[data-mode="light"]` = classic light; `:root[data-theme="obsidian"]` and `...[data-mode="light"]`; `:root[data-theme="black"]` and `...[data-mode="light"]`. With no JS, `@media (prefers-color-scheme: light) { :root:not([data-mode]) }` gives classic light. `web/css/glass.css` softens the obsidian glow on light and makes `black` flat (no blur, no colour fields, 1px edges). `python3 tools/contrast.py` checks all 6 looks (text 4.5:1, line and focus 3:1).

## Theme: Obsidian & Lime
Status: **[exists]** in `web/css/tokens.css` and `glass.css`, dark and light (light: `--accent` #4d6600 on warm white #f2f4ea). The dark values are below. Preview: section "Obsidian & Lime" in `docs/ux/design-preview.html` (`[data-theme="obsidian"]` token block). No external font link: Space Grotesk and JetBrains Mono are stacks with system fallbacks (Helm is local-first, no network assumed).

| Role | Token | Value | Spec |
|---|---|---|---|
| Shell / page | `--surface-0` | #000000 | same |
| Obsidian card | `--surface-1` | #0c0c0c | same |
| Raised / hover | `--surface-2` | #1a1a1a | added |
| Border (controls) | `--line` | #6e6e6e | changed (spec: 10% white) |
| Glass edge / divider | `--track` | #262626 | solid stand-in for 10% white |
| Text primary | `--text-1` | #ebebeb | same |
| Text secondary | `--text-2` | #999999 | 60% white as solid |
| Text muted (disabled only) | `--text-3` | #8c8c8c | changed (spec: 30% white = #4d4d4d) |
| Accent / focus | `--accent`, `--focus` | #ccff00 | same |
| On accent | `--on-accent` | #000000 | same |
| Success | `--success` | #10b981 | Emerald, same |
| Warning / Danger / Info | `--warning` `--danger` `--info` | #f5c04a / #ff7b7b / #7cc8f5 | not in spec, chosen |
| Radii | `--r-shell` / glass card | 2.5rem / 1.5rem | new; control and card radii stay |
| Fonts | headings / technical | Space Grotesk, -0.06em / JetBrains Mono, uppercase, 0.2em | stacks only |

Component notes
- Glass floating card: 3% white fill, `backdrop-filter: blur(16px)`, 10% white edge, `--r-glass`, float 6s ease-in-out (translateY 0 to -10px).
- Neon pulse button: `--accent` fill, `--on-accent` text, weight 700, pill, `0 0 30px` lime glow, hover scale 1.05, pulse 2s, easing `cubic-bezier(.4,0,.2,1)`.
- System status tag: mono, uppercase, 11px, 0.2em tracking, 6px pulsing lime dot; the text label carries the status (dot is not colour alone).
- Backdrop: 60px grid, noise SVG data URI at 15% opacity, glow sphere with 120px blur.

### Contrast (WCAG 2.x, computed with a python3 snippet)
Text needs 4.5:1, line and focus 3:1.

| Token | Value | on surface-0 | on surface-1 | on surface-2 |
|---|---|---|---|---|
| `--text-1` | #ebebeb | 17.62 | 16.41 | 14.60 |
| `--text-2` | #999999 | 7.37 | 6.87 | 6.11 |
| `--text-3` | #8c8c8c | 6.25 | 5.82 | 5.18 |
| `--accent` | #ccff00 | 17.87 | 16.65 | 14.81 |
| `--success` | #10b981 | 8.28 | 7.71 | 6.86 |
| `--warning` | #f5c04a | 12.52 | 11.66 | 10.38 |
| `--danger` | #ff7b7b | 8.37 | 7.80 | 6.94 |
| `--info` | #7cc8f5 | 11.44 | 10.65 | 9.48 |
| `--line` (3:1) | #6e6e6e | 4.12 | 3.84 | 3.41 |
| `--focus` (3:1) | #ccff00 | 17.87 | 16.65 | 14.81 |
| `--on-accent` on `--accent` | #000000 | 17.87 | | |

Changes from the spec: `--text-3` 30% white (#4d4d4d, 2.48:1 on #000) became #8c8c8c; `--line` 10% white (about 1.4:1) became #6e6e6e for controls (glass edge keeps 10% white as decoration only); warning, danger, info were unspecified and are picked to pass.

### Conflicts with the UI checklist and how the proposal resolves them
- (a) Muted text at 30% white fails 4.5:1: `--text-3` is the solid #8c8c8c and is used only for disabled.
- (b) 10px mono labels are below the 11px app minimum (`--fs-11`): use 11px, keep uppercase and 0.2em tracking.
- (c) 2.5rem shell and 1.5rem card radius vs `--r-control` 10px and `--r-card` 14px: add `--r-shell` (and glass card radius) for the shell and hero cards; controls keep `--r-control`.
- (d) Backdrop blur and noise count against the 72 KB CSS budget (`tests/web/test_shell.py` `CSS_TOTAL_MAX`); keep the noise data URI tiny, and add fallbacks: `prefers-reduced-transparency` (opaque `--surface-1`, no blur, no noise, no glow) and `prefers-reduced-motion` (no float, pulse or scale).
- (e) Glass border at 10% white is under 3:1 for control borders: inputs and buttons use the stronger `--line`; focus ring is lime `--focus`.
- (f) Hero 7.5rem type and the light "methodology" section are landing-page parts and do not apply to the dashboard.
- (g) Lime on light surfaces fails contrast: resolved by a separate light mode with olive `--accent` #4d6600 (4.5:1+ on the light surfaces), not by lime.
