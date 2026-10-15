Head list stops short of every item. I’ll read the lazy-load and trim paths in those four files and report the ranked causes in chat.

The Head screen never pages the ledger. It paints `snapshot.head.rows`, and that array is already a newest-only cut. There is no `24` cap in these files. A full unhandled count can still show about 24 rows because the byte trim drops the oldest rows until the head key fits in 8192 bytes, while the badge keeps the pre-trim count.

`docs/head.jsonl` has 60 entries. The screen can show only the newest open window that survives that cut.

## Findings

1. **`roadmap/core/snapshot.py:331-332`** — Open rows are `_newest(open_rows)[:HEAD_OPEN_MAX]` (`HEAD_OPEN_MAX` is 40 at line 30), then reversed. Done rows are the newest 5 (`HEAD_DONE_MAX`, line 31). Every older open entry, including old unhandled asks, is omitted. Line 30 says “oldest first”; the cut keeps the newest.

2. **`roadmap/core/snapshot.py:326-330`** — `counts.open`, `counts.unhandled`, and `counts.doneUnacc` are taken from the full fold before that cut. The badge can say 24 unhandled when the array holds fewer of them.

3. **`roadmap/core/snapshot.py:38` and `:336-345`** — After the 40-cap, the loop drops rows until compact JSON is at most `HEAD_BYTES_MAX` (8192). Titles go first, then the oldest done row, then the oldest open row (`done_at` falls back to index 0). Rows that carry `linked` are large, so the surviving list often lands in the low twenties. Newest rows stay. `tests/unit/test_head_snapshot.py:377-385` already expects `len(rows) < 40` under this cap.

4. **`roadmap/core/snapshot.py:301-302`** — `open_rows` drops `done`, `declined`, and `merged` (`CLOSED_STATUSES` in `roadmap/core/head.py:17`). `done_rows` keeps only `status == "done"`. Declined and merged never enter `head.rows`.

5. **`web/js/views/head.js:45-47`, `:519-525`, `:791`, `:821`** — `rowsOf` returns `vm.head.rows`. `sectionView` passes only `vm.project.snapshot.head`. `headHtml` filters and paints that array. No page size, no Show more, no list request.

6. **`web/js/views/head.js:50-54` and `:508-515`** — Unhandled keeps `new` and `understood` inside that same array. The empty-state “Show all” link only sets `f=all` on the same array. A trimmed id stays unreachable.

7. **`web/js/views/head.js:68-84` and `:104-108`** — Alerts prefer `head.counts` over the rows on screen. “N unhandled / Show” can open a shorter list, or “Nothing in this view.”

8. **`web/js/views/head.js:553-562`** — The only `GET /head` is the verbatim fetch: `?f=all&n=200&full=H…`. The handler stores `data.full` and discards `data.rows`. With 60 entries that response already holds the whole newest page. Lazy load here is text only (`FULL_CONCURRENCY` at line 31, `pump` at line 616).

9. **`web/js/views/head.js:802-806` and `:368`** — `#head?id=H12` adds the id to `openSet`. The row is rendered only when that id is already in the trimmed array, so a trimmed deep link opens nothing.

10. **`web/js/views/head.js:302-305` and `:815`** — Default sort is `new`, which reverses the window. The painted list is newest-first of a set that was already cut to the newest.

11. **`roadmap/http/routes.py:512-513` and `:518-531`** — The query allows `f` (`open|all`), `n` (1..200, default 100), and `full`. No `before` or offset.

12. **`roadmap/http/routes.py:563-574`** — `fold` returns file order, oldest first (`roadmap/core/head.py:177-222`). `shown[-n:]` keeps the newest `n`. `total` is the full filtered length. Nothing in the client reads `total`. Entry 201 and older cannot be named.

13. **`roadmap/http/routes.py:574`** — List rows are `head_row(e, moment)` with no accepted flag, suggest, linked, or prog. The snapshot row is richer (`snapshot.py:316-321`). Switching the screen onto this payload as it stands drops those fields.

14. **`web/js/state.js:312-313`** — `normalizeSnapshot` stores `raw.head` unchanged. That object is the trimmed preview. There is no second list.

15. **`web/js/state.js:501-507`** — `buildViewModel` exposes that snapshot and nothing else. `web/js/app.js:268` replaces `store.snapshots[id]` on every poll, so rows kept only inside the snapshot cannot grow across refreshes.

16. **`roadmap/core/snapshot.py:226-229`** — `head_row` copies `id`, `kind`, `sum`, `status`, `age`, and `ts`. It skips `sid` and `acct`, which `fold` does set (`roadmap/core/head.py:199-200`). `head.js:59` and `:154` compare `row.acct || row.sid`, so the session filter matches no row.

## Fix rule

The Head screen lists every folded entry. `snapshot.head` stays a small preview for the badge and the first paint. On open, the screen fetches `GET /head?f=all&n=200`. While `loaded < total`, a **Show older** button requests the next older page with `before=<oldest loaded id>`. Filters run on the merged list. A deep-linked id that is missing keeps paging until it is present or `more` is false. One page covers the current 60 entries. Past 200, the cursor is what makes the rest reachable.

Snapshot refresh must not delete that page cache. A head command drops the cache and fetches again so off-window status stays current.

### `roadmap/http/routes.py`

Add `before` to the query. Page toward older ids. `more` is true when the window does not start at the oldest shown entry.

```python
HEAD_QUERY_KEYS = ("f", "n", "full", "before")

def _head_window(shown, n, before):
    if before is None:
        window = shown[-n:]
    else:
        ids = [e["id"] for e in shown]
        if before not in ids:
            raise RoadmapError("invalid_input", "before must be an id in this list", EXIT_USAGE)
        window = shown[:ids.index(before)][-n:]
    more = bool(window) and window[0]["id"] != shown[0]["id"]
    return window, more
```

In `project_head`, replace `shown[-n:]` with that window. Build rows with the same fields as the snapshot (`accepted`, `suggest`, `linked`, `prog`), not a bare `head_row(e, moment)`.

```python
f, n, full, before = _head_query(req.query)
entries = head_service.rows(data_dir, link_state=head_link_state(snap["tasks"], snap["jobs"]), now=moment)
shown = [e for e in entries if f == "all" or e["status"] not in head_rules.CLOSED_STATUSES]
window, more = _head_window(shown, n, before)
body = {"f": f, "n": n, "total": len(shown), "more": more,
        "rows": [head_row_full(e) for e in window]}
```

`tests/api/test_head_api.py:58` still expects `n=1` with no `before` to return the newest id. Add a `before=<that id>` case that returns the older id and `more: false` when the oldest page is reached.

### `roadmap/core/snapshot.py`

Copy session fields onto every row (snapshot and the route share `head_row`):

```python
if entry.get("sid"):
    row["sid"] = entry["sid"]
if entry.get("acct"):
    row["acct"] = entry["acct"]
```

After the byte loop, mark the preview incomplete. Include declined and merged, which never enter `rows`:

```python
kept_open = sum(1 for r in rows if r["status"] != "done")
kept_done = sum(1 for r in rows if r["status"] == "done")
view["truncated"] = (kept_open < len(open_rows) or kept_done < len(done_rows)
                     or any(e["status"] in ("declined", "merged") for e in entries))
```

Add a public builder, `head_list(...)`, that returns every folded entry as a `head_row` in file order, with the same `row()` closure `_head_view` uses (lines 316-321). `_head_view` keeps the 40/5/8192 preview. `project_head` pages `head_list` and does not trim.

### `web/js/state.js`

Keep the trimmed snapshot at line 313. Store pages beside it so the poll cannot wipe them:

```javascript
const headPages = new Map();

export function noteHeadPage(pid, body) {
  const prev = headPages.get(pid) || { rows: [] };
  const byId = new Map(prev.rows.map(function (r) { return [r.id, r]; }));
  (body.rows || []).forEach(function (r) { if (r && r.id) byId.set(r.id, r); });
  headPages.set(pid, { rows: Array.from(byId.values()), total: body.total || 0, more: Boolean(body.more) });
}

export function headPageOf(pid) {
  return headPages.get(pid) || null;
}

export function dropHeadPage(pid) {
  headPages.delete(pid);
}
```

In `buildViewModel`, on the project object next to `snapshot` (line 502):

```javascript
headPage: headPageOf(route.id),
```

### `web/js/views/head.js`

Paint the union. Snapshot rows win on id so a poll refreshes status for rows still in the preview. Page rows supply everyone the preview dropped.

```javascript
function listRows(vm) {
  const byId = new Map();
  const page = vm && vm.headPage;
  (page && page.rows || []).forEach(function (r) { byId.set(String(r.id), r); });
  rowsOf(vm).forEach(function (r) { byId.set(String(r.id), r); });
  return Array.from(byId.values());
}
```

Use `listRows(vm)` in `headHtml` instead of `rowsOf` (line 522). Counts for the badge stay on `head.counts`. Under the list, when `headPage` is missing or `headPage.rows.length < headPage.total`:

```javascript
'<p class="hd-more"><button type="button" class="btn" data-action="head-more">Show older (' +
  (page.total - page.rows.length) + ")</button></p>"
```

Fetch like Research (`rb:render` at `web/js/app.js:498`):

```javascript
const PAGE = 200;

function headUrl(pid, before) {
  return "/api/v1/projects/" + encodeURIComponent(pid) + "/head?f=all&n=" + PAGE +
    (before ? "&before=" + encodeURIComponent(before) : "");
}

function loadHead(pid, before) {
  getJson(headUrl(pid, before)).then(function (res) {
    noteHeadPage(pid, res.data || {});
    document.dispatchEvent(new Event("rb:render"));
  });
}
```

Call `loadHead(pid)` from `sectionView` when `vm.project.headPage` is null. `data-action="head-more"` calls `loadHead(pid, oldestId)` where `oldestId` is the smallest `ts` in `headPage.rows`. After each `run("head.…")`, `dropHeadPage(project)` and `loadHead(project)` so a status change off the preview is not stuck. Change `fetchFull` (line 558) to `?f=all&n=1&full=` so opening a row no longer downloads a list and throws it away.

If `params.get("id")` is absent from `listRows` and `headPage.more` is true, call `loadHead` with the current oldest id until that id appears.

