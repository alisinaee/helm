// Run the command palette's pure functions in node (used by tests/web/test_palette.py). No DOM: isPaletteKey and
// searchPalette are plain functions. argv: this script, web directory. Prints one JSON object.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const palette = await import(pathToFileURL(web + "/js/views/palette.js").href);

const key = (k, extra) => Object.assign({ key: k, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false }, extra);
const keys = {
  cmdK: palette.isPaletteKey(key("k", { metaKey: true })),
  ctrlK: palette.isPaletteKey(key("k", { ctrlKey: true })),
  upperCtrlK: palette.isPaletteKey(key("K", { ctrlKey: true })),
  plainK: palette.isPaletteKey(key("k")),
  cmdJ: palette.isPaletteKey(key("j", { metaKey: true })),
  altCmdK: palette.isPaletteKey(key("k", { metaKey: true, altKey: true })),
  shiftCmdK: palette.isPaletteKey(key("k", { metaKey: true, shiftKey: true })),
  nullEvent: palette.isPaletteKey(null),
};

const snap = {
  id: "alpha",
  tasks: [
    { id: "P1.1", title: "Set up the project" },
    { id: "P1.2", title: "Write the parser" },
    { id: "P10.1", title: "Release notes" },
    { id: "P2.4", title: "Planner drawer" },
  ],
  issues: [{ id: "I1", title: "Slow snapshot on P1 projects" }],
  questions: [{ id: "Q3", text: "Use the staging host?" }],
};

const ids = (text, s, pid) => palette.searchPalette(text, s === undefined ? snap : s, pid === undefined ? "alpha" : pid)
  .map((r) => r.id);

const search = {
  p1: ids("P1"),
  p24: ids("p2.4"),
  issue: ids("I1"),
  question: ids("Q3"),
  titleWord: ids("parser"),
  none: ids("zzzz"),
  emptyAll: ids(""),
  stopFirst: ids(">st"),
  goWork: ids(">go wo"),
  start: ids(">start P1.2"),
  startUnknown: ids(">start P9.9"),
  doneUnknown: ids(">done P9.9"),
  noProject: palette.searchPalette(">st", null, null).map((r) => r.id),
  noProjectTasks: palette.searchPalette("P1", null, null).map((r) => r.id),
  limit: ids("").length,
};

const commands = palette.commandsFor(snap, "alpha").map((c) => c.id);
const commandsAllProjects = palette.commandsFor(null, null).map((c) => c.id);

console.log(JSON.stringify({ keys, search, commands, commandsAllProjects }));
