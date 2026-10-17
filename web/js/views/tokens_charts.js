// Small inline-SVG chart helpers for the Tokens page (R11.6). Pure functions: data in, HTML string out. No library,
// no inline style (CSP): colours come from classes (tk-m-<model>, tk-line-<n>) that read the design tokens, sizes from
// attributes. Every chart is an <svg role="img"> with an aria-label, bars/points carry data-tip (the hover tooltip is
// wired in tokens_history.js) and every chart is followed by a plain table (tableHtml) for keyboard and screen readers.

import { esc } from "../dom.js";
import { MISSING } from "../format.js";

const W = 640;
const PAD = { l: 46, r: 8, t: 8, b: 22 };

// 12.3k, 4.5M, 1.2G; 0 stays "0".
export function fmtN(n) {
  if (typeof n !== "number" || !isFinite(n)) return MISSING;
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1) + "G";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1) + "k";
  return String(Math.round(n * 10) / 10);
}

// A round upper bound for an axis: 1, 2, 2.5, 5 or 10 times a power of ten.
export function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const m = v / p;
  const step = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
  return step * p;
}

function num(n) {
  return Math.round(n * 10) / 10;
}

function svgOpen(h, label, cls) {
  return '<svg class="tk-svg ' + (cls || "") + '" viewBox="0 0 ' + W + " " + h + '" role="img" aria-label="' +
    esc(label) + '" preserveAspectRatio="xMidYMid meet" focusable="false">';
}

function gridAndAxis(h, max, fmt) {
  const plotH = h - PAD.t - PAD.b;
  let out = "";
  for (let i = 0; i <= 2; i++) {
    const y = num(PAD.t + plotH - (plotH * i) / 2);
    out += '<line class="tk-gl" x1="' + PAD.l + '" x2="' + (W - PAD.r) + '" y1="' + y + '" y2="' + y + '"/>' +
      '<text class="tk-ax" x="' + (PAD.l - 6) + '" y="' + (y + 3) + '" text-anchor="end">' +
      esc(fmt((max * i) / 2)) + "</text>";
  }
  return out;
}

function xLabels(items, h, xOf) {
  const every = Math.max(1, Math.ceil(items.length / 8));
  let out = "";
  items.forEach(function (it, i) {
    if (i % every !== 0) return;
    out += '<text class="tk-ax" x="' + num(xOf(i)) + '" y="' + (h - 6) + '" text-anchor="middle">' +
      esc(it.label) + "</text>";
  });
  return out;
}

// Stacked bars per slot. slots: [{label, tip, parts: {model: value}}]; keys: stack order bottom-up.
export function stackedBars(slots, keys, opts) {
  const h = (opts && opts.h) || 190;
  const fmt = (opts && opts.fmt) || fmtN;
  const total = slots.map(function (s) {
    return keys.reduce(function (a, k) {
      return a + (s.parts[k] || 0);
    }, 0);
  });
  const max = niceMax(Math.max.apply(null, total.concat([0])));
  const plotH = h - PAD.t - PAD.b;
  const plotW = W - PAD.l - PAD.r;
  const slot = plotW / Math.max(slots.length, 1);
  const bw = Math.max(1.5, Math.min(slot * 0.72, 40));
  const xOf = function (i) {
    return PAD.l + slot * (i + 0.5);
  };
  let out = svgOpen(h, opts.label) + gridAndAxis(h, max, fmt);
  slots.forEach(function (s, i) {
    let y = PAD.t + plotH;
    let g = '<g class="tk-bar" data-tip="' + esc(s.tip) + '">' + '<rect class="tk-hit" x="' + num(PAD.l + slot * i) +
      '" y="' + PAD.t + '" width="' + num(slot) + '" height="' + plotH + '"/>';
    keys.forEach(function (k) {
      const v = s.parts[k] || 0;
      if (v <= 0) return;
      const bh = Math.max(0.5, (v / max) * plotH);
      y -= bh;
      g += '<rect class="tk-m-' + esc(k) + '" x="' + num(xOf(i) - bw / 2) + '" y="' + num(y) + '" width="' + num(bw) +
        '" height="' + num(bh) + '"/>';
    });
    out += g + "</g>";
  });
  return out + xLabels(slots, h, xOf) + "</svg>";
}

// Line chart. series: [{name, cls, pts: [{x, y, tip}]}]; x numeric (any unit), xlabels: [{x, label}].
export function lineChart(series, xmin, xmax, ymax, xlabels, opts) {
  const h = (opts && opts.h) || 190;
  const fmt = (opts && opts.fmt) || fmtN;
  const max = (opts && opts.fixedMax) || niceMax(ymax);
  const plotH = h - PAD.t - PAD.b;
  const plotW = W - PAD.l - PAD.r;
  const span = xmax > xmin ? xmax - xmin : 1;
  const px = function (x) {
    return num(PAD.l + ((x - xmin) / span) * plotW);
  };
  const py = function (y) {
    return num(PAD.t + plotH - (Math.min(y, max) / max) * plotH);
  };
  let out = svgOpen(h, opts.label) + gridAndAxis(h, max, fmt);
  xlabels.forEach(function (l, i) {
    const anchor = xlabels.length > 1 && i === xlabels.length - 1 && l.edge ? "end" : "middle";
    out += '<text class="tk-ax" x="' + px(l.x) + '" y="' + (h - 6) + '" text-anchor="' + anchor + '">' +
      esc(l.label) + "</text>";
  });
  series.forEach(function (s) {
    if (!s.pts.length) return;
    const d = s.pts.map(function (p, i) {
      return (i ? "L" : "M") + px(p.x) + " " + py(p.y);
    }).join("");
    out += '<path class="tk-path ' + esc(s.cls) + '" d="' + d + '"/>';
    const every = Math.max(1, Math.ceil(s.pts.length / 120));
    s.pts.forEach(function (p, i) {
      if (i % every !== 0 && i !== s.pts.length - 1) return;
      out += '<circle class="tk-dot ' + esc(s.cls) + '" cx="' + px(p.x) + '" cy="' + py(p.y) + '" r="3" data-tip="' +
        esc(p.tip) + '"/>';
    });
  });
  return out + "</svg>";
}

function cut(text, n) {
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

// Horizontal bars, one row each. rows: [{label, value, cls, tip, text}]; text is the value label at the bar end.
export function hBars(rows, opts) {
  const rowH = 22;
  const labelW = 150;
  const valW = 64;
  const h = Math.max(rows.length, 1) * rowH + 4;
  const barW = W - labelW - valW - 8;
  const max = Math.max.apply(null, rows.map(function (r) {
    return r.value;
  }).concat([0])) || 1;
  let out = svgOpen(h, opts.label, "tk-svg-h");
  rows.forEach(function (r, i) {
    const y = 2 + i * rowH;
    const w = r.value > 0 ? Math.max(1.5, (r.value / max) * barW) : 0;
    out += '<g class="tk-bar" data-tip="' + esc(r.tip) + '"><rect class="tk-hit" x="0" y="' + y + '" width="' + W +
      '" height="' + rowH + '"/><text class="tk-lb" x="0" y="' + (y + 14) + '">' + esc(cut(r.label, 24)) + "</text>" +
      '<rect class="' + esc(r.cls) + '" x="' + labelW + '" y="' + (y + 4) + '" width="' + num(w) + '" height="' +
      (rowH - 8) + '" rx="2"/><text class="tk-lb tk-val" x="' + (W - 2) + '" y="' + (y + 14) +
      '" text-anchor="end">' + esc(r.text) + "</text></g>";
  });
  return out + "</svg>";
}

// Donut of shares. parts: [{key, value, tip}]. Segments use pathLength 100 so the dash maths is in percent.
export function donut(parts, centerText, opts) {
  const total = parts.reduce(function (a, p) {
    return a + p.value;
  }, 0);
  let out = '<svg class="tk-svg tk-svg-d" viewBox="0 0 120 120" role="img" aria-label="' + esc(opts.label) +
    '" focusable="false"><circle class="tk-ring" cx="60" cy="60" r="42"/>';
  let at = 0;
  if (total > 0) {
    parts.forEach(function (p) {
      if (p.value <= 0) return;
      const share = (p.value / total) * 100;
      out += '<circle class="tk-seg tk-s-' + esc(p.key) + '" cx="60" cy="60" r="42" pathLength="100" ' +
        'stroke-dasharray="' + num(share) + " " + num(100 - share) + '" stroke-dashoffset="' + num(25 - at) +
        '" data-tip="' + esc(p.tip) + '"/>';
      at += share;
    });
  }
  return out + '<text class="tk-ctr" x="60" y="64" text-anchor="middle">' + esc(centerText) + "</text></svg>";
}

// One 100% bar. parts as in donut.
export function shareBar(parts, opts) {
  const total = parts.reduce(function (a, p) {
    return a + p.value;
  }, 0);
  const w = 300;
  let out = '<svg class="tk-svg tk-svg-s" viewBox="0 0 ' + w + ' 18" role="img" aria-label="' + esc(opts.label) +
    '" focusable="false"><rect class="tk-ring-r" x="0" y="2" width="' + w + '" height="14" rx="3"/>';
  let x = 0;
  if (total > 0) {
    parts.forEach(function (p) {
      if (p.value <= 0) return;
      const seg = (p.value / total) * w;
      out += '<rect class="tk-m-' + esc(p.key) + '" x="' + num(x) + '" y="2" width="' + num(seg) +
        '" height="14" data-tip="' + esc(p.tip) + '"/>';
      x += seg;
    });
  }
  return out + "</svg>";
}

// A plain table behind a disclosure, the text alternative of a chart. rows: arrays of strings.
export function tableHtml(caption, heads, rows) {
  const th = heads.map(function (h, i) {
    return '<th scope="col"' + (i ? ' class="num"' : "") + ">" + esc(h) + "</th>";
  }).join("");
  const body = rows.map(function (r) {
    return "<tr>" + r.map(function (c, i) {
      return (i ? '<td class="num">' : '<th scope="row">') + esc(c) + (i ? "</td>" : "</th>");
    }).join("") + "</tr>";
  }).join("");
  return '<details class="tk-tbl"><summary>Data table</summary><table><caption>' + esc(caption) +
    "</caption><thead><tr>" + th + "</tr></thead><tbody>" + body + "</tbody></table></details>";
}
