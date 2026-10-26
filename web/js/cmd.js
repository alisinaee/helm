// The one write path (WP28). run() applies a change at once, posts it to /api/v1/cmd with the page's CSRF token, and
// on failure reverts it and shows the server's message. A reply with undo:true gets an Undo toast; Undo posts the
// undo op for that activity id, then the snapshot is read again. A pending value shows until the project's snapshot
// rev changes after the reply (the new generation has the write). A poll that finds the same rev does not settle it.

import { postJson } from "./api.js";
import { withBusy } from "./busy.js";
import { logAction } from "./log.js";
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
let revOf = function () {
  return null;
};

export function configureCommands(opts) {
  writable = opts.writable;
  refreshNow = opts.refresh;
  rerender = opts.render;
  projectOf = opts.project;
  revOf = opts.rev || revOf;
}

// Whether a pending entry has settled: the reply is in and the project's snapshot rev differs from the rev it had
// when the change was sent. With no rev (a snapshot without one) the body time decides, as before.
function settled(entry, fetchedAt) {
  if (entry.repliedAt === null) return false;
  const rev = revOf(entry.project);
  if (rev === null || rev === undefined) return fetchedAt > entry.repliedAt;
  return rev !== entry.baseRev;
}

// The value to show for a key while a change is pending, or undefined when the snapshot should decide.
// fetchedAt is the control's snapshot body time, used only when the snapshot has no rev.
export function pendingValue(key, fetchedAt, now) {
  const entry = pending.get(key);
  if (!entry) return undefined;
  if (settled(entry, fetchedAt) || now > entry.expires) {
    pending.delete(key);
    return undefined;
  }
  return entry.value;
}

function holdValue(key, value, project) {
  pending.set(key, { value: value, project: project, baseRev: revOf(project), repliedAt: null,
    expires: Date.now() + PENDING_MS });
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

// R9.42: a brief drop is quiet. The connection counts as down (red Offline) only after DOWN_GRACE_MS without a good
// reading; before that it is "wait" (Reconnecting). downSince is the first failed poll; any ok clears it.
export const DOWN_GRACE_MS = 5000;
let downSince = 0;
export function connPhase(conn, now) {
  if (!conn || conn.ok !== false) { downSince = 0; return conn && conn.ok === true ? "ok" : "wait"; }
  const t = typeof now === "number" ? now : Date.now();
  if (!downSince) downSince = t;
  return t - downSince >= DOWN_GRACE_MS ? "down" : "reconnecting";
}
export function resetConnGrace() { downSince = 0; }

function notifyPaused() {
  const down = downSince && Date.now() - downSince >= DOWN_GRACE_MS;
  if (down) showToast({ text: "Offline. Changes are paused until the connection returns.", tone: "danger" });
  else showToast({ text: "Reconnecting. Try again in a moment." });
}

// opts: label (toast text), project (id; default the current project), apply and revert (local state),
// onError (called with the message instead of the failure toast), key and value (a pending value for the
// snapshot-backed control, see pendingValue), busyEl (a function that returns the button to show loading, called
// after the optimistic re-render, which replaces the pressed button).
export async function run(op, args, opts) {
  const o = opts || {};
  const label = o.label || op;
  if (!writable()) {
    notifyPaused();
    return null;
  }
  const project = o.project || projectOf();
  const key = o.key || null;
  logAction(op, null, { project: project });
  if (key) holdValue(key, o.value, project);
  if (typeof o.apply === "function") o.apply();
  rerender();
  let reply;
  try {
    const busyOn = typeof o.busyEl === "function" ? o.busyEl() : null;
    reply = await withBusy(busyOn, postOp(op, args, project));
  } catch (err) {
    if (key) pending.delete(key);
    if (typeof o.revert === "function") o.revert();
    rerender();
    if (typeof o.onError === "function") o.onError(err.message || "unknown error");
    else showToast({ text: label + " failed: " + (err.message || "unknown error"), tone: "danger" });
    return null;
  }
  const data = reply.data || {};
  if (key && pending.has(key)) pending.get(key).repliedAt = Date.now();
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
    notifyPaused();
    return null;
  }
  const project = o.project || projectOf();
  logAction("batch", null, { project: project, count: items.length });
  const keys = [];
  for (const item of items) {
    if (!item.key) continue;
    keys.push(item.key);
    holdValue(item.key, item.value, project);
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
    if (pending.has(key)) pending.get(key).repliedAt = Date.now();
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
