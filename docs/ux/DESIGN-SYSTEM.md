# Helm design system (R12.1 proposal)

Status key: **[exists]** already in `web/css/tokens.css`, `components.css` or `web/icons.svg`; **[proposed]** new, not wired into the app. Preview: `docs/ux/design-preview.html` (open from file://).

## Palette
Dark is the default; light applies via `prefers-color-scheme: light` or `data-theme="light"`. All **[exists]**; no new hues.

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
