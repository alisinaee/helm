# Limits v2 and top bar usage (R11.126, R11.129; asks H254, H257)

The person's words (2026-10-17): "I need to set a token limit for 5h. The user can set a limit in two ways: how much to
consume (e.g. 20% of the 5h, or 5% of weekly) OR a cap (stop at 35% weekly or 5h). More interactive UI, e.g. set it on
the chart bar. Top bar: show the current account's usage in a small, visual way plus the limit if set; remove unused
things like Mark or the shortcut button."

## 1. Two windows, two modes each

For each window (5 hours, Week) one limit row:

| Field | Values |
|---|---|
| on | on / off |
| mode | `budget` = "use at most N% more from now" (stored as start reading + N, so cap = start + N, clamped 100) or `cap` = "stop at N%" |
| value | 1..100 |
| scope | account (default) or per project (existing share-per-project stays, folded under "Per project") |

Both modes resolve to one absolute stop % per window (`effectiveStop`). A budget is re-based when the window resets
(5h budget repeats each 5h window unless "once" is ticked). The head and agents stop launching at the lowest active stop.

## 2. Interactive control (Tokens > Limits)

One card per window, side by side (stacked < 900px):
- A horizontal usage bar 0-100% (current usage filled, tick at now). The stop is a draggable handle on the bar (pointer
  drag + arrow keys 1%, Shift+arrow 5%, role="slider" aria-valuenow/min/max, aria-valuetext "stop at 35%").
- In budget mode the handle is placed at now+N and a shaded segment shows the allowed range (from now to stop),
  labelled "+20% of 5h"; dragging updates N. In cap mode the label reads "stop at 35%".
- Mode segmented control: "Budget from now" | "Cap at". On/off switch. Numeric input mirrors the handle.
- Status line: "Stops new jobs in ~1h 10m at current pace" when a pace estimate exists; "Reached: agents paused" with
  "Override 1h" when hit.
- Save is live (debounced 400 ms); every change is a board op so it reaches the head (panel line).

## 3. Head and agents obey the board

- `roadmap usage stops` prints effective stops; the hook/head brief shows "5h 49% / stop 50%".
- The head runbook caps (H232 weekly 40%, H235 5h 50%) are seeded into the board once, then the board is the source of
  truth (runbook says "read the board").

## 4. Top bar

Replace the text "Week 20% · stop off · 1m ago" with a compact usage widget:
- Two mini bars (5h, W), 56px wide each, current fill + stop tick; tone warn >= stop-10, danger >= stop. Text "49%" next
  to each. Tooltip/aria: "5 hours 49%, stop at 50%, resets 13:50; updated 1m ago". Stale reading (> 15 min) dims and
  shows a dot. Click opens Tokens > Limits.
- Account chip (masked name) before the bars when more than one account is configured.
- Remove from the top bar: Mark (keep the Mark key/command in the palette), the ⌘K button (palette stays on the key;
  add it to the help "?" list), Auto if it is unused (check usage first; if used, move into the More menu). Keep
  Running/Stop, Live, ?, panel toggle.

## 5. Tests

Unit: effectiveStop for both modes, budget re-base on reset, lowest-stop wins. API: set/get limits, panel record.
Web: slider keyboard and aria, top bar widget markup, removed buttons absent, a11y static, r765 labels.
