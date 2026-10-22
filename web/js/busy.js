// Loading state for a button that waits on the server (docs/MOTION-PLAN.md). The state is the attribute
// aria-busy="true"
// plus disabled while the request runs; motion.css draws the spinner from the attribute, so this file never draws
// anything. No DOM is touched at import time. Both functions accept a null element and an element that is no longer
// in the page: then they do nothing visible, and nothing throws.

// The disabled state a button had before it went busy, so the restore puts it back exactly as it was.
const before = new WeakMap();

// on true: marks el busy and disabled. on false: removes the busy mark and restores the disabled state it had.
export function setBusy(el, on) {
  if (!el || typeof el.setAttribute !== "function") return;
  if (on) {
    if (!before.has(el)) before.set(el, "disabled" in el ? !!el.disabled : false);
    el.setAttribute("aria-busy", "true");
    if ("disabled" in el) el.disabled = true;
    return;
  }
  el.removeAttribute("aria-busy");
  if (before.has(el)) {
    if ("disabled" in el) el.disabled = before.get(el);
    before.delete(el);
  }
}

// Marks el busy while promise runs. Always clears the mark in finally. Resolves to the promise's value and rethrows
// its error, so the caller's own catch still sees the failure.
export async function withBusy(el, promise) {
  setBusy(el, true);
  try {
    return await promise;
  } finally {
    setBusy(el, false);
  }
}
