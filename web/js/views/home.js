// Home (#/): one card per project, then Running now across projects. The project view (#/p/<id>) is composed here
// from the section modules: Phases in the main column; Running now, Needs you, Next up, Recent, Extras and Legend in
// the side column. On narrow screens the side column follows the main column.

import { bannerHtml, chipHtml, emptyHtml, esc, meterHtml, sectionHtml, skeletonHtml } from "../dom.js";
import { fmtCount, fmtDuration, fmtPercent, MISSING } from "../format.js";
import { projectHash } from "../router.js";
import { extrasSection } from "./extras.js";
import { legendSection } from "./legend.js";
import { needsSection } from "./needsyou.js";
import { nextSection } from "./next.js";
import { phasesSection } from "./phases.js";
import { recentSection } from "./recent.js";
import { runningSection } from "./running.js";

const MODEL_KINDS = ["haiku", "sonnet", "opus", "cursor", "agy"];

function runRow(job, showProject) {
  const model = MODEL_KINDS.indexOf(job.model) >= 0 ? job.model : "neutral";
  const project = showProject && job.projectId
    ? ' <a href="' + esc(projectHash(job.projectId)) + '">' + esc(job.projectName) + "</a>"
    : "";
  return '<div class="run-row"><span class="run-task">' + esc(job.task || job.id) + "</span>" +
    chipHtml(job.model || "model?", model) +
    '<span class="run-title" title="' + esc(job.title) + '">' + esc(job.title || "") + project + "</span>" +
    '<span class="run-time">' + esc(fmtDuration(job.elapsedNow)) + "</span></div>";
}

function runList(jobs, showProject) {
  if (!jobs.length) return '<p class="placeholder">Nothing is running.</p>';
  return '<div class="run-list">' + jobs.map(function (job) {
    return runRow(job, showProject);
  }).join("") + "</div>";
}

function projectCard(p) {
  const badges = [];
  if (p.stale) badges.push('<span class="badge badge-warning">Stale</span>');
  if (p.errorsCount > 0) {
    badges.push('<span class="badge badge-danger">' + esc(fmtCount(p.errorsCount)) + " file error" +
      (p.errorsCount === 1 ? "" : "s") + "</span>");
  }
  const pct = p.progress == null ? null : p.progress * 100;
  return '<article class="card"><div class="card-head"><h3 class="card-name"><a href="' +
    esc(projectHash(p.id)) + '">' + esc(p.name) + "</a></h3>" + badges.join("") + "</div>" +
    '<div class="card-progress">' + meterHtml(pct, "accent") + "<span>" + esc(fmtPercent(pct)) + "</span></div>" +
    '<p class="card-counts">' + esc(fmtCount(p.tasksLeft)) + " tasks left · " + esc(fmtCount(p.running)) +
    " running · " + esc(fmtCount(p.needUser)) + " need you</p></article>";
}

export function homeView(vm) {
  if (vm.projectsError && !vm.projects) {
    return bannerHtml("danger", "Could not load projects. Retrying.", vm.projectsError.message);
  }
  if (!vm.projects || vm.home.loading) {
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90", "w-40"]) + "</div>";
  }
  if (!vm.projects.length) {
    return emptyHtml("No projects yet.", "Run <code class=\"code\">roadmap project add &lt;path&gt;</code>.");
  }
  const running = vm.projects.reduce(function (sum, p) {
    return sum + (p.running || 0);
  }, 0);
  const needYou = vm.projects.reduce(function (sum, p) {
    return sum + (p.needUser || 0);
  }, 0);
  const cards = '<div class="cards">' + vm.projects.map(projectCard).join("") + "</div>";
  const projectsSection = sectionHtml({
    id: "projects",
    title: "Projects",
    summary: vm.projects.length + " registered · " + running + " running · " + needYou + " need you",
    open: vm.open.projects,
    body: cards,
  });
  const runningSection = sectionHtml({
    id: "running",
    title: "Running now",
    summary: vm.home.running.length + " running",
    open: vm.open.running,
    body: runList(vm.home.running, true),
  });
  return projectsSection + runningSection;
}

export function projectView(vm) {
  const project = vm.project;
  if (project.notFound) {
    return emptyHtml("No project with that id.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const snap = project.snapshot;
  if (!snap) {
    if (project.error) {
      return bannerHtml("danger", "Could not load this project. Retrying.", project.error.message);
    }
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  }
  const errors = snap.errors.map(function (e) {
    return bannerHtml("warning", "Could not read " + e.file,
      e.message + ". Fix the file named above, then save it.");
  }).join("");
  const updated = snap.tasksUpdated ? '<p class="project-line">Tasks updated ' + esc(snap.tasksUpdated) + "</p>" : "";
  const side = [runningSection(vm), needsSection(vm), nextSection(vm), recentSection(vm), extrasSection(vm),
    legendSection(vm)].join("");
  return (errors ? '<div class="banner-stack">' + errors + "</div>" : "") + updated +
    '<div class="proj"><div class="proj-main">' + phasesSection(vm) + '</div>' +
    '<div class="proj-side">' + side + "</div></div>";
}
