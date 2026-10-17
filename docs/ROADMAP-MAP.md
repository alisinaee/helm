# Roadmap Map (R11.5)

The Roadmap section has three views: Lanes, Timeline and **Map** (`#/p/<id>/roadmap/map`, item: `/i/<task>`).

## What was compared

| Pattern | Good at | Weak for Helm |
|---|---|---|
| Now / Next / Later board | Undated priority, stakeholder view | Loses the phase plan order; Lanes already does columns |
| Swimlane roadmap | Parallel streams (teams, themes) | Our streams are phases, which are sequential |
| Gantt / timeline | Dated commitments | Helm has no dates (estimates in tokens only); Timeline view covers size |
| Tree / milestone map | Hierarchy | Plan is only two levels deep (phase, task) |
| Dependency graph | `after` links, critical path | Few links in practice; alone it hides progress per phase |
| Metro / subway line (roadmap.sh style) | Ordered stations, "you are here", progress | Needs a body for tasks |
| Story map | Backbone of steps with cards under each | Same columns as a lane board unless drawn on a canvas |

Sources: Roadmunk glossary (roadmap visualisation), Tempo Roadmaps docs (swimlane vs timeline), SlideUpLift roadmap
types, roadmap.sh about page (clickable nodes, progress tracking).

## Choice: metro line + story-map columns, with a dependency overlay

1. **Metro line of phases (backbone).** One station per phase in plan order, left to right, on one line. Each station
   shows id, name, `done/total · %`, a progress bar and `● n doing`. Done phases start folded (narrow column with a
   summary box); a tap, Enter or Space on the station opens or folds it in place.
2. **Story-map columns of task cards** under each open station, in plan order. A card has a coloured edge plus a glyph
   (✓ done, ● doing, ○ to do, ✕ blocked, ⏸ on hold, – deferred: status never by colour alone), id, model, size
   (`~tokens`) and the title. Done tasks of an open phase fold into one `✓ N done` stub that opens in place. A card
   with a running job shows ▶ and a pulsing outline (off under reduced motion); `·you` marks needs-you.
3. **Dependency overlay.** `after` pairs from the raw snapshot (`workflow.edges.after`) are drawn as arrows between
   shown cards (a loop on the right side within one column).
4. **Now marker.** A dashed vertical line and a ring on the station of the phase that owns a running job, else the
   first phase that is not done. The map opens 1:1 with that column a third in; `N` or the Now button centres on it.

Why: the plan is an ordered list of phases with many small tasks, no dates, and live agents. The metro line gives the
order, progress and "you are here" at a glance; the columns keep every task one click away; arrows add dependencies
without making a graph the whole picture. Lanes stays the editing view (reorder, approve); Map is for overview.

## Interaction

- Pan: drag, or plain wheel / trackpad scroll. Zoom: Cmd/Ctrl+wheel (pinch) around the cursor, `+` `-`, buttons.
  Fit: `0` or Fit. Full screen: the page is pinned over the window and the browser is asked for full screen; Escape or
  the button leaves. Pan and zoom are kept per project across refreshes; the SVG re-mounts only when the layout changes.
- Filters: status (All, Open, Doing, Blocked, On hold, Done) and model.
- Click or Enter on a card: Details in the right panel (route item; the panel has Copy ref). In full screen an aside on
  the map shows the same essentials with Copy ref and Open in Work.
- Right click, ContextMenu key or Shift+F10 on a card: Open details, Open in Work, Copy ref, Ask head (copies the ref
  with a "Head, about this task" line and opens Head filtered to the task; there is no web command to post to the head
  yet). The menu takes arrows, Home, End, Escape.
- Keyboard: the SVG is one tab stop; arrows move between items (graph/viewport.js), Shift+arrows pan.

## Files

- `web/js/graph/roadmap_layout.js` pure layout (node-tested). `web/js/views/roadmap_map.js` SVG, viewport, menu,
  full screen; reuses `graph/viewport.js` unchanged. `web/css/roadmap_map.css` loaded on demand by the view.
- Tests: `tests/web/test_roadmap_map.py`.
