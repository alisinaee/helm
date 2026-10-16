// System views side panel (R10.33): the facts of the selected node, as a string. system.js docks it at the right
// edge. `d` is arch.details[id] from GET /api/v1/projects/<id>/system: kind (system, person, external, container,
// component, module, store) and the lists for that kind. Rows use the shared .row-grid columns (name | number |
// number), so counts line up; a related node is a link (data-sys-go) that system.js turns into a selection.

import { chipHtml, esc } from "../dom.js";

const KIND = { system: "System", person: "Person", external: "External system", container: "Container",
  component: "Component", module: "Module (folder)", store: "Data store" };

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function human(n) {
  const v = num(n);
  return v >= 1000 ? (v / 1000).toFixed(1) + "k" : String(v);
}

function day(at) {
  if (typeof at === "number") return new Date(at * 1000).toISOString().slice(5, 10);
  return typeof at === "string" ? at.slice(5, 10) : "";
}

function cell(text, cls, title) {
  return '<span class="' + cls + '" title="' + esc(title || text) + '">' + esc(text) + "</span>";
}

function row(a, b, c) {
  return '<div class="row-grid fin-row">' + a + cell(b, "rg-num") + cell(c, "rg-num") + "</div>";
}

function head(a, b, c) {
  return '<div class="row-grid fin-row wfg-note">' + cell(a, "rg-t") + cell(b, "rg-num") + cell(c, "rg-num") +
    "</div>";
}

// A related node: a link to this section that system.js turns into a selection (it keeps the URL).
function go(id, label) {
  return '<a class="rg-t" href="#" data-sys-go="' + esc(id) + '" title="' + esc(label) + '">' + esc(label) + "</a>";
}

function section(title, rows, more) {
  if (!rows.length) return "";
  return "<section><h3>" + esc(title) + (more ? ' <span class="wfg-note">' + esc(more) + "</span>" : "") +
    "</h3>" + rows.join("") + "</section>";
}

function links(list, title) {
  const rows = (Array.isArray(list) ? list : []).slice(0, 12).map((x) => row(go(x.id, x.label),
    x.count ? String(x.count) : "", "", x.note));
  return rows.length ? section(title, [head("Name", "Imports", "")].concat(rows)) : "";
}

function files(list, total) {
  const rows = (Array.isArray(list) ? list : []).map((f) => row(cell(f.path, "rg-t"), f.lines ? human(f.lines) : "",
    f.commits !== undefined ? String(num(f.commits)) : ""));
  return rows.length ? section("Files", [head("Path", "Lines", "Commits")].concat(rows),
    total > rows.length ? "top " + rows.length + " of " + total : "") : "";
}

function facts(pairs) {
  const rows = pairs.filter((p) => p[1] !== "" && p[1] !== null && p[1] !== undefined)
    .map((p) => row(cell(p[0], "rg-t"), String(p[1]), ""));
  return rows.join("");
}

export function panelHtml(pid, id, d) {
  if (!id || !d) return "";
  const title = d.title || id;
  const base = "#/p/" + encodeURIComponent(pid);
  let body = "";
  if (d.notes) body += "<p>" + esc(d.notes) + "</p>";
  if (d.kind === "system" && d.stats) {
    const s = d.stats;
    body += facts([["Files", s.files], ["Source files", s.sourceFiles], ["Lines of code", human(s.lines)],
      ["Imports", s.imports], ["Modules", s.modules]]);
    body += section("Languages", Object.entries(s.languages || {}).map((kv) => row(cell(kv[0], "rg-t"),
      String(kv[1]), "files")));
  }
  if (d.kind === "container") {
    body += facts([["Technology", d.tech || ""], ["Entry", (d.entries || [])[0] || ""]]);
    body += links(d.components, "Components");
  }
  if (d.kind === "component") {
    const h = d.heat || {};
    body += facts([["Layer", d.layer || ""], ["Language", d.language || ""], ["Files", num(d.fileCount)],
      ["Lines", human(d.lines)], ["Commits (30 days)", num(d.commits30)], ["Running jobs", num(h.runningJobs)],
      ["Open Work", num(h.openWork)], ["Entry", (d.entries || [])[0] || ""]]);
    body += links(d.dependsOn, "Depends on") + links(d.usedBy, "Used by");
    if (Array.isArray(d.stores) && d.stores.length) {
      body += section("Data", [row(cell(d.stores.join(", "), "rg-t"), "", "")]);
    }
    body += files(d.files, d.fileCount);
    body += section("Recent commits", (d.commits || []).map((c) => row(cell(c.subject, "rg-t"), c.sha, day(c.at))));
    body += section("Agent jobs", (d.jobs || []).map((j) => row(cell((j.task || "") + " " + (j.title || ""), "rg-t"),
      j.model || "", j.status || "")));
    if (Array.isArray(d.globs) && d.globs.length) {
      body += section("Paths", [row(cell(d.globs.join("  "), "rg-t code"), "", "")]);
    }
  }
  if (d.kind === "module") {
    body += facts([["Files", num(d.fileCount)], ["Lines", human(d.lines)]]);
    if (d.component) body += section("Component", [row(go(d.component.id, d.component.label), "", "")]);
    body += links(d.dependsOn, "Imports from") + links(d.usedBy, "Imported by");
    if (Array.isArray(d.packages) && d.packages.length) {
      body += section("Packages", [row(cell(d.packages.join(", "), "rg-t"), "", "")]);
    }
    body += files(d.files, d.fileCount);
  }
  if (d.kind === "store") {
    if (Array.isArray(d.tables) && d.tables.length) body += section("Tables", [row(cell(d.tables.join(", "), "rg-t"),
      String(d.tables.length), "")]);
    body += section("Read and written by", (d.readers || []).map((r) => row(cell(r.path, "rg-t"), "", r.mode)));
    body += section("Tracked files", (d.tracked || []).map((p) => row(cell(p, "rg-t"), "", "")));
  }
  if (d.kind === "external") body += section("Used by", (d.files || []).map((f) => row(cell(f.path, "rg-t"), "", "")));
  return '<aside class="side-body sys-panel" aria-label="' + esc(KIND[d.kind] || "Node") + " " + esc(title) + '">' +
    '<div class="p-head"><h2 class="p-name" title="' + esc(title) + '">' + esc(title) + "</h2>" +
    chipHtml(KIND[d.kind] || d.kind || "node") + '<button type="button" class="btn btn-small" data-sys-op="close" ' +
    'aria-label="Close panel (Esc)">Close</button></div>' + body +
    (d.kind === "component" ? '<p class="wfg-note"><a href="' + base + '/git">Commits in Git</a> · <a href="' + base +
      '/agents">Agents</a></p>' : "") + "</aside>";
}
