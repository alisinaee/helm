// System v2 diagram renderers (R11.107). Pure functions: data in, SVG markup out, no DOM.
// Each renderer takes (data, opts) with opts.selected (id drawn with the --focus stroke) and opts.near (Set of ids;
// every other node gets class "wfg-dim"). It returns {inner, w, h, boxes, bands}: inner is SVG markup without the
// outer <svg> (the caller wraps it and adds a viewport <g>); it carries its own <defs> with ids prefixed "sysd-".
// boxes are the node rectangles in the returned coordinate space, bands the container frames (for tests and fit).
import { esc } from "../dom.js";

const PAD = 12;
const CH = 7;
const ROW = 20;
const HEAD = 26;
const CAP = 8;

function v(name) {
  return "var(" + name + ")";
}

function tw(s) {
  return String(s == null ? "" : s).length * CH;
}

function clip(s, n) {
  const t = String(s == null ? "" : s);
  return t.length > n ? t.slice(0, Math.max(1, n - 1)) + "…" : t;
}

function f(n) {
  return Math.round(n * 10) / 10;
}

function arr(x) {
  return Array.isArray(x) ? x : [];
}

function ctx(opts) {
  const o = opts || {};
  return { sel: o.selected == null ? null : String(o.selected), near: o.near instanceof Set ? o.near : null };
}

const DEFS = "<defs>" +
  '<marker id="sysd-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 1L9 5L0 9z"' +
      ' fill="' + v("--text-2") + '"/></marker>' +
  '<marker id="sysd-arrow-err" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 1L9 5L0 9z"' +
      ' fill="' + v("--danger") + '"/></marker>' +
  '<marker id="sysd-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M1 1L9 5L1 9" fill="none"' +
      ' stroke="' + v("--text-2") + '" stroke-width="1.3"/></marker>' +
  '<marker id="sysd-tri" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M1 1L11 6L1 11z"' +
      ' fill="' + v("--surface-1") + '" stroke="' + v("--text-2") + '" stroke-width="1.2"/></marker>' +
  '<marker id="sysd-many" viewBox="0 0 12 12" refX="12" refY="6" markerWidth="12" markerHeight="12"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 6L12 0M0 6L12 6M0 6L12 12" fill="none"' +
      ' stroke="' + v("--text-2") + '" stroke-width="1.2"/></marker>' +
  '<marker id="sysd-one" viewBox="0 0 12 12" refX="8" refY="6" markerWidth="12" markerHeight="12"' +
      ' markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M8 1V11" fill="none"' +
      ' stroke="' + v("--text-2") + '" stroke-width="1.4"/></marker>' +
  "</defs>";

function empty() {
  return {
    inner: DEFS + '<text x="' + PAD + '" y="28" font-size="13" fill="' + v("--text-2") + '">Nothing to draw</text>',
    w: 160, h: 44, boxes: [], bands: []
  };
}

function finish(parts, w, h, boxes, bands) {
  const shift = (b) => ({ id: b.id, x: b.x + PAD, y: b.y + PAD, w: b.w, h: b.h });
  return {
    inner: DEFS + '<g transform="translate(' + PAD + " " + PAD + ')">' + parts + "</g>",
    w: Math.ceil(w + 2 * PAD), h: Math.ceil(h + 2 * PAD),
    boxes: boxes.map(shift), bands: arr(bands).map(shift)
  };
}

function strokeOf(c, id) {
  return c.sel === id ? v("--focus") : v("--line");
}

function swOf(c, id) {
  return c.sel === id ? 2 : 1;
}

function nodeG(c, id, label, tip, x, y, body) {
  const dim = c.near && !c.near.has(id);
  return '<g class="wfg-n' + (dim ? " wfg-dim" : "") + '" data-sys="' + esc(id) + '" data-wf-item="' + esc(id) +
    '" tabindex="-1" role="button" aria-pressed="' + (c.sel === id) + '" aria-label="' + esc(label) +
    '" transform="translate(' + f(x) + " " + f(y) + ')"><title>' + esc(tip) + "</title>" + body + "</g>";
}

function edgeDim(c, a, b) {
  return c.near && !(c.near.has(a) && c.near.has(b)) ? " wfg-dim" : "";
}

function pathG(c, a, b, d, attrs, title) {
  return '<path class="sys-e' + edgeDim(c, a, b) + '" d="' + d + '" fill="none" ' + attrs + ' data-from="' + esc(a) +
    '" data-to="' + esc(b) + '"><title>' + esc(title || "") + "</title></path>";
}

function text(x, y, s, size, fill, extra) {
  return '<text x="' + f(x) + '" y="' + f(y) + '" font-size="' + size + '" fill="' + fill + '"' + (extra || "") + ">" +
    esc(s) + "</text>";
}

function halo(x, y, s) {
  return '<text x="' + f(x) + '" y="' + f(y) + '" font-size="11" text-anchor="middle" fill="' + v("--text-2") +
    '" stroke="' + v("--surface-1") + '" stroke-width="3" paint-order="stroke">' + esc(s) + "</text>";
}

// Point on the border of rect b, from its centre toward (px, py).
function clipRect(b, px, py) {
  const cx = b.x + b.w / 2;
  const cy = b.y + b.h / 2;
  const dx = px - cx;
  const dy = py - cy;
  if (!dx && !dy) return [cx, cy];
  const s = Math.min(dx ? b.w / 2 / Math.abs(dx) : Infinity, dy ? b.h / 2 / Math.abs(dy) : Infinity);
  return [cx + dx * s, cy + dy * s];
}

function link(a, b) {
  const p = clipRect(a, b.x + b.w / 2, b.y + b.h / 2);
  const q = clipRect(b, a.x + a.w / 2, a.y + a.h / 2);
  return { p, q, len: Math.hypot(q[0] - p[0], q[1] - p[1]) };
}

function line(p, q) {
  return "M" + f(p[0]) + " " + f(p[1]) + "L" + f(q[0]) + " " + f(q[1]);
}

function uniq(list, key) {
  const seen = new Set();
  const out = [];
  list.forEach((x) => {
    if (!x || x[key] == null) return;
    const k = String(x[key]);
    if (seen.has(k)) return;
    seen.add(k);
    out.push(x);
  });
  return out;
}

function wrap2(s, n) {
  const words = String(s == null ? "" : s).split(/\s+/).filter(Boolean);
  const lines = [""];
  words.forEach((w) => {
    const cur = lines[lines.length - 1];
    if (!cur) lines[lines.length - 1] = w;
    else if ((cur + " " + w).length <= n || lines.length >= 2) lines[lines.length - 1] = cur + " " + w;
    else lines.push(w);
  });
  return lines.slice(0, 2).map((l) => clip(l, n));
}

// ---------------------------------------------------------------- ER / EER

export function erSvg(er, opts) {
  const c = ctx(opts);
  const ents = uniq(arr(er && er.entities), "id");
  if (!ents.length) return empty();
  const byId = new Map();
  const items = ents.map((e) => {
    const id = String(e.id);
    const label = String(e.label == null ? id : e.label);
    const attrs = arr(e.attrs).filter((a) => a && a.name != null);
    const shown = attrs.length > 30 ? attrs.slice(0, 29) : attrs;
    const more = attrs.length - shown.length;
    let wmax = tw(clip(label, 36)) + 20;
    shown.forEach((a) => {
      wmax = Math.max(wmax, 34 + tw(a.name) + 14 + tw(clip(a.type, 12)) + 10);
    });
    const rows = shown.length + (more > 0 ? 1 : 0);
    const it = {
      id, label, e, shown, more, rows, deg: 0, x: 0, y: 0,
      w: Math.max(120, Math.min(260, wmax)), h: HEAD + (rows ? rows * ROW + 4 : 8)
    };
    byId.set(id, it);
    return it;
  });
  const rels = uniq(arr(er.relations).map((r) => (r ? { ...r, key: r.from + ">" + r.to + ":" + r.label } : r)), "key")
    .filter((r) => byId.has(String(r.from)) && byId.has(String(r.to)));
  rels.forEach((r) => {
    if (String(r.from) === String(r.to)) return;
    byId.get(String(r.from)).deg++;
    byId.get(String(r.to)).deg++;
  });
  items.forEach((it) => {
    const p = it.e.parent == null ? "" : String(it.e.parent);
    if (p && byId.has(p) && p !== it.id) {
      it.deg++;
      byId.get(p).deg++;
    }
  });
  const n = items.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.3)));
  const nrows = Math.ceil(n / cols);
  const slots = [];
  for (let r = 0; r < nrows; r++) {
    for (let k = 0; k < cols; k++) {
      slots.push({ r, k, d: Math.hypot((k - (cols - 1) / 2) * 1.4, r - (nrows - 1) / 2) });
    }
  }
  slots.sort((a, b) => a.d - b.d || a.r - b.r || a.k - b.k);
  const order = items.slice().sort((a, b) => b.deg - a.deg || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
  const colW = new Array(cols).fill(0);
  const rowH = new Array(nrows).fill(0);
  order.forEach((it, i) => {
    it.r = slots[i].r;
    it.k = slots[i].k;
    colW[it.k] = Math.max(colW[it.k], it.w);
    rowH[it.r] = Math.max(rowH[it.r], it.h);
  });
  const GX = 64;
  const GY = 46;
  const colX = [];
  let x = 0;
  colW.forEach((w) => {
    colX.push(x);
    x += w + GX;
  });
  const rowY = [];
  let y = 0;
  rowH.forEach((h) => {
    rowY.push(y);
    y += h + GY;
  });
  items.forEach((it) => {
    it.x = colX[it.k] + (colW[it.k] - it.w) / 2;
    it.y = rowY[it.r] + (rowH[it.r] - it.h) / 2;
  });
  const out = [];
  const endMark = (one) => (one ? "sysd-one" : "sysd-many");
  rels.forEach((r) => {
    const a = byId.get(String(r.from));
    const b = byId.get(String(r.to));
    const card = String(r.card || "1-n").split("-");
    const aOne = card[0] !== "n";
    const bOne = card[1] !== "n";
    const attrs = 'stroke="' + v("--text-2") + '" stroke-width="1.2"' +
        (r.implied ? ' stroke-dasharray="5 3" stroke-opacity=".6"' : "") +
      ' marker-start="url(#sysd-' + endMark(aOne).slice(5) + ')" marker-end="url(#sysd-' + endMark(bOne).slice(5) +
          ')"';
    const title = a.label + " → " + b.label + (r.label ? " (" + r.label + ")" : "") + (r.implied ? " implied" : "");
    if (a === b) {
      const rx = a.x + a.w;
      const d = "M" + f(rx) + " " + f(a.y + 12) + "C" + f(rx + 40) + " " + f(a.y - 4) + " " + f(rx + 40) + " " + f(a.y +
          34) + " " +
        f(rx) + " " + f(a.y + 28);
      out.push(pathG(c, a.id, b.id, d, attrs, title));
      return;
    }
    const L = link(a, b);
    out.push(pathG(c, a.id, b.id, line(L.p, L.q), attrs, title));
    if (r.label && L.len > tw(clip(r.label, 16)) + 40) {
      out.push(halo((L.p[0] + L.q[0]) / 2, (L.p[1] + L.q[1]) / 2 - 4, clip(r.label, 16)));
    }
  });
  items.forEach((it) => {
    const p = it.e.parent == null ? "" : String(it.e.parent);
    if (!p || !byId.has(p) || p === it.id) return;
    const pa = byId.get(p);
    const L = link(it, pa);
    out.push(pathG(c, it.id, pa.id, line(L.p, L.q),
      'stroke="' + v("--text-2") + '" stroke-width="1.3" marker-end="url(#sysd-tri)"', it.label + " is a " + pa.label));
  });
  items.forEach((it) => {
    const sel = c.sel === it.id;
    const sk = strokeOf(c, it.id);
    let body = '<rect width="' + f(it.w) + '" height="' + f(it.h) + '" rx="6" fill="' + v("--surface-2") +
        '" stroke="' + sk +
      '" stroke-width="' + swOf(c, it.id) + '" stroke-opacity="' + (sel ? 1 : 0.7) + '"/>' +
      '<path d="M0 ' + HEAD + "V6a6 6 0 0 1 6-6h" + f(it.w - 12) + "a6 6 0 0 1 6 6V" + HEAD + 'z" fill="' +
          v("--track") + '"/>' +
      text(10, 17, clip(it.label, Math.floor((it.w - 20) / CH)), 13, v("--text-1"), ' font-weight="600"') +
      '<path d="M0 ' + HEAD + "H" + f(it.w) + '" stroke="' + v("--line") + '" stroke-opacity=".5"/>';
    it.shown.forEach((a, i) => {
      const yy = HEAD + i * ROW + 15;
      const type = clip(a.type, 12);
      const tag = a.pk ? "PK" : a.fk ? "FK" : "";
      if (tag) body += text(8, yy, tag, 10, a.pk ? v("--accent") : v("--text-2"), ' font-weight="700"');
      body += text(34, yy, clip(a.name, Math.floor((it.w - 34 - 14 - tw(type)) / CH)), 11, v("--text-1"));
      if (type) body += text(it.w - 8, yy, type, 11, v("--text-3"), ' text-anchor="end"');
    });
    if (it.more > 0) body += text(34, HEAD + it.shown.length * ROW + 15, "+" + it.more + " more", 11, v("--text-3"));
    const tip = it.label + (it.e.source ? "\n" + it.e.source : "") + (it.e.file ? "\n" + it.e.file : "") + "\n" +
      (it.shown.length + it.more) + " attributes";
    out.push(nodeG(c, it.id, it.label, tip, it.x, it.y, body));
  });
  const W = x - GX + 44;
  return finish(out.join(""), W, y - GY, items.map((it) => ({ id: it.id, x: it.x, y: it.y, w: it.w, h: it.h })), []);
}

// ---------------------------------------------------------------- State machine

export function stateSvg(machine, opts) {
  const c = ctx(opts);
  const m = machine || {};
  const names = [];
  const seen = new Set();
  const add = (s) => {
    if (s == null) return;
    const k = String(s);
    if (!seen.has(k)) {
      seen.add(k);
      names.push(k);
    }
  };
  arr(m.states).forEach(add);
  const trans = arr(m.transitions).filter((t) => t && t.from != null && t.to != null);
  trans.forEach((t) => {
    add(t.from);
    add(t.to);
  });
  if (!names.length) return empty();
  const initial = m.initial != null && seen.has(String(m.initial)) ? String(m.initial) : names[0];
  const out = new Map();
  names.forEach((s) => out.set(s, []));
  trans.forEach((t) => {
    if (String(t.from) !== String(t.to)) out.get(String(t.from)).push(String(t.to));
  });
  const layerOf = new Map();
  const layers = [];
  const bfs = (start, base) => {
    layerOf.set(start, base);
    const queue = [start];
    while (queue.length) {
      const s = queue.shift();
      const l = layerOf.get(s);
      (layers[l] = layers[l] || []).push(s);
      out.get(s).forEach((t) => {
        if (!layerOf.has(t)) {
          layerOf.set(t, l + 1);
          queue.push(t);
        }
      });
    }
  };
  bfs(initial, 0);
  names.forEach((s) => {
    if (!layerOf.has(s)) bfs(s, layers.length);
  });
  const finals = new Set(names.filter((s) => !out.get(s).length));
  const H = 36;
  const GAPY = 44;
  const GAPX = 96;
  const loops = new Map();
  trans.forEach((t) => {
    if (String(t.from) === String(t.to)) loops.set(String(t.from), (loops.get(String(t.from)) || 0) + 1);
  });
  const maxLoops = Math.max(0, ...loops.values());
  const top = 34 + 12 * Math.max(0, maxLoops - 1);
  const boxes = new Map();
  let x = 34;
  let total = 0;
  const colH = layers.map((l) => (l || []).length * (H + GAPY) - GAPY);
  const maxH = Math.max(H, ...colH);
  layers.forEach((l, li) => {
    const cw = Math.max(64, ...l.map((s) => tw(clip(s, 22)) + 28));
    const y0 = top + (maxH - colH[li]) / 2;
    l.forEach((s, i) => boxes.set(s, { id: s, x: x + (cw - Math.max(64, tw(clip(s, 22)) + 28)) / 2, y: y0 + i * (H +
        GAPY),
      w: Math.max(64, tw(clip(s, 22)) + 28), h: H }));
    x += cw + GAPX;
    total = x - GAPX;
  });
  const parts = [];
  const pairIdx = new Map();
  const loopIdx = new Map();
  const arrowAttrs = (t) => 'stroke="' + v("--text-2") + '" stroke-width="1.3"' +
    (t.guessed ? ' stroke-dasharray="5 3" stroke-opacity=".65"' : "") + ' marker-end="url(#sysd-arrow)"';
  const ini = boxes.get(initial);
  const dotC = [12, ini.y + H / 2];
  parts.push('<circle cx="12" cy="' + f(dotC[1]) + '" r="7" fill="' + v("--text-1") +
      '"><title>initial</title></circle>');
  const first = clipRect(ini, dotC[0], dotC[1]);
  parts.push(pathG(c, initial, initial, line([19, dotC[1]], first), arrowAttrs({}), "initial"));
  trans.forEach((t) => {
    const a = boxes.get(String(t.from));
    const b = boxes.get(String(t.to));
    const title = t.from + " → " + t.to + (t.label ? " (" + t.label + ")" : "") + (t.guessed ? " guessed" : "");
    if (a === b) {
      const k = loopIdx.get(a.id) || 0;
      loopIdx.set(a.id, k + 1);
      const lift = 22 + 12 * k;
      const x1 = a.x + a.w / 2 - 12;
      const x2 = a.x + a.w / 2 + 12;
      const d = "M" + f(x1) + " " + f(a.y) + "C" + f(x1 - 8) + " " + f(a.y - lift) + " " + f(x2 + 8) + " " +
          f(a.y - lift) +
        " " + f(x2) + " " + f(a.y);
      parts.push(pathG(c, a.id, a.id, d, arrowAttrs(t), title));
      if (t.label) parts.push(halo(a.x + a.w / 2, a.y - lift * 0.75 - 3, clip(t.label, 18)));
      return;
    }
    const key = a.id + ">" + b.id;
    const k = pairIdx.get(key) || 0;
    pairIdx.set(key, k + 1);
    const mx = (a.x + a.w / 2 + b.x + b.w / 2) / 2;
    const my = (a.y + a.h / 2 + b.y + b.h / 2) / 2;
    const dx = b.x + b.w / 2 - (a.x + a.w / 2);
    const dy = b.y + b.h / 2 - (a.y + a.h / 2);
    const len = Math.hypot(dx, dy) || 1;
    const off = 18 + 16 * k;
    const cx = mx + (-dy / len) * off;
    const cy = my + (dx / len) * off;
    const p = clipRect(a, cx, cy);
    const q = clipRect(b, cx, cy);
    parts.push(pathG(c, a.id, b.id, "M" + f(p[0]) + " " + f(p[1]) + "Q" + f(cx) + " " + f(cy) + " " + f(q[0]) + " " +
        f(q[1]),
      arrowAttrs(t), title));
    if (t.label) parts.push(halo(0.25 * p[0] + 0.5 * cx + 0.25 * q[0], 0.25 * p[1] + 0.5 * cy +
        0.25 * q[1] - 3, clip(t.label, 18)));
  });
  const list = [];
  names.forEach((s) => {
    const b = boxes.get(s);
    const fin = finals.has(s);
    const sk = strokeOf(c, s);
    let body = '<rect width="' + f(b.w) + '" height="' + H + '" rx="12" fill="' + v("--surface-2") + '" stroke="' + sk +
      '" stroke-width="' + swOf(c, s) + '"/>';
    if (fin) body += '<rect x="3" y="3" width="' + f(b.w - 6) + '" height="' + (H - 6) +
        '" rx="9" fill="none" stroke="' + sk +
      '" stroke-width="1"/>';
    body += text(b.w / 2, 22, clip(s, 22), 12, v("--text-1"), ' text-anchor="middle" font-weight="600"');
    parts.push(nodeG(c, s, s, s + (fin ? "\nfinal" : s === initial ? "\ninitial" : ""), b.x, b.y, body));
    list.push(b);
  });
  return finish(parts.join(""), Math.max(total, 40), top + maxH, list, []);
}

// ---------------------------------------------------------------- Use cases

function actorFig(kind, sk) {
  const d = kind === "external" ? ' stroke-dasharray="3 2"' : "";
  return '<g fill="none" stroke="' + sk + '" stroke-width="1.5"' + d +
      '><circle cx="45" cy="8" r="6"/><path d="M45 14V30M33 20H57M45 30L35 42M45 30L55 42"/></g>';
}

export function usecaseSvg(uc, opts) {
  const c = ctx(opts);
  const actors = uniq(arr(uc && uc.actors), "id");
  const cases = uniq(arr(uc && uc.cases), "id");
  if (!actors.length && !cases.length) return empty();
  const groupLabel = new Map(arr(uc && uc.groups).filter((g) => g && g.id != null).map((g) => [String(g.id), g.label]));
  const buckets = new Map();
  cases.forEach((cs) => {
    const g = cs.group != null && cs.group !== "" ? String(cs.group) : "";
    if (!buckets.has(g)) buckets.set(g, []);
    buckets.get(g).push(cs);
  });
  const EW = 176;
  const EH = 54;
  const EG = 12;
  const BX = 140;
  const BP = 16;
  const BH = 30;
  let gy = BH + BP;
  const gboxes = [];
  const ells = [];
  buckets.forEach((list, g) => {
    const cols = Math.min(2, list.length);
    const rows = Math.ceil(list.length / cols);
    const head = g ? 24 : 0;
    const gw = cols * EW + (cols - 1) * EG + 24;
    const gh = head + rows * EH + (rows - 1) * EG + 24;
    gboxes.push({ id: g, label: g ? groupLabel.get(g) || g : "", x: BX + BP, y: gy, w: gw, h: gh });
    list.forEach((cs, i) => {
      ells.push({ cs, id: String(cs.id), x: BX + BP + 12 + (i % cols) * (EW + EG), y: gy + head + 12 +
          Math.floor(i / cols) * (EH + EG), w: EW, h: EH });
    });
    gy += gh + 16;
  });
  const bw = Math.max(0, ...gboxes.map((g) => g.w)) + 2 * BP;
  const bh = Math.max(gy - 16 + BP, BH + 2 * BP + 40);
  const AH = 76;
  const ah = actors.length * (AH + 20) - 20;
  const totalH = Math.max(bh, ah);
  const step = actors.length ? Math.max(AH + 20, totalH / actors.length) : 0;
  const at = actors.map((a, i) => ({ a, id: String(a.id), x: 0, y: step * (i + 0.5) - AH / 2 +
      (actors.length > 1 ? 0 : 0), w: 90, h: AH }));
  const byCase = new Map(ells.map((e) => [e.id, e]));
  const byActor = new Map(at.map((a) => [a.id, a]));
  const out = [];
  out.push('<rect x="' + BX + '" y="0" width="' + f(bw) + '" height="' + f(totalH) + '" rx="10" fill="none" stroke="' +
      v("--line") +
    '" stroke-opacity=".7"><title>System boundary</title></rect>');
  out.push(text(BX + BP, 20, clip(uc && uc.title ? uc.title : "System", 40), 13, v("--text-2"), ' font-weight="600"'));
  gboxes.forEach((g) => {
    out.push('<rect x="' + f(g.x) + '" y="' + f(g.y) + '" width="' + f(g.w) + '" height="' + f(g.h) +
        '" rx="8" fill="' + v("--surface-1") +
      '" stroke="' + v("--track") + '"><title>' + esc(g.label) + "</title></rect>");
    if (g.label) out.push(text(g.x + 12, g.y +
        17, clip(g.label, Math.floor((g.w - 24) / CH)), 11, v("--text-2"), ' font-weight="600"'));
  });
  arr(uc && uc.links).forEach((l) => {
    const a = l && byActor.get(String(l.actor));
    const e = l && byCase.get(String(l.case));
    if (!a || !e) return;
    const sx = a.x + 62;
    const sy = a.y + 24;
    const rx = e.w / 2;
    const ry = e.h / 2;
    const dx = sx - (e.x + rx);
    const dy = sy - (e.y + ry);
    const s = 1 / Math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2 || 1);
    const p = [sx, sy];
    const q = [e.x + rx + dx * s, e.y + ry + dy * s];
    out.push(pathG(c, a.id, e.id, line(p, q), 'stroke="' + v("--text-2") +
        '" stroke-width="1.1" stroke-opacity=".8"', a.id + " → " + e.id));
  });
  at.forEach((a) => {
    const sk = strokeOf(c, a.id);
    const label = String(a.a.label == null ? a.id : a.a.label);
    const body = actorFig(a.a.kind, sk) + text(45, 58, clip(label, 14), 11, v("--text-1"), ' text-anchor="middle"') +
      (a.a.kind ? text(45, 70, clip(a.a.kind, 14), 10, v("--text-3"), ' text-anchor="middle"') : "");
    out.push(nodeG(c, a.id, label, label + (a.a.kind ? "\n" + a.a.kind : ""), a.x, a.y, body));
  });
  ells.forEach((e) => {
    const lines = wrap2(e.cs.label == null ? e.id : e.cs.label, 22);
    const sk = strokeOf(c, e.id);
    let body = '<ellipse cx="' + e.w / 2 + '" cy="' + e.h / 2 + '" rx="' + e.w / 2 + '" ry="' + e.h / 2 + '" fill="' +
        v("--surface-2") +
      '" stroke="' + sk + '" stroke-width="' + swOf(c, e.id) + '"/>';
    const y0 = lines.length > 1 ? e.h / 2 - 3 : e.h / 2 + 4;
    lines.forEach((l, i) => {
      body += text(e.w / 2, y0 + i * 14, l, 12, v("--text-1"), ' text-anchor="middle"');
    });
    out.push(nodeG(c, e.id, String(e.cs.label == null ? e.id : e.cs.label),
      String(e.cs.label == null ? e.id : e.cs.label) + (e.cs.sub ? "\n" + e.cs.sub : ""), e.x, e.y, body));
  });
  const boxes = at.map((a) => ({ id: a.id, x: a.x, y: a.y, w: a.w, h: a.h })).concat(ells.map((e) => ({ id: e.id,
      x: e.x, y: e.y, w: e.w, h: e.h })));
  const bands = [{ id: "boundary", x: BX, y: 0, w: bw, h: totalH }].concat(gboxes.map((g) => ({ id: "g:" +
      g.id, x: g.x, y: g.y, w: g.w, h: g.h })));
  return finish(out.join(""), BX + bw, totalH, boxes, bands);
}

// ---------------------------------------------------------------- Activity

export function activitySvg(item, opts) {
  const c = ctx(opts);
  const steps = uniq(arr(item && item.steps), "id");
  if (!steps.length) return empty();
  const byId = new Map();
  const nodes = steps.map((s) => {
    const id = String(s.id);
    const kind = String(s.kind || "action");
    const label = String(s.label == null ? id : s.label);
    let w;
    let h;
    if (kind === "start" || kind === "end") {
      w = 18;
      h = 18;
    } else if (kind === "merge") {
      w = 28;
      h = 28;
    } else if (kind === "decision" || kind === "loop") {
      w = Math.max(80, Math.min(180, tw(clip(label, 24)) + 44));
      h = 46;
    } else {
      w = Math.max(96, Math.min(230, tw(clip(label, 32)) + 28));
      h = 34;
    }
    const n = { id, kind, label, s, w, h, rank: 0, col: 0, x: 0, y: 0 };
    byId.set(id, n);
    return n;
  });
  const edges = arr(item.edges).filter((e) => e && byId.has(String(e.from)) && byId.has(String(e.to)) &&
      String(e.from) !== String(e.to));
  const outs = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => outs.get(String(e.from)).push(e));
  // DFS: preorder and back edges
  const state = new Map();
  const back = new Set();
  const pre = [];
  const dfs = (root) => {
    const stack = [[root, 0]];
    state.set(root.id, 1);
    pre.push(root);
    while (stack.length) {
      const top = stack[stack.length - 1];
      const list = outs.get(top[0].id);
      if (top[1] >= list.length) {
        state.set(top[0].id, 2);
        stack.pop();
        continue;
      }
      const e = list[top[1]++];
      const t = byId.get(String(e.to));
      if (state.get(t.id) === 1) back.add(e);
      else if (!state.has(t.id)) {
        state.set(t.id, 1);
        pre.push(t);
        stack.push([t, 0]);
      }
    }
  };
  const startNode = nodes.find((n) => n.kind === "start") || nodes[0];
  dfs(startNode);
  nodes.forEach((n) => {
    if (!state.has(n.id)) dfs(n);
  });
  const order = new Map(pre.map((n, i) => [n.id, i]));
  const fwd = edges.filter((e) => !back.has(e));
  // longest-path ranks over forward edges, in preorder (forward edges only go to later... not guaranteed), so relax
  for (let pass = 0; pass < nodes.length; pass++) {
    let changed = false;
    fwd.forEach((e) => {
      const a = byId.get(String(e.from));
      const b = byId.get(String(e.to));
      if (b.rank < a.rank + 1) {
        b.rank = a.rank + 1;
        changed = true;
      }
    });
    if (!changed) break;
  }
  const ranks = [];
  nodes.forEach((n) => {
    (ranks[n.rank] = ranks[n.rank] || []).push(n);
  });
  const colW = Math.max(...nodes.map((n) => n.w)) + 44;
  const GAPY = 34;
  let y = 0;
  const maxCols = Math.max(...ranks.map((r) => (r ? r.length : 0)));
  const total = maxCols * colW;
  ranks.forEach((r) => {
    if (!r) return;
    r.sort((a, b) => order.get(a.id) - order.get(b.id));
    const rh = Math.max(...r.map((n) => n.h));
    r.forEach((n, i) => {
      n.x = 56 + (total - r.length * colW) / 2 + i * colW + (colW - n.w) / 2;
      n.y = y + (rh - n.h) / 2;
    });
    y += rh + GAPY;
  });
  const H = y - GAPY;
  const parts = [];
  const isErr = (e) => byId.get(String(e.to)).kind === "error" || byId.get(String(e.from)).kind === "error";
  const leftX = 22;
  let loopK = 0;
  edges.forEach((e) => {
    const a = byId.get(String(e.from));
    const b = byId.get(String(e.to));
    const err = isErr(e);
    const attrs = 'stroke="' + v(err ? "--danger" : "--text-2") + '" stroke-width="1.3" marker-end="url(#sysd-arrow' +
        (err ? "-err" : "") + ')"';
    const title = a.label + " → " + b.label + (e.label ? " (" + e.label + ")" : "");
    if (back.has(e)) {
      const lx = leftX - 6 * (loopK++ % 3);
      const ya = a.y + a.h / 2;
      const yb = b.y + b.h / 2;
      const d = "M" + f(a.x) + " " + f(ya) + "H" + lx + "V" + f(yb) + "H" + f(b.x - 1);
      parts.push(pathG(c, a.id, b.id, d, attrs, title));
      if (e.label) parts.push('<text x="' + (lx + 4) + '" y="' + f((ya + yb) / 2) + '" font-size="11" fill="' +
          v("--text-2") +
        '" stroke="' + v("--surface-1") + '" stroke-width="3" paint-order="stroke">' + esc(clip(e.label, 12)) +
            "</text>");
      return;
    }
    let p;
    let q;
    if (b.rank > a.rank) {
      p = [a.x + a.w / 2, a.y + a.h];
      q = [b.x + b.w / 2, b.y];
      if (Math.abs(p[0] - q[0]) > 1) {
        const my = f(a.y + a.h + GAPY / 2);
        const sx = a.kind === "decision" || a.kind === "loop" ? a.x + (q[0] > p[0] ? a.w : 0) : p[0];
        const sy = a.kind === "decision" || a.kind === "loop" ? a.y + a.h / 2 : p[1];
        const d = a.kind === "decision" || a.kind === "loop" ?
          "M" + f(sx) + " " + f(sy) + "H" + f(q[0]) + "V" + f(q[1]) :
          "M" + f(p[0]) + " " + f(p[1]) + "V" + my + "H" + f(q[0]) + "V" + f(q[1]);
        parts.push(pathG(c, a.id, b.id, d, attrs, title));
        if (e.label) parts.push(halo((sx +
            q[0]) / 2, a.kind === "decision" || a.kind === "loop" ? sy - 4 : +my - 4, clip(e.label, 12)));
        return;
      }
    } else {
      const L = link(a, b);
      p = L.p;
      q = L.q;
    }
    parts.push(pathG(c, a.id, b.id, line(p, q), attrs, title));
    if (e.label) parts.push('<text x="' + f(p[0] + 6) + '" y="' + f(p[1] + 14) + '" font-size="11" fill="' +
        v("--text-2") + '" stroke="' +
      v("--surface-1") + '" stroke-width="3" paint-order="stroke">' + esc(clip(e.label, 12)) + "</text>");
  });
  nodes.forEach((n) => {
    const sk = n.kind === "error" && c.sel !== n.id ? v("--danger") : strokeOf(c, n.id);
    const sw = swOf(c, n.id);
    let body;
    if (n.kind === "start") body = '<circle cx="9" cy="9" r="9" fill="' + v("--text-1") + '" stroke="' + sk +
        '" stroke-width="' + sw + '"/>';
    else if (n.kind === "end") body = '<circle cx="9" cy="9" r="9" fill="none" stroke="' + sk + '" stroke-width="' +
        Math.max(sw, 1.5) +
      '"/><circle cx="9" cy="9" r="5" fill="' + v("--text-1") + '"/>';
    else if (n.kind === "merge") body = '<path d="M14 0L28 14L14 28L0 14z" fill="' + v("--surface-2") + '" stroke="' +
        sk + '" stroke-width="' + sw + '"/>';
    else if (n.kind === "decision" || n.kind === "loop") body = '<path d="M' + n.w / 2 + " 0L" + n.w + " " + n.h / 2 +
        "L" + n.w / 2 + " " + n.h +
      "L0 " + n.h / 2 + 'z" fill="' + v("--surface-2") + '" stroke="' + sk + '" stroke-width="' + sw + '"' +
      (n.kind === "loop" ? ' stroke-dasharray="4 2"' : "") + "/>" +
      text(n.w / 2, n.h / 2 +
          4, clip(n.label, Math.floor((n.w - 36) / 6.5)), 11, v("--text-1"), ' text-anchor="middle"');
    else body = '<rect width="' + n.w + '" height="' + n.h + '" rx="' + (n.kind === "error" ? 8 : 12) + '" fill="' +
        v("--surface-2") + '" stroke="' + sk +
      '" stroke-width="' + sw + '"/>' + text(n.w / 2, n.h / 2 + 4, clip(n.label, Math.floor((n.w - 16) / 7)), 12,
      v(n.kind === "error" ? "--danger" : "--text-1"), ' text-anchor="middle"');
    parts.push(nodeG(c, n.id, n.label, n.label + "\n" + n.kind, n.x, n.y, body));
  });
  return finish(parts.join(""), 56 + total +
      12, H, nodes.map((n) => ({ id: n.id, x: n.x, y: n.y, w: n.w, h: n.h })), []);
}

// ---------------------------------------------------------------- Deployment

export function deploymentSvg(dep, opts) {
  const c = ctx(opts);
  const nodes = uniq(arr(dep && dep.nodes), "id");
  if (!nodes.length) return empty();
  const groups = uniq(arr(dep.groups), "id").map((g) => ({ id: String(g.id),
      label: String(g.label == null ? g.id : g.label), list: [] }));
  const gById = new Map(groups.map((g) => [g.id, g]));
  const loose = { id: "", label: "", list: [], frame: false };
  nodes.forEach((n) => {
    const g = n.group != null ? gById.get(String(n.group)) : null;
    (g || loose).list.push(n);
  });
  const all = groups.filter((g) => g.list.length);
  if (loose.list.length) all.push(loose);
  const NW = 156;
  const D = 10;
  const items = new Map();
  const cells = all.map((g) => {
    const framed = g.frame !== false;
    const cols = Math.max(1, Math.min(framed ? 2 : 3, g.list.length));
    const rows = Math.ceil(g.list.length / cols);
    const head = framed ? 26 : 0;
    const pad = framed ? 12 : 0;
    const gw = cols * NW + (cols - 1) * 14 + 2 * pad;
    const rh = [];
    g.list.forEach((n, i) => {
      const r = Math.floor(i / cols);
      rh[r] = Math.max(rh[r] || 0, n.kind === "store" ? 52 : 42);
    });
    const gh = head + pad + rh.reduce((a, b) => a + b + 14, 0) - 14 + pad;
    return { g, framed, cols, head, pad, gw, gh: framed ? gh : gh, rh };
  });
  const gcols = Math.max(1, Math.ceil(Math.sqrt(cells.length)));
  const GX = 56;
  const GY = 46;
  const cw = new Array(gcols).fill(0);
  const rhs = [];
  cells.forEach((cell, i) => {
    cell.k = i % gcols;
    cell.r = Math.floor(i / gcols);
    cw[cell.k] = Math.max(cw[cell.k], cell.gw);
    rhs[cell.r] = Math.max(rhs[cell.r] || 0, cell.gh);
  });
  const cx = [];
  let x = 0;
  cw.forEach((w) => {
    cx.push(x);
    x += w + GX;
  });
  const cy = [];
  let y = D;
  rhs.forEach((h) => {
    cy.push(y);
    y += h + GY;
  });
  const parts = [];
  const bands = [];
  const boxes = [];
  cells.forEach((cell) => {
    cell.x = cx[cell.k];
    cell.y = cy[cell.r];
    if (cell.framed) {
      const gx = cell.x;
      const gy = cell.y;
      parts.push('<g><title>' + esc(cell.g.label) + "</title>" +
        '<polygon points="' + [gx, gy, gx + D, gy - D, gx + cell.gw + D, gy - D, gx + cell.gw, gy].map(f).join(" ") +
            '" fill="' + v("--track") +
        '" stroke="' + v("--line") + '" stroke-opacity=".6"/>' +
        '<polygon points="' + [gx + cell.gw, gy, gx + cell.gw + D, gy - D, gx + cell.gw + D, gy + cell.gh - D, gx +
            cell.gw, gy + cell.gh].map(f).join(" ") +
        '" fill="' + v("--surface-2") + '" stroke="' + v("--line") + '" stroke-opacity=".6"/>' +
        '<rect x="' + f(gx) + '" y="' + f(gy) + '" width="' + f(cell.gw) + '" height="' + f(cell.gh) + '" fill="' +
            v("--surface-1") +
        '" stroke="' + v("--line") + '" stroke-opacity=".8"/>' +
        text(gx + 12, gy +
            18, clip(cell.g.label, Math.floor((cell.gw - 24) / CH)), 12, v("--text-2"), ' font-weight="600"') + "</g>");
      bands.push({ id: "g:" + cell.g.id, x: gx, y: gy - D, w: cell.gw + D, h: cell.gh + D });
    }
    let ry = cell.y + cell.head + cell.pad;
    cell.g.list.forEach((n, i) => {
      const col = i % cell.cols;
      const r = Math.floor(i / cell.cols);
      if (col === 0 && r > 0) ry += cell.rh[r - 1] + 14;
      const h = n.kind === "store" ? 52 : 42;
      const b = { id: String(n.id), x: cell.x + cell.pad + col * (NW + 14), y: ry + (cell.rh[r] - h) / 2, w: NW, h, n };
      items.set(b.id, b);
      boxes.push(b);
    });
  });
  const edgeParts = [];
  arr(dep.edges).forEach((e) => {
    const a = e && items.get(String(e.from));
    const b = e && items.get(String(e.to));
    if (!a || !b || a === b) return;
    const L = link(a, b);
    edgeParts.push(pathG(c, a.id, b.id, line(L.p, L.q), 'stroke="' + v("--text-2") +
        '" stroke-width="1.3" marker-end="url(#sysd-arrow)"',
      a.n.label + " → " + b.n.label + (e.label ? " (" + e.label + ")" : "")));
    if (e.label && L.len > tw(clip(e.label, 16)) + 20) edgeParts.push(halo((L.p[0] + L.q[0]) / 2, (L.p[1] +
        L.q[1]) / 2 - 4, clip(e.label, 16)));
  });
  parts.push(edgeParts.join(""));
  boxes.forEach((b) => {
    const n = b.n;
    const sk = strokeOf(c, b.id);
    const sw = swOf(c, b.id);
    const label = String(n.label == null ? b.id : n.label);
    let shape;
    if (n.kind === "store") {
      const e = 7;
      shape = '<path d="M0 ' + e + "a" + NW / 2 + " " + e + " 0 0 1 " + NW + " 0v" + (b.h - 2 * e) + "a" + NW / 2 +
          " " + e + " 0 0 1 " + -NW +
        ' 0z" fill="' + v("--surface-2") + '" stroke="' + sk + '" stroke-width="' + sw + '"/><path d="M0 ' + e + "a" +
            NW / 2 + " " + e +
        " 0 0 0 " + NW + ' 0" fill="none" stroke="' + sk + '" stroke-width="' + sw + '"/>';
    } else if (n.kind === "external") {
      shape = '<rect width="' + NW + '" height="' + b.h + '" rx="6" fill="' + v("--surface-1") + '" stroke="' +
        (c.sel === b.id ? sk : v("--text-3")) + '" stroke-width="' + sw + '" stroke-dasharray="5 3"/>';
    } else {
      shape = '<rect width="' + NW + '" height="' + b.h + '" rx="6" fill="' + v("--surface-2") + '" stroke="' + sk +
          '" stroke-width="' + sw + '"/>';
    }
    const ty = n.kind === "store" ? 26 : 19;
    const body = shape + text(10, ty, clip(label, 20), 12, v("--text-1"), ' font-weight="600"') +
      (n.sub ? text(10, ty + 15, clip(n.sub, 24), 11, v("--text-2")) : "");
    parts.push(nodeG(c, b.id, label, label + (n.sub ? "\n" + n.sub : "") + (n.kind ? "\n" +
        n.kind : ""), b.x, b.y, body));
  });
  const W = x - GX + D;
  return finish(parts.join(""), W, y - GY, boxes.map((b) => ({ id: b.id, x: b.x, y: b.y, w: b.w, h: b.h })), bands);
}

// ---------------------------------------------------------------- Class / module

export function classSvg(cls, opts) {
  const c = ctx(opts);
  const nodes = uniq(arr(cls && cls.nodes), "id");
  if (!nodes.length) return empty();
  const byId = new Map();
  const items = nodes.map((n) => {
    const id = String(n.id);
    const label = String(n.label == null ? id : n.label);
    const cut = (list) => {
      const l = arr(list);
      return l.length > CAP ? { rows: l.slice(0, CAP).concat(["+" + (l.length - CAP) +
          " more"]), n: l.length } : { rows: l.slice(), n: l.length };
    };
    const at = cut(n.attrs);
    const me = cut(n.methods);
    const stereo = n.kind && n.kind !== "class" ? String(n.kind) : "";
    let wmax = tw(clip(label, 34)) + 16;
    at.rows.concat(me.rows).forEach((r) => {
      wmax = Math.max(wmax, tw(clip(r, 40)) + 16);
    });
    const head = stereo ? 34 : 24;
    const ca = at.rows.length ? at.rows.length * 16 + 6 : 8;
    const cm = me.rows.length ? me.rows.length * 16 + 6 : 8;
    const it = { id, label, n, at, me, stereo, head, ca, cm, w: Math.max(130, Math.min(280, wmax)), h: head + ca +
        cm, x: 0, y: 0, depth: 0, group: n.group == null ? "" : String(n.group) };
    byId.set(id, it);
    return it;
  });
  const es = arr(cls.edges).filter((e) => e && byId.has(String(e.from)) && byId.has(String(e.to)) &&
      String(e.from) !== String(e.to));
  const ext = es.filter((e) => e.kind === "extends");
  for (let pass = 0; pass < items.length; pass++) {
    let changed = false;
    ext.forEach((e) => {
      const ch = byId.get(String(e.from));
      const base = byId.get(String(e.to));
      if (ch.depth < base.depth + 1 && base.depth + 1 <= items.length) {
        ch.depth = base.depth + 1;
        changed = true;
      }
    });
    if (!changed) break;
  }
  const gl = new Map(arr(cls.groups).filter((g) => g && g.id != null).map((g) => [String(g.id),
      g.label == null ? String(g.id) : g.label]));
  const order = [];
  const seenG = new Set();
  arr(cls.groups).forEach((g) => {
    if (g && g.id != null && !seenG.has(String(g.id))) {
      seenG.add(String(g.id));
      order.push(String(g.id));
    }
  });
  items.forEach((it) => {
    if (!seenG.has(it.group)) {
      seenG.add(it.group);
      order.push(it.group);
    }
  });
  const LIM = 1200;
  const GX = 40;
  const GY = 34;
  const BP = 14;
  const BHEAD = 24;
  const bands = [];
  const parts = [];
  let y = 0;
  let maxW = 0;
  const bandParts = [];
  order.forEach((g) => {
    const list = items.filter((it) => it.group === g);
    if (!list.length) return;
    list.sort((a, b) => a.depth - b.depth || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
    const lines = [];
    let cur = null;
    let curDepth = -1;
    list.forEach((it) => {
      if (!cur || it.depth !== curDepth || cur.w + it.w + GX > LIM) {
        cur = { list: [], w: -GX, h: 0 };
        lines.push(cur);
        curDepth = it.depth;
      }
      cur.list.push(it);
      cur.w += it.w + GX;
      cur.h = Math.max(cur.h, it.h);
    });
    const bw = Math.max(...lines.map((l) => l.w)) + 2 * BP;
    let yy = y + BHEAD + BP;
    lines.forEach((l) => {
      let xx = BP;
      l.list.forEach((it) => {
        it.x = xx;
        it.y = yy;
        xx += it.w + GX;
      });
      yy += l.h + GY;
    });
    const bh = yy - GY + BP - y;
    const label = g ? gl.get(g) || g : "";
    bands.push({ id: "g:" + g, x: 0, y, w: bw, h: bh });
    bandParts.push('<g><title>' + esc(label) + '</title><rect x="0" y="' + f(y) + '" width="' + f(bw) + '" height="' +
        f(bh) + '" rx="8" fill="none" stroke="' +
      v("--track") + '"/>' + (label ? text(BP, y +
          17, clip(label, Math.floor((bw - 2 * BP) / CH)), 12, v("--text-2"), ' font-weight="600"') : "") + "</g>");
    maxW = Math.max(maxW, bw);
    y += bh + 24;
  });
  parts.push(bandParts.join(""));
  es.forEach((e) => {
    const a = byId.get(String(e.from));
    const b = byId.get(String(e.to));
    const isExt = e.kind === "extends";
    const attrs = 'stroke="' + v("--text-2") + '" stroke-width="1.2"' + (isExt ? ' marker-end="url(#sysd-tri)"' :
      ' stroke-dasharray="5 3" marker-end="url(#sysd-open)"');
    const L = link(a, b);
    parts.push(pathG(c, a.id, b.id, line(L.p, L.q), attrs, a.label + (isExt ? " extends " : " uses ") + b.label +
        (e.label ? " (" + e.label + ")" : "")));
    if (!isExt && e.label && L.len > tw(clip(e.label, 14)) + 24) parts.push(halo((L.p[0] + L.q[0]) / 2, (L.p[1] +
        L.q[1]) / 2 - 4, clip(e.label, 14)));
  });
  items.forEach((it) => {
    const sk = strokeOf(c, it.id);
    const rowsOf = (r, y0, n) => r.rows.map((s, i) => {
      const more = i === CAP && n > CAP;
      return text(8, y0 + 13 + i * 16, clip(s, 40), 11, v(more ? "--text-3" : "--text-1"));
    }).join("");
    let body = '<rect width="' + f(it.w) + '" height="' + f(it.h) + '" rx="4" fill="' + v("--surface-2") +
        '" stroke="' + sk + '" stroke-width="' + swOf(c, it.id) + '"/>' +
      '<path d="M0 ' + it.head + "V4a4 4 0 0 1 4-4h" + f(it.w - 8) + "a4 4 0 0 1 4 4V" + it.head + 'z" fill="' +
          v("--track") + '"/>';
    if (it.stereo) body += text(it.w / 2, 13, "«" + clip(it.stereo, 14) +
        "»", 10, v("--text-3"), ' text-anchor="middle"');
    body += text(it.w / 2, it.stereo ? 28 : 17, clip(it.label, Math.floor((it.w - 16) / CH)), 13, v("--text-1"), '' +
        ' text-anchor="middle" font-weight="700"') +
      '<path d="M0 ' + it.head + "H" + f(it.w) + "M0 " + (it.head + it.ca) + "H" + f(it.w) + '" stroke="' + sk +
          '" stroke-opacity=".6"/>' +
      rowsOf(it.at, it.head + 2, it.at.n) + rowsOf(it.me, it.head + it.ca + 2, it.me.n);
    parts.push(nodeG(c, it.id, it.label, it.label + (it.n.sub ? "\n" + it.n.sub : "") + "\n" + it.at.n +
        " attributes, " + it.me.n + " methods", it.x, it.y, body));
  });
  return finish(parts.join(""), maxW, y - 24, items.map((it) => ({ id: it.id, x: it.x, y: it.y, w: it.w, h: it.h })),
      bands);
}
