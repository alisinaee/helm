# System section: engineering views (R10.33, H217)

Goal: for the selected project, show its structure the way engineers draw it, so a reader understands what runs,
what depends on what, where data lives and how a request flows. Replaces the single flat card map (R10.23).

## Why the old map failed
One hand-written list (roadmap-board only); other projects got folder cards with no edges. Edges came only from
docs/system.json, had no labels, crossed through cards, and the cards said nothing about what a part does.

## Views (one segmented switcher; C4 levels first)
| View | Shows | Source |
|---|---|---|
| Context (C4 L1) | Person, the system, external systems (Git, DBs, HTTP APIs, AI APIs, agents) with labelled arrows | imports matched to a catalogue + system.json `external` layer |
| Containers (C4 L2) | Runnable units: web app, Python/Node apps, scripts, file/DB stores; HTTP and data arrows | entry points, package dirs, `fetch("/api")`, data literals; system.json `containers` |
| Components (C4 L3) | Components grouped in their container boxes; import arrows labelled with the imported modules | system.json components or folder baseline; import scan |
| Modules (code) | Every source folder, ranked by dependency tier (entry on top, foundations at the bottom) | import scan (py, js, mjs, cjs, ts, tsx, jsx); tests excluded |
| Layers | Components in layer bands; arrows that point up a layer are red (layer violations / cycles) | system.json `layers`, else tiers from the dependency graph |
| Flows | Sequence diagrams: numbered messages between participants, replies dashed | system.json `flows`, else derived from each entry point |
| Data | Stores (data files, DBs) and the components that read / write them | string literals of data files + DB client imports |

Every node opens the side panel: what it is, files (lines, commits 30 d), depends on / used by with counts, recent
commits, jobs on its tasks, readers / writers for stores.

## Derivation (server, `roadmap/services/system_arch.py`)
- Reads only tracked source files (cap 4000 files, 256 KB each), confined to the project root; cached by HEAD sha
  and system.json mtime. Python `import` / `from` (relative too) and JS/TS `import` / `export from` / `require` /
  `import()` with relative paths are resolved to files; bare names become external packages.
- Module = source folder. Component edges = file imports aggregated by component globs. Declared edges keep their
  labels; derived ones are marked `derived`.
- system.json (all optional): `containers: [{id, name, tech, components: [ids], notes}]`,
  `flows: [{id, name, notes, steps: [{from, to, label, reply}]}]` (ids of components, containers or `user`).

## API
`GET /api/v1/projects/{id}/system` keeps its fields and adds `arch: {views: {context, containers, components,
modules, layers, data}, flows, details, stats}`. A view is `{groups: [{id, label}], nodes: [{id, label, sub, kind,
group, tone}], edges: [{from, to, label, kind, count, derived}]}`; node ids are prefixed (`c:`, `m:`, `k:`, `s:`,
`x:`, `p:`) and key into `details`.

## Drawing (`web/js/graph/syslayout.js`, `web/js/views/system.js`, `system-panel.js`)
- Rows = groups (boxes with a label), wrapped at 6 nodes; barycentre ordering to cut crossings; curved edges from
  bottom ports to top ports, arrowheads, labels placed where they hit no node or other label (else tooltip only).
- Shapes: person, system (accent), external (dashed), container / component / module (tone strip), store
  (cylinder). Colours are token vars in SVG attributes (light / dark follow the theme, no new CSS).
- Pan / zoom from graph/viewport.js (Cmd/Ctrl+wheel zooms at the cursor); opens fitted, never below 60 %.
- Legend line and a one-line "what this view answers" under the switcher. Esc closes the panel.

## Left
Container and context detection is heuristic; projects can pin them in system.json. Runtime flows are derived
from import chains, so they show "who calls whom", not timing.
