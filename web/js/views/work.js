// Work section (WP28 placeholder): the existing project content until the Work package replaces it. Board, List and
// Tree arrive with that package, so this file only mounts the current project view.

import { emptyHtml } from "../dom.js";
import { projectView } from "./home.js";

export function sectionView(vm) {
  if (vm.route.name !== "project" || !vm.project) {
    return emptyHtml("Work belongs to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  return projectView(vm);
}
