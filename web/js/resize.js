// Drag-to-resize for the left nav and the right side panel (R10.3). Widths live in --w-nav / --w-side on :root.
const KEY = "rb.widths";
const STEP = 16;
const MIN_W = 768;
const SPECS = {
  nav: { cssVar: "--w-nav", def: 232, min: 56, max: function () { return 360; }, label: "Resize navigation", sign: 1 },
  side: { cssVar: "--w-side", def: 320, min: 280, max: function () { return Math.min(720, Math.round(window.innerWidth * 0.6)); }, label: "Resize side panel", sign: -1 },
};

function clamp(spec, v) {
  return Math.max(spec.min, Math.min(spec.max(), Math.round(v)));
}

function load() {
  try {
    const o = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return o && typeof o === "object" ? o : {};
  } catch (e) {
    return {};
  }
}

function save(name, value) {
  try {
    const o = load();
    if (value === null) delete o[name]; else o[name] = value;
    window.localStorage.setItem(KEY, JSON.stringify(o));
  } catch (e) { /* storage unavailable */ }
}

export function initResize() {
  const app = document.getElementById("app");
  if (!app) return;
  const saved = load();
  const root = document.documentElement;
  const cur = {};
  function apply(name, value) {
    const spec = SPECS[name];
    cur[name] = clamp(spec, value);
    root.style.setProperty(spec.cssVar, cur[name] + "px");
    handles[name].setAttribute("aria-valuenow", String(cur[name]));
  }
  const handles = {};
  Object.keys(SPECS).forEach(function (name) {
    const spec = SPECS[name];
    const h = document.createElement("div");
    h.className = "rz rz-" + name;
    h.tabIndex = 0;
    h.setAttribute("role", "separator");
    h.setAttribute("aria-orientation", "vertical");
    h.setAttribute("aria-label", spec.label);
    h.setAttribute("aria-valuemin", String(spec.min));
    h.setAttribute("aria-valuemax", String(spec.max()));
    h.title = "Drag to resize, double-click to reset";
    handles[name] = h;
    app.appendChild(h);
    apply(name, typeof saved[name] === "number" ? saved[name] : spec.def);
    if (typeof saved[name] !== "number") root.style.removeProperty(spec.cssVar);
    let drag = null;
    let raf = 0;
    let pending = 0;
    h.addEventListener("pointerdown", function (e) {
      if (window.innerWidth < MIN_W || e.button > 0) return;
      drag = { x: e.clientX, w: cur[name] };
      h.setPointerCapture(e.pointerId);
      h.classList.add("rz-drag");
      e.preventDefault();
    });
    h.addEventListener("pointermove", function (e) {
      if (!drag) return;
      pending = drag.w + spec.sign * (e.clientX - drag.x);
      if (!raf) raf = requestAnimationFrame(function () { raf = 0; apply(name, pending); });
    });
    function end(e) {
      if (!drag) return;
      drag = null;
      if (raf) { cancelAnimationFrame(raf); raf = 0; apply(name, pending); }
      h.classList.remove("rz-drag");
      try { h.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }
      save(name, cur[name]);
    }
    h.addEventListener("pointerup", end);
    h.addEventListener("pointercancel", end);
    h.addEventListener("dblclick", function () {
      root.style.removeProperty(spec.cssVar);
      cur[name] = spec.def;
      h.setAttribute("aria-valuenow", String(spec.def));
      save(name, null);
    });
    h.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const dir = e.key === "ArrowRight" ? 1 : -1;
      apply(name, cur[name] + spec.sign * dir * STEP);
      save(name, cur[name]);
      e.preventDefault();
    });
  });
  window.addEventListener("resize", function () {
    Object.keys(SPECS).forEach(function (n) {
      if (cur[n] !== SPECS[n].def || root.style.getPropertyValue(SPECS[n].cssVar)) apply(n, cur[n]);
    });
  });
}
