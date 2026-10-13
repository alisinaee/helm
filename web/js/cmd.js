// The one write path (WP28). run() applies a change at once, posts it to /api/v1/cmd with the page's CSRF token, and
// on failure reverts it and shows the server's message. A reply with undo:true gets an Undo toast; Undo posts the
// undo op for that activity id, then the snapshot is read again. A pending value shows until the next snapshot that
// was read after the reply, so a poll does not flip a control back before the server has it.

import { postJson } from "./api.js";
import { showToast } from "./views/toast.js";

const PENDING_MS = 10000;
const pending = new Map();
let writable = function () {
  return true;
};
let refreshNow = function () {};
let rerender = function () {};
let projectOf = function () {
  return null;
};

export function configureCommands(opts) {
  writable = opts.writable;
  refreshNow = opts.refresh;
  rerender = opts.render;
  projectOf = opts.project;
}

// The value to show for a key while a change is pending, or undefined when the snapshot should decide.
export function pendingValue(key, fetchedAt, now) {
  const entry = pending.get(key);
  if (!entry) return undefined;
  const settled = entry.doneAt !== null && fetchedAt > entry.doneAt;
  if (settled || now > entry.expires) {
    pending.delete(key);
    return undefined;
  }
  return entry.value;
}

async function postOp(op, args, project) {
  const body = { op: op, args: args || {} };
  if (project) body.project = project;
  return postJson("/api/v1/cmd", body);
}

async function undoActivity(activity, project, opts, key) {
  if (key) pending.delete(key);
  if (typeof opts.revert === "function") opts.revert();
  rerender();
  try {
    await postOp("undo", { activity: activity }, project);
    showToast({ text: "Undone: " + (opts.label || "change"), tone: "success" });
  } catch (err) {
    showToast({ text: "Undo failed: " + (err.message || "unknown error"), tone: "danger" });
  }
  refreshNow();
}

// opts: label (toast text), project (id; default the current project), apply and revert (local state),
// key and value (a pending value for the snapshot-backed control, see pendingValue).
export async function run(op, args, opts) {
  const o = opts || {};
  const label = o.label || op;
  if (!writable()) {
    showToast({ text: "Offline. Changes are paused until the connection returns.", tone: "danger" });
    return null;
  }
  const project = o.project || projectOf();
  const key = o.key || null;
  if (key) pending.set(key, { value: o.value, doneAt: null, expires: Date.now() + PENDING_MS });
  if (typeof o.apply === "function") o.apply();
  rerender();
  let reply;
  try {
    reply = await postOp(op, args, project);
  } catch (err) {
    if (key) pending.delete(key);
    if (typeof o.revert === "function") o.revert();
    rerender();
    showToast({ text: label + " failed: " + (err.message || "unknown error"), tone: "danger" });
    return null;
  }
  const data = reply.data || {};
  if (key && pending.has(key)) pending.get(key).doneAt = Date.now();
  const undoable = data.undo === true && typeof data.activity === "string";
  showToast({
    text: label,
    tone: "success",
    undo: undoable ? function () {
      return undoActivity(data.activity, project, o, key);
    } : null,
  });
  refreshNow();
  return data;
}

async function undoBatch(activities, project, o, keys) {
  for (const key of keys) pending.delete(key);
  rerender();
  let failed = 0;
  for (const activity of activities) {
    try {
      await postOp("undo", { activity: activity }, project);
    } catch (err) {
      failed += 1;
    }
  }
  showToast(failed
    ? { text: "Undo failed for " + failed + " change(s)", tone: "danger" }
    : { text: "Undone: " + (o.done || "changes"), tone: "success" });
  refreshNow();
}

// Several ops as one change (WP31, the Work list's bulk bar). items: [{op, args, key, value}]. The ops post in turn and
// a failure is counted without stopping the rest. One toast reports the count, with one Undo that reverts every
// undoable op, newest first. opts: done (the noun shown after the count, e.g. "tasks updated"), project.
export async function runBatch(items, opts) {
  const o = opts || {};
  if (!writable()) {
    showToast({ text: "Offline. Changes are paused until the connection returns.", tone: "danger" });
    return null;
  }
  const project = o.project || projectOf();
  const keys = [];
  for (const item of items) {
    if (!item.key) continue;
    keys.push(item.key);
    pending.set(item.key, { value: item.value, doneAt: null, expires: Date.now() + PENDING_MS });
  }
  rerender();
  const activities = [];
  let failed = 0;
  for (const item of items) {
    try {
      const reply = await postOp(item.op, item.args, project);
      const data = reply.data || {};
      if (data.undo === true && typeof data.activity === "string") activities.push(data.activity);
    } catch (err) {
      failed += 1;
    }
  }
  for (const key of keys) {
    if (pending.has(key)) pending.get(key).doneAt = Date.now();
  }
  const count = items.length - failed;
  const text = count + " " + (o.done || "changes") + (failed ? "; " + failed + " failed" : "");
  showToast({
    text: text,
    tone: failed ? "danger" : "success",
    undo: activities.length ? function () {
      return undoBatch(activities.slice().reverse(), project, o, keys);
    } : null,
  });
  refreshNow();
  return { changed: count, failed: failed };
}
