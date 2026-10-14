// Workflow graph model (WP71, WP70-A). buildGraph(snap, filters) turns one project snapshot (the shape in
// docs/WORKFLOW-SPEC.md section 2) into the nodes and edges the workflow diagram draws. Pure: no DOM and no clock, so
// the same input always gives the same output.
//
// Node ids carry their kind: phase:<id>, task:<id>, job:<id> (one pill per job), job+:<task> (the "+n" pill that stands
// for the older jobs of a task), issue:<id>, queue, and collapse:<phase> (the done tasks of a completed phase).
// Edges: dependency (task to task, from the `after` pairs, prerequisite first), handoff (job to job, parent to child)
// and blocker (issue to task). Phases and the queue add no edges.
//
// filters: {status, agent, phase}, each an array or a comma list (empty or missing means no filter), and expand: true
// to skip the collapse. Above NODE_CAP nodes, the done tasks of each completed phase collapse into one node.
//
// Also returned (kept out of `nodes` and `edges`, so layout and render are unchanged): start and end (the Start and
// End pseudo-nodes, ids "start" and "end"); sequence (edges task to next task in a phase, and last task of a phase to
// the first task of the next, from Start and to End; kept apart from the `after` dependency edges); current (the Now
// point: "task:<id>", "start" or "end"); parallel (groups of two or more active tasks in one phase: doing or partial,
// or with a running job). A phase node has `collapsed`: true when every live (not deferred) task of the phase is done.

export const NODE_CAP = 300;
export const PILL_MAX = 3;
const PILL_KEEP = 2;

function isObj(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function list(value) {
  return Array.isArray(value) ? value.filter(isObj) : [];
}

function pairs(value) {
  return Array.isArray(value) ? value.filter((p) => Array.isArray(p) && p.length >= 2) : [];
}

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function idOf(value) {
  const s = text(value);
  return s === "" ? null : s;
}

function num(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function secMs(value) {
  const n = num(value);
  return n === null ? null : n * 1000;
}

function uniqueBy(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}

export function filterSet(value) {
  const items = typeof value === "string" ? value.split(",") : value;
  if (!Array.isArray(items)) return null;
  const set = new Set(items.map((s) => text(s).trim()).filter((s) => s !== ""));
  return set.size ? set : null;
}

export function taskStatus(task) {
  const s = text(task.state);
  if (s === "done") return "done";
  if (s === "doing" || s === "partial" || s === "active" || s === "running") return "doing";
  if (s === "block" || s === "blocked" || s === "hold") return "blocked";
  if (s === "deferred" || s === "defer") return "defer";
  return "todo";
}

function jobStatus(status) {
  if (status === "running") return "doing";
  if (status === "done") return "done";
  if (status === "failed") return "blocked";
  return "todo";
}

function laneKey(task) {
  return task.phase === null ? "_" : task.phase;
}

// The first moment of a task: its doing stamp or the start of one of its jobs, whichever is earliest.
function timeOf(task, jobs) {
  const times = [];
  const doing = task.at && typeof task.at.doing === "string" ? Date.parse(task.at.doing) : NaN;
  if (Number.isFinite(doing)) times.push(doing);
  jobs.forEach((j) => {
    if (j.start !== null) times.push(j.start);
  });
  return times.length ? Math.min(...times) : null;
}

// The current point (Now): the first doing task in chain order; else Start when nothing is done yet; else the first
// task that is neither done nor deferred; else End.
function currentOf(order) {
  const doing = order.find((t) => t.status === "doing");
  if (doing) return "task:" + doing.id;
  if (!order.some((t) => t.status === "done")) return "start";
  const next = order.find((t) => t.status !== "done" && t.status !== "defer");
  return next ? "task:" + next.id : "end";
}

function pushRow(map, key, row) {
  const rows = map.get(key) || [];
  rows.push(row);
  map.set(key, rows);
}

function addEdge(edges, seen, type, from, to) {
  const id = type + ":" + from + ">" + to;
  if (seen.has(id)) return;
  seen.add(id);
  edges.push({ id, type, from, to });
}

// Replace the done tasks of each complete phase by one node per phase. Edges are re-pointed; self loops, and edges
// that touched a dropped job pill, go.
function collapseDone(nodes, edges, complete) {
  const victims = new Map();
  nodes.forEach((n) => {
    if (n.type === "task" && n.status === "done" && complete.has(n.lane)) victims.set(n.task, n.lane);
  });
  if (!victims.size) return null;
  const groups = new Map();
  const redirect = new Map();
  nodes.forEach((n) => {
    if (!n.task || !victims.has(n.task)) return;
    if (n.type === "task") {
      const g = groups.get(n.lane) || { count: 0, tokensK: 0 };
      g.count += 1;
      g.tokensK += n.tokensK || 0;
      groups.set(n.lane, g);
      redirect.set(n.id, "collapse:" + n.lane);
    } else if (n.type === "job") {
      redirect.set(n.id, null);
    }
  });
  const merged = Array.from(groups, ([lane, g]) => ({
    id: "collapse:" + lane, type: "task", task: null, lane, label: "Phase " + lane + ": " + g.count + " done",
    title: "", status: "done", model: "", tokensK: g.tokensK, time: null, after: 0, jobs: 0, collapsed: g.count,
  }));
  const seen = new Set();
  const out = [];
  edges.forEach((e) => {
    const from = redirect.has(e.from) ? redirect.get(e.from) : e.from;
    const to = redirect.has(e.to) ? redirect.get(e.to) : e.to;
    if (from === null || to === null || from === to) return;
    const id = e.type + ":" + from + ">" + to;
    if (seen.has(id)) return;
    seen.add(id);
    out.push({ id, type: e.type, from, to });
  });
  return {
    nodes: nodes.filter((n) => !redirect.has(n.id)).concat(merged),
    edges: out,
    lanes: Array.from(groups.keys()),
  };
}

export function buildGraph(snap, filters) {
  const raw = isObj(snap) ? snap : {};
  const opt = isObj(filters) ? filters : {};
  const fStatus = filterSet(opt.status);
  const fAgent = filterSet(opt.agent);
  const fPhase = filterSet(opt.phase);
  const wf = isObj(raw.workflow) ? raw.workflow : {};
  const wfEdges = isObj(wf.edges) ? wf.edges : {};

  const phases = uniqueBy(list(raw.phases).map((p) => ({
    id: idOf(p.id), title: text(p.name || p.title), approved: p.approved === true,
  })).filter((p) => p.id !== null));
  const tasks = uniqueBy(list(raw.tasks).map((t) => ({
    id: idOf(t.id), title: text(t.title), phase: idOf(t.phase), status: taskStatus(t), model: text(t.model),
    tokensK: num(t.tokensK), at: isObj(t.at) ? t.at : {},
  })).filter((t) => t.id !== null));
  const taskById = new Map(tasks.map((t) => [t.id, t]));
  const titles = new Map(list(raw.jobs).map((j) => [text(j.id), text(j.title)]));
  const spans = uniqueBy(pairs(wf.spans).map((r) => ({
    id: idOf(r[0]), task: idOf(r[1]), model: text(r[2]), role: text(r[3]), parent: idOf(r[4]),
    start: secMs(r[5]), end: secMs(r[6]), status: text(r[7]), tokensK: num(r[8]),
  })).filter((j) => j.id !== null));

  // Lanes: the phases in their order, then any phase a task names that the phase list lacks, then no phase.
  const laneOrder = [];
  const laneInfo = new Map();
  const addLane = (id, label, approved) => {
    if (laneInfo.has(id)) return;
    laneInfo.set(id, { label, approved });
    laneOrder.push(id);
  };
  phases.forEach((p) => addLane(p.id, p.title || p.id, p.approved));
  tasks.forEach((t) => addLane(laneKey(t), t.phase === null ? "No phase" : t.phase, false));
  const totals = new Map();
  tasks.forEach((t) => {
    const cur = totals.get(laneKey(t)) || { done: 0, total: 0, tokensK: 0 };
    cur.total += 1;
    if (t.status === "done") cur.done += 1;
    cur.tokensK += t.tokensK || 0;
    totals.set(laneKey(t), cur);
  });

  const liveDone = new Map();
  tasks.forEach((t) => {
    if (t.status === "defer") return;
    const c = liveDone.get(laneKey(t)) || { open: 0, done: 0 };
    if (t.status === "done") c.done += 1;
    else c.open += 1;
    liveDone.set(laneKey(t), c);
  });
  const laneRows = new Map();
  tasks.forEach((t) => pushRow(laneRows, laneKey(t), t));
  const order = [];
  laneOrder.forEach((id) => (laneRows.get(id) || []).forEach((t) => order.push(t)));

  const jobsByTask = new Map();
  spans.forEach((j) => {
    if (!j.task || !taskById.has(j.task)) return;
    const rows = jobsByTask.get(j.task) || [];
    rows.push(j);
    jobsByTask.set(j.task, rows);
  });
  jobsByTask.forEach((rows) => rows.sort((a, b) => (a.start || 0) - (b.start || 0) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)));
  const unattachedJobs = spans.filter((j) => !j.task || !taskById.has(j.task)).length;
  const jobPasses = (j) => !fAgent || fAgent.has(j.model);

  const keptTasks = tasks.filter((t) => {
    if (fStatus && !fStatus.has(t.status)) return false;
    if (fPhase && !fPhase.has(laneKey(t))) return false;
    if (fAgent && !fAgent.has(t.model) && !(jobsByTask.get(t.id) || []).some(jobPasses)) return false;
    return true;
  });
  const keptIds = new Set(keptTasks.map((t) => t.id));
  const lanesOut = laneOrder.filter((id) => (!fPhase || fPhase.has(id)) &&
    (id !== "_" || keptTasks.some((t) => t.phase === null)));

  const nodes = [];
  const edges = [];
  const seen = new Set();
  const jobNodeOf = new Map();
  lanesOut.forEach((id) => {
    const info = laneInfo.get(id);
    const tot = totals.get(id) || { done: 0, total: 0, tokensK: 0 };
    const live = liveDone.get(id);
    nodes.push({ id: "phase:" + id, type: "phase", lane: id, label: info.label, approved: info.approved,
      done: tot.done, total: tot.total, tokensK: tot.tokensK, collapsed: !!live && live.open === 0 && live.done > 0 });
  });

  const afterCount = new Map();
  pairs(wfEdges.after).forEach((p) => {
    const to = text(p[1]);
    afterCount.set(to, (afterCount.get(to) || 0) + 1);
  });
  keptTasks.forEach((t) => {
    const all = jobsByTask.get(t.id) || [];
    const jobs = all.filter(jobPasses);
    const hidden = jobs.length > PILL_MAX ? jobs.length - PILL_KEEP : 0;
    nodes.push({ id: "task:" + t.id, type: "task", task: t.id, lane: laneKey(t), label: t.title || t.id,
      title: t.title, status: t.status, model: t.model, tokensK: t.tokensK, time: timeOf(t, all),
      after: afterCount.get(t.id) || 0, jobs: jobs.length, collapsed: 0 });
    if (hidden > 0) {
      const nid = "job+:" + t.id;
      jobs.slice(0, hidden).forEach((j) => jobNodeOf.set(j.id, nid));
      nodes.push({ id: nid, type: "job", task: t.id, parent: "task:" + t.id, lane: laneKey(t),
        label: "+" + hidden, more: hidden, status: "todo" });
    }
    jobs.slice(hidden).forEach((j) => {
      const nid = "job:" + j.id;
      jobNodeOf.set(j.id, nid);
      nodes.push({ id: nid, type: "job", task: t.id, parent: "task:" + t.id, lane: laneKey(t), label: j.model || j.id,
        job: j.id, title: titles.get(j.id) || "", model: j.model, role: j.role, status: jobStatus(j.status),
        running: j.status === "running", start: j.start, end: j.end, tokensK: j.tokensK });
    });
  });

  pairs(wfEdges.after).forEach((p) => {
    const from = text(p[0]);
    const to = text(p[1]);
    if (from === to || !keptIds.has(from) || !keptIds.has(to)) return;
    addEdge(edges, seen, "dependency", "task:" + from, "task:" + to);
  });
  spans.forEach((j) => {
    if (!j.parent) return;
    const from = jobNodeOf.get(j.parent);
    const to = jobNodeOf.get(j.id);
    if (!from || !to || from === to) return;
    addEdge(edges, seen, "handoff", from, to);
  });

  const issueTitle = new Map(list(raw.issues).map((i) => [text(i.id), text(i.title)]));
  const issueSeen = new Set();
  pairs(wfEdges.block).forEach((p) => {
    const iid = text(p[0]);
    const tid = text(p[1]);
    if (!keptIds.has(tid)) return;
    if (!issueSeen.has(iid)) {
      issueSeen.add(iid);
      nodes.push({ id: "issue:" + iid, type: "issue", issue: iid, task: tid, lane: laneKey(taskById.get(tid)),
        label: issueTitle.get(iid) || iid, status: "blocked" });
    }
    addEdge(edges, seen, "blocker", "issue:" + iid, "task:" + tid);
  });

  const queued = list(raw.queue).map((q) => idOf(q.task)).filter((tid) => tid !== null && keptIds.has(tid));
  if (queued.length) {
    nodes.push({ id: "queue", type: "queue", lane: laneKey(taskById.get(queued[0])),
      label: "Queue (" + queued.length + ")", count: queued.length, status: "todo" });
  }

  // Sequence: Start to the first kept task, each kept task to the next in its phase, the last task of a phase to the
  // first of the next phase, and the last task to End. Built with the other edges so the cap collapse re-points them.
  const keptByLane = new Map();
  keptTasks.forEach((t) => pushRow(keptByLane, laneKey(t), t));
  const seqEdges = [];
  const seqSeen = new Set();
  let prev = "start";
  let linked = false;
  lanesOut.forEach((id) => (keptByLane.get(id) || []).forEach((t) => {
    addEdge(seqEdges, seqSeen, "sequence", prev, "task:" + t.id);
    prev = "task:" + t.id;
    linked = true;
  }));
  if (linked) addEdge(seqEdges, seqSeen, "sequence", prev, "end");

  // Parallel: in each phase, the active tasks (doing or partial, or owning a running job) when two or more are active.
  const isActive = (t) => t.status !== "done" &&
    (t.status === "doing" || (jobsByTask.get(t.id) || []).some((j) => j.status === "running"));
  const parallel = [];
  lanesOut.forEach((lane) => {
    const members = (keptByLane.get(lane) || []).filter(isActive);
    if (members.length > 1) {
      parallel.push({ id: "par:" + members[0].id, lane, members: members.map((t) => "task:" + t.id) });
    }
  });

  const firstTimes = tasks.map((t) => timeOf(t, jobsByTask.get(t.id) || [])).filter((x) => x !== null);
  const projectTitle = isObj(raw.project) ? text(raw.project.title) : "";
  const left = tasks.filter((t) => t.status !== "done" && t.status !== "defer").length;

  const stats = { before: nodes.length, after: nodes.length, collapsed: [], capped: false,
    tasks: keptTasks.length, unattachedJobs };
  let finalNodes = nodes;
  let finalEdges = edges.concat(seqEdges);
  if (!opt.expand && nodes.length > NODE_CAP) {
    const complete = new Set(lanesOut.filter((id) => {
      const t = totals.get(id);
      return t && t.total > 0 && t.done === t.total;
    }));
    const res = collapseDone(nodes, finalEdges, complete);
    if (res) {
      finalNodes = res.nodes;
      finalEdges = res.edges;
      stats.collapsed = res.lanes;
    }
  }
  stats.after = finalNodes.length;
  stats.capped = finalNodes.length > NODE_CAP;
  return {
    nodes: finalNodes,
    edges: finalEdges.filter((e) => e.type !== "sequence"),
    sequence: finalEdges.filter((e) => e.type === "sequence"),
    lanes: lanesOut.map((id) => ({ id, label: laneInfo.get(id).label, approved: laneInfo.get(id).approved })),
    stats,
    start: { id: "start", type: "start", label: projectTitle || "Start",
      date: firstTimes.length ? Math.min(...firstTimes) : null },
    end: { id: "end", type: "end", label: left + " left", left },
    current: currentOf(order),
    parallel,
  };
}
