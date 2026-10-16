"""Command group system: the architecture map from docs/system.json (A8, SYSTEM-DESIGN-SECTION.md).

show prints the components, layers, edges, file counts and recent commit heat; check validates docs/system.json
(exit 0 when it is valid, 1 with the messages when it is not). Both read only; the map logic lives in
roadmap/services/system.py and the heat in roadmap/services/systemheat.py.
"""

import os

from roadmap.errors import EXIT_ERROR, RoadmapError
from roadmap.services import system, systemheat


def register(sub, common):
    """Add the system group and its actions."""
    group = sub.add_parser("system", parents=[common], help="architecture map (docs/system.json)")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, handler, text in (("show", handle_show, "show the components, layers and edges"),
                                ("check", handle_check, "validate docs/system.json (exit 1 when invalid)")):
        part = actions.add_parser(name, parents=[common], help=text)
        part.add_argument("--path", metavar="DIR", default=None,
                          help="project folder (default: the current folder)")
        part.set_defaults(handler=handler)


def _root(args):
    return os.path.realpath(getattr(args, "path", None) or os.getcwd())


def _json_mode(args):
    return getattr(args, "json", False)


def _heat(root, components, sha):
    """commits30 and lastAt per component from git history; empty when history cannot be read."""
    try:
        heat = systemheat.build(root, components, sha=sha)["heat"]
    except RoadmapError:
        return {}
    return {cid: {"commits30": row["commits30"], "lastAt": row["lastAt"]} for cid, row in heat.items()}


def _show_data(root):
    view = system.load(root)
    heat = _heat(root, view["components"], view["sha"])
    comps = []
    for comp in view["components"]:
        row = dict(comp)
        row["heat"] = heat.get(comp["id"], {"commits30": 0, "lastAt": None})
        comps.append(row)
    return {"source": view["source"], "warnings": view["warnings"], "layers": view["layers"],
            "components": comps, "edges": view["edges"], "fileCount": view["fileCount"], "sha": view["sha"]}


def handle_show(args):
    """The map: one line per component (layer, kind, files, commits in 30 days), then the edges."""
    data = _show_data(_root(args))
    if not _json_mode(args):
        print("system map: source %s, %d components, %d edges, %d files"
              % (data["source"], len(data["components"]), len(data["edges"]), data["fileCount"]))
        for text in data["warnings"]:
            print("warning: " + text)
        print("layers: " + " > ".join(data["layers"]) if data["layers"] else "layers: none")
        width = max([len(c["id"]) for c in data["components"]] + [2])
        print("%s  %-8s %-7s %6s %9s" % ("id".ljust(width), "layer", "kind", "files", "commits30"))
        for comp in data["components"]:
            print("%s  %-8s %-7s %6d %9d" % (comp["id"].ljust(width), comp["layer"], comp["kind"],
                                             comp["fileCount"], comp["heat"]["commits30"]))
        for edge in data["edges"]:
            print("%s -> %s%s" % (edge["from"], edge["to"], " (" + edge["label"] + ")" if edge["label"] else ""))
    return data


def handle_check(args):
    """Validate docs/system.json. Valid: source file with no warnings. Anything else is invalid, with each message."""
    root = _root(args)
    view = system.load(root, use_cache=False)
    problems = []
    if view["source"] == "baseline" and not any("system.json" in w for w in view["warnings"]):
        problems.append("docs/system.json is missing (the map is only the automatic baseline)")
    problems.extend(view["warnings"])
    if view["source"] == "merged" and not problems:
        problems.append("some files fall only into auto 'other' components; add them to docs/system.json")
    if problems:
        raise RoadmapError("invalid_system", "\n".join(problems), EXIT_ERROR,
                           next="edit docs/system.json, then run roadmap system check")
    data = {"valid": True, "source": view["source"], "components": len(view["components"]),
            "edges": len(view["edges"]), "fileCount": view["fileCount"]}
    if not _json_mode(args):
        print("system map ok: %d components, %d edges, %d files"
              % (data["components"], data["edges"], data["fileCount"]))
    return data
