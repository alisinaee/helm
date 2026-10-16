# Web Git Section JS Library Review

## 1. Candidate Comparison Table

| Lib | License | Repo URL | Last Release | Size | No-build Usable? | What It Covers | Risk |
|---|---|---|---|---|---|---|---|
| `diff2html` | MIT | https://github.com/rtfpessoa/diff2html | 2026 | ~35 KB JS + ~30 KB CSS | Yes (`bundles/js/diff2html.min.js`) | Side-by-side & inline file diff viewer, file summary | Companion CSS required; UI bundle large if bundled with full highlight.js |
| `@gitgraph/js` | MIT | https://github.com/nicoespeon/gitgraph.js | 2020 (archived 2024) | ~30 KB | Yes (`gitgraph.umd.min.js`) | Visual commit graph, branch lanes, merge curves | Upstream archived July 2024; imperative simulation API requires DAG replay adapter |
| `gitgraph.js` (legacy v1) | MIT | https://github.com/nicoespeon/gitgraph.js | 2018 | ~55 KB | Yes (plain `<script>`) | Canvas/SVG commit graph with branch lanes | Abandoned/unmaintained; superseded by `@gitgraph/js`; lacks modern DOM support |
| `d3-dag` | MIT | https://github.com/erikbrinkman/d3-dag | 2026 | ~25 KB | Yes (`d3-dag.iife.min.js`) | DAG layout algorithms (topological sort, decrossing, coord mapping) | Layout engine only; requires writing custom SVG rendering for lanes and commit dots |
| `vis-network` | MIT / Apache-2.0 | https://github.com/visjs/vis-network | 2026 | ~170 KB | Yes (`vis-network.min.js`) | General network graphs, physics simulation, DAG layout | Heavy bundle (~170 KB); general-purpose layout requires tuning for Git lane topology |
| `monaco diff` | MIT | https://github.com/microsoft/monaco-editor | 2026 | >2 MB | No (requires AMD loader & workers) | Side-by-side & inline rich diff editor | Exceeds web asset budget (>2 MB); complex worker setup; overkill for read-only diffs |
| `jsdiff` | BSD-3-Clause | https://github.com/kpdecker/jsdiff | 2024 | ~15 KB | Yes (`diff.min.js`) | Text diff computation (Myers/LCS algorithm, patches) | Algorithm only; provides zero UI/DOM/HTML rendering for side-by-side diffs or trees |

## 2. Recommendation (2 Libraries)

1. **`diff2html` (v3.4.56, MIT)**: Best-in-class for side-by-side and inline diff viewing and file change listings. The core UMD bundle (`diff2html.min.js`, ~35 KB) directly parses unified diff text from `git diff` into GitHub-like HTML tables without build steps, fulfilling the read-only viewer spec in `docs/GIT-SPEC.md#L9`.
2. **`@gitgraph/js` (v1.4.0, MIT)**: Turnkey choice for visual commit graph and branch lanes. Its standalone UMD bundle (`gitgraph.umd.min.js`, ~30 KB) renders SVG commit nodes and branch curves with zero external dependencies. (*Fallback*: `d3-dag` if direct parent-pointer coordinate mapping is preferred over history replay).

## 3. Integration Plan (14 Steps)

### Existing Files Changing
- `roadmap/services/git.py`: Git service runner and parsers (`roadmap/services/git.py#L1-L405`).
- `roadmap/services/gitops.py`: Git operations service (`roadmap/services/gitops.py#L1-L432`).
- `roadmap/http/routes.py`: Read route handlers for git endpoints (`roadmap/http/routes.py#L750-L839`).
- `web/index.html`: Web asset inclusions (`web/index.html#L24-L54`).
- `web/css/git.css`: Git section layout and diff styling within size budget (`docs/GIT-SPEC.md#L51`).
- `web/js/views/git.js`: Git section view and DOM rendering (`web/js/views/git.js#L1-L224`).

### Steps
1. **Vendor Libraries**: Download and vendor `diff2html.min.js` (~35 KB), `diff2html.min.css` (~30 KB), and `gitgraph.umd.min.js` (~30 KB) into `web/vendor/`.
2. **Include Web Assets**: Reference `diff2html.min.css` in `web/index.html#L24-L25` and vendor scripts before `app.js` in `web/index.html#L54`.
3. **Extend Log Format for Graph Data**: In `roadmap/services/git.py#L36`, update `LOG_FORMAT` from `%H%x00%an%x00%at%x00%s%x00%B%x00` to include parent hashes (`%P`) as a 6th NUL-delimited field.
4. **Parse Commit Parents**: Update `parse_log()` in `roadmap/services/git.py#L336-L351` to parse `parents: tokens[start+5].split()` into each commit dict.
5. **Serve Graph Log Data**: In `roadmap/http/routes.py#L756-L763`, ensure `GET /api/v1/projects/{pid}/git/log?n=` includes parent hashes for graph rendering.
6. **Add Uncommitted Diff Service**: In `roadmap/services/git.py`, add `read_worktree_diff(project, rel_path, staged=False)` using `cap_text` (`roadmap/services/git.py#L392-L404`) and `diff_skip_reason` (`roadmap/services/git.py#L382-L390`).
7. **Add Worktree Diff Endpoint**: In `roadmap/http/routes.py#L800-L822`, add `GET /api/v1/projects/{pid}/git/diff?path=&staged=` to fetch patches for uncommitted files in `status` (`web/js/views/git.js#L103-L135`).
8. **Verify Commit Show & Diff Endpoints**: Confirm `GET .../git/show/{sha}` (`roadmap/http/routes.py#L773-L796`) and `GET .../git/diff/{sha}?path=` (`roadmap/http/routes.py#L799-L822`) return commit file lists and capped patches.
9. **Build Replay Adapter for Gitgraph**: In `web/js/views/git.js`, create a helper `renderCommitGraph(container, rows)` that maps topological commits and branch lanes into `GitgraphJS.createGitgraph(container)`.
10. **Render Graph in History Tab**: In `web/js/views/git.js#L149-L164` (`historyHtml`), split the view into an SVG lane graph container alongside the commit metadata table.
11. **Add Commit Detail & File Tree Drawer**: In `web/js/views/git.js`, handle commit row clicks by calling `gitBase(pid) + "show/" + sha` (`web/js/views/git.js#L23-L25`) and rendering a file tree with `added`/`deleted` badges.
12. **Integrate Diff Viewer Component**: In `web/js/views/git.js`, render diffs via `Diff2Html.html(diffText, { drawFileList: false, outputFormat: mode })` when a file is selected in Changes or Commit Detail.
13. **Add Diff View Mode Toggle**: Add inline vs side-by-side mode toggle controls and raw patch copy buttons in `web/js/views/git.js`.
14. **CSS Styling & Verification**: Add container classes in `web/css/git.css` adhering to token colors and CSS budget (`docs/GIT-SPEC.md#L51`), then verify with tests in `tests/unit/test_git_service.py` and `tests/web/test_git_view.py` (`docs/GIT-SPEC.md#L59`).
