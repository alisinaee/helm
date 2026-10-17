"""R11.103 System v2: the class, deployment, use case and activity diagrams, derived from the code (stdlib only).
Each public function takes (root, files, mapped): root = absolute project folder, files = tracked relative POSIX
paths, mapped = the result of roadmap.services.system.load(root). Reads stay inside root (system._read_confined),
at most 256 KB per file. docs/system.json overrides (classes, deployment, usecases, activities) merge by id."""

import ast
import json
import os
import plistlib
import re

from roadmap.services import system, system_arch

MAX_CLASS_NODES = 80
MAX_CASES = 60
MAX_ITEMS = 24
MAX_STEPS = 40
MAX_RUN = 6
CAP_LIST = 8
MAX_SCAN = 600
MAX_IMPORT_EDGES = 400

_JS_EXT = (".js", ".mjs", ".ts", ".tsx", ".jsx")
_JS_CLASS = re.compile(r"^\s*export\s+(?:default\s+)?class\s+(\w+)(?:\s+extends\s+([\w.]+))?", re.M)
_JS_FUNC = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)", re.M)
_PORT = re.compile(r"(?<![A-Za-z])port\b[\w ]*[=:]\s*(\d{4,5})\b", re.I)
_SERVE_WORDS = re.compile(r"serve|server|http\.server|uvicorn|gunicorn|flask|runserver|npm (?:run )?start|npm run dev")
_ROUTE = re.compile(r"re\.compile\(\s*r?[\"'](\^?/api/[^\"']*)[\"']\s*\)\s*,\s*\(([^)]*)\)")
_ENTRY_HINT = ("main", "run", "handle", "serve", "build")


def _text(root, rel):
    try:
        data = system._read_confined(root, rel)
    except Exception:
        return ""
    return data.decode("utf-8", "replace") if data else ""


def _is_test(path):
    return "tests/" in path or "/test_" in "/" + path or path.startswith("test_")


def _comps(mapped):
    return list((mapped or {}).get("components") or [])


def _owner(files, mapped):
    comps = _comps(mapped)
    groups, _ = system.assign_files(list(files), comps)
    out = {}
    for cid, paths in groups.items():
        for path in paths:
            out[path] = cid
    return out, {c["id"]: c.get("name", c["id"]) for c in comps}


def _overrides(root, key):
    try:
        data = json.loads(_text(root, "docs/system.json") or "{}")
    except ValueError:
        return None
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, (dict, list)) else None


def _merge(base, extra, keyfn):
    """Add or replace by key: items of extra win over the same key in base."""
    out = {}
    for item in list(base) + [x for x in (extra or []) if isinstance(x, dict)]:
        out[keyfn(item)] = item
    return list(out.values())


def _id(item):
    return str(item.get("id"))


def _edge_key(item):
    return (item.get("from"), item.get("to"), item.get("kind"))


def _short(text, n=60):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _pyfiles(files):
    return [f for f in files if f.endswith(".py") and not _is_test(f)]


def _parse(text):
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None


# ---------------------------------------------------------------- classes

def _class_attrs(cls):
    seen = []

    def add(name):
        if name not in seen:
            seen.append(name)
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    add(tgt.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            add(stmt.target.id)
    for node in ast.walk(cls):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in tgts:
                if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                    add(tgt.attr)
    return seen[:CAP_LIST]


def _base_name(base):
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _import_edges(root, files, keep):
    """kind "imports" edges between kept JS module nodes (ids mod:<path>), resolved with the arch import rules."""
    known, edges, seen = set(files), [], set()
    for path in sorted(files):
        nid = "mod:" + path
        if nid not in keep or not path.endswith(_JS_EXT) or _is_test(path) or ".test." in path:
            continue
        targets, _ = system_arch._js_imports(_text(root, path), path, known)
        for target in targets:
            tid = "mod:" + target
            if target == path or tid not in keep or (nid, tid) in seen:
                continue
            seen.add((nid, tid))
            edges.append({"from": nid, "to": tid, "kind": "imports", "label": "imports"})
            if len(edges) >= MAX_IMPORT_EDGES:
                return edges
    return edges


def classes(root, files, mapped):
    owner, names = _owner(files, mapped)
    nodes, pending = [], []
    for path in _pyfiles(files):
        tree = _parse(_text(root, path))
        if tree is None:
            continue
        for stmt in tree.body:
            if isinstance(stmt, ast.ClassDef):
                methods = [n.name for n in stmt.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and not n.name.startswith("_")]
                nodes.append({"id": "cls:%s:%s" % (path, stmt.name), "label": stmt.name, "sub": path,
                              "kind": "class", "group": owner.get(path, "other"),
                              "attrs": _class_attrs(stmt), "methods": methods[:CAP_LIST]})
                pending.append(([b for b in map(_base_name, stmt.bases) if b], nodes[-1]["id"]))
    for path in [f for f in files if f.endswith(_JS_EXT) and not _is_test(f) and ".test." not in f]:
        text = _text(root, path)
        for m in _JS_CLASS.finditer(text):
            nodes.append({"id": "cls:%s:%s" % (path, m.group(1)), "label": m.group(1), "sub": path,
                          "kind": "class", "group": owner.get(path, "other"), "attrs": [], "methods": []})
            pending.append(([m.group(2).split(".")[-1]] if m.group(2) else [], nodes[-1]["id"]))
        funcs = []
        for m in _JS_FUNC.finditer(text):
            if m.group(1) not in funcs:
                funcs.append(m.group(1))
        if funcs:
            nodes.append({"id": "mod:" + path, "label": path.rsplit("/", 1)[-1], "sub": path, "kind": "module",
                          "group": owner.get(path, "other"), "attrs": [], "methods": funcs[:CAP_LIST]})
    count = {}
    for node in nodes:
        count[node["group"]] = count.get(node["group"], 0) + 1
    order = sorted(count, key=lambda g: (-count[g], g))
    nodes.sort(key=lambda n: order.index(n["group"]))
    nodes = nodes[:MAX_CLASS_NODES]
    keep = {n["id"] for n in nodes}
    byname = {}
    for node in nodes:
        byname.setdefault(node["label"], node["id"])
    edges = []
    for bases, nid in pending:
        if nid not in keep:
            continue
        for base in bases:
            if base in byname and byname[base] != nid:
                edges.append({"from": nid, "to": byname[base], "kind": "extends", "label": "extends"})
    edges.extend(_import_edges(root, files, keep))
    groups = [{"id": g, "label": names.get(g, "Other" if g == "other" else g)} for g in order
              if g in {n["group"] for n in nodes}]
    out = {"groups": groups, "nodes": nodes, "edges": edges}
    over = _overrides(root, "classes")
    if isinstance(over, dict):
        out["groups"] = _merge(out["groups"], over.get("groups"), _id)
        out["nodes"] = _merge(out["nodes"], over.get("nodes"), _id)
        out["edges"] = _merge(out["edges"], over.get("edges"), _edge_key)
        ids = {n["id"] for n in out["nodes"]}
        out["edges"] = [e for e in out["edges"] if e.get("from") in ids and e.get("to") in ids]
    return out


# ---------------------------------------------------------------- deployment

def _makefile_servers(text):
    out, name, body = [], None, []

    def flush():
        if name and _SERVE_WORDS.search(" ".join(body)):
            out.append((name, _short(next((b for b in body if _SERVE_WORDS.search(b)), ""), 70)))
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", line)
        if m and not line.startswith("\t"):
            flush()
            name, body = m.group(1), []
        elif line.startswith("\t") and name:
            body.append(line.strip())
    flush()
    return out


def _compose_services(text):
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^services:\s*$", line):
            inside = True
        elif inside and re.match(r"^\S", line):
            inside = False
        elif inside:
            m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
            if m:
                out.append(m.group(1))
    return out


def _plist_info(text):
    try:
        data = plistlib.loads(text.encode("utf-8"))
        args = data.get("ProgramArguments") or []
        return str(data.get("Label") or ""), " ".join(str(a) for a in args)
    except Exception:
        label = re.search(r"<key>Label</key>\s*<string>([^<]*)</string>", text)
        args = re.findall(r"<string>([^<]*)</string>", (re.search(r"<key>ProgramArguments</key>\s*<array>(.*?)</array>",
                                                                  text, re.S) or [None, ""])[1])
        return (label.group(1) if label else ""), " ".join(args)


def deployment(root, files, mapped):
    nodes, edges = [], []
    seen = set()

    def add(nid, label, sub, kind, group):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": _short(label, 40), "sub": _short(sub, 80), "kind": kind, "group": group})
    add("dev", "Developer machine", "", "device", "dev")
    procs = []

    def proc(nid, label, sub, source=""):
        add(nid, label, sub, "process", "dev")
        procs.append((nid, source))
    fileset = set(files)
    if "Makefile" in fileset:
        for name, cmd in _makefile_servers(_text(root, "Makefile")):
            proc("proc:make-" + name, "make " + name, cmd)
    for path in files:
        base = path.rsplit("/", 1)[-1]
        if base.endswith(".plist"):
            label, args = _plist_info(_text(root, path))
            proc("proc:" + path, label or base, args or path)
        elif base.endswith(".service"):
            text = _text(root, path)
            m = re.search(r"^ExecStart=(.*)$", text, re.M)
            proc("proc:" + path, base, m.group(1) if m else path)
        elif base == "Procfile":
            for line in _text(root, path).splitlines():
                m = re.match(r"^([\w-]+):\s*(.+)$", line)
                if m:
                    proc("proc:procfile-" + m.group(1), m.group(1), m.group(2))
        elif base == "Dockerfile":
            add("dev:docker:" + path, "Docker image", path, "device", "dev")
        elif re.match(r"^(docker-)?compose[\w.-]*\.ya?ml$", base):
            for svc in _compose_services(_text(root, path)):
                add("svc:" + svc, svc, path, "device", "dev")
        elif path == "package.json":
            try:
                scripts = json.loads(_text(root, path) or "{}").get("scripts") or {}
            except (ValueError, AttributeError):
                scripts = {}
            for name in ("start", "dev", "serve"):
                if isinstance(scripts.get(name), str):
                    proc("proc:npm-" + name, "npm run " + name, scripts[name])
        elif path.startswith("bin/") and path.count("/") == 1 and "." not in base:
            proc("proc:" + path, base, path)
    ports = {}
    scanned = _pyfiles(files)[:MAX_SCAN]
    for path in scanned:
        text = _text(root, path)
        for m in _PORT.finditer(text):
            ports.setdefault(m.group(1), (path, text))
        if "http.server" in text or re.search(r"^def serve\b", text, re.M):
            ports.setdefault("", (path, text))
    servers = []
    if len(ports) > 1:
        ports.pop("", None)
    for port, (path, text) in sorted(ports.items()):
        nid = "proc:server-" + (port or "py")
        proc(nid, "Server" + (" :" + port if port else ""), path, text)
        servers.append((nid, port))
    stores = [f for f in files if (re.match(r"^docs/[^/]+\.jsonl?$", f) or re.search(r"\.(db|sqlite3?)$", f))
              and not _is_test(f)][:CAP_LIST]
    for store in stores:
        add("store:" + store, store.rsplit("/", 1)[-1], store, "store", "dev")
        users = [p for p, src in procs if src and store.rsplit("/", 1)[-1] in src] or ([procs[0][0]] if procs else [])
        for pid in users[:2]:
            edges.append({"from": pid, "to": "store:" + store, "label": "data", "kind": "data"})
    ext = []
    for comp in _comps(mapped):
        if comp.get("kind") == "external":
            ext.append((comp["id"], comp.get("name", comp["id"])))
    over_sys = _overrides(root, "external")
    for item in over_sys if isinstance(over_sys, list) else []:
        if isinstance(item, dict) and item.get("id"):
            ext.append((str(item["id"]), str(item.get("name") or item["id"])))
    if servers:
        ext.append(("browser", "Browser"))
    if os.path.isdir(os.path.join(root, ".git")):
        ext.append(("git", "Git"))
    for eid, label in ext:
        add("ext:" + eid, label, "", "external", "ext")
    if servers:
        for sid, port in servers:
            edges.append({"from": "ext:browser", "to": sid, "label": "HTTP" + (" :" + port if port else ""),
                          "kind": "http"})
    if "ext:git" in seen and procs:
        edges.append({"from": procs[0][0], "to": "ext:git", "label": "git", "kind": "call"})
    groups = [{"id": "dev", "label": "Developer machine"}]
    if any(n["group"] == "ext" for n in nodes):
        groups.append({"id": "ext", "label": "External"})
    out = {"groups": groups, "nodes": nodes, "edges": edges}
    over = _overrides(root, "deployment")
    if isinstance(over, dict):
        out["groups"] = _merge(out["groups"], over.get("groups"), _id)
        out["nodes"] = _merge(out["nodes"], over.get("nodes"), _id)
        out["edges"] = _merge(out["edges"], over.get("edges"), _edge_key)
        ids = {n["id"] for n in out["nodes"]}
        out["edges"] = [e for e in out["edges"] if e.get("from") in ids and e.get("to") in ids]
    return out


# ---------------------------------------------------------------- use cases

def _route_label(method, pattern):
    path = re.sub(r"\(\?P<(\w+)>[^)]*\)", r"{\1}", pattern.lstrip("^"))
    path = re.sub(r"\([^)]*\)", "{}", path).rstrip("$")
    path = re.sub(r"^/api/v\d+", "", path) or "/"
    return "%s %s" % (method, path)


def _sections(text):
    m = re.search(r"\bSECTIONS\s*=\s*\[", text)
    if not m:
        return []
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"[": 1, "]": -1}.get(text[i], 0)
        i += 1
    out = []
    for obj in re.findall(r"\{[^{}]*\}", text[m.end():i]):
        mid = re.search(r"\bid\s*:\s*[\"']([\w-]+)[\"']", obj)
        lab = re.search(r"\blabel\s*:\s*[\"']([^\"']+)[\"']", obj)
        if mid:
            out.append((mid.group(1), lab.group(1) if lab else mid.group(1)))
    return out


def usecases(root, files, mapped):
    cases = []
    for path in _pyfiles(files)[:MAX_SCAN]:
        text = _text(root, path)
        if "add_parser" in text:
            tree = _parse(text)
            for node in ast.walk(tree) if tree else []:
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "add_parser" and node.args
                        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    helps = [k.value.value for k in node.keywords if k.arg == "help"
                             and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)]
                    cases.append({"id": "cli:" + node.args[0].value, "label": node.args[0].value, "group": "CLI",
                                  "sub": _short(helps[0] if helps else "", 80)})
        for m in _ROUTE.finditer(text):
            for method in re.findall(r"[\"'](\w+)[\"']", m.group(2)):
                label = _route_label(method, m.group(1))
                cases.append({"id": "http:" + label, "label": label, "group": "HTTP API", "sub": path})
    for path in files:
        if path.endswith(_JS_EXT) and path.startswith(("web/", "src/", "app/", "public/", "static/")):
            for sid, label in _sections(_text(root, path)):
                cases.append({"id": "ui:" + sid, "label": label, "group": "Web UI", "sub": path})
    uniq = {}
    for case in cases:
        uniq.setdefault(case["id"], case)
    by_group = {}
    for case in uniq.values():
        by_group.setdefault(case["group"], []).append(case)
    picked = []
    while len(picked) < MAX_CASES and any(by_group.values()):
        for grp in ("CLI", "Web UI", "HTTP API"):
            if by_group.get(grp) and len(picked) < MAX_CASES:
                picked.append(by_group[grp].pop(0))
    actors = [{"id": "person", "label": "Person", "kind": "user"}]
    for comp in _comps(mapped):
        if comp.get("kind") == "agent":
            actors.append({"id": comp["id"], "label": comp.get("name", comp["id"]), "kind": "agent"})
        elif comp.get("kind") == "external":
            actors.append({"id": comp["id"], "label": comp.get("name", comp["id"]), "kind": "external"})
    links = []
    for case in picked:
        if case["group"] in ("CLI", "Web UI"):
            links.append({"actor": "person", "case": case["id"]})
        if case["group"] == "CLI":
            links += [{"actor": a["id"], "case": case["id"]} for a in actors if a["kind"] == "agent"]
    used = [g for g in ("CLI", "Web UI", "HTTP API") if any(c["group"] == g for c in picked)]
    out = {"actors": actors, "cases": picked, "links": links, "groups": [{"id": g, "label": g} for g in used]}
    over = _overrides(root, "usecases")
    if isinstance(over, dict):
        out["actors"] = _merge(out["actors"], over.get("actors"), _id)
        out["cases"] = _merge(out["cases"], over.get("cases"), _id)
        out["groups"] = _merge(out["groups"], over.get("groups"), _id)
        out["links"] = _merge(out["links"], over.get("links"), lambda x: (x.get("actor"), x.get("case")))
    return out


# ---------------------------------------------------------------- activity

def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return (base + "." if base else "") + node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _call_of(stmt):
    value = getattr(stmt, "value", None)
    if isinstance(stmt, ast.Expr) or isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        while isinstance(value, (ast.Await,)):
            value = value.value
        if isinstance(value, ast.Call):
            return _dotted(value) or "call"
    return None


class _Full(Exception):
    pass


class _Flow:
    def __init__(self, item_id):
        self.item_id, self.steps, self.edges = item_id, [], []

    def emit(self, kind, label, pending):
        if kind != "end" and len(self.steps) >= MAX_STEPS - 1:
            raise _Full()
        sid = "%s:s%d" % (self.item_id, len(self.steps))
        self.steps.append({"id": sid, "kind": kind, "label": _short(label, 48)})
        for src, lab in pending:
            self.edges.append({"from": src, "to": sid, "label": lab})
        return sid

    def seq(self, stmts, pending):
        run = []

        def flush(pend):
            if len(run) > MAX_RUN:
                labels = run[:3] + ["... %d more steps" % (len(run) - 4)] + run[-1:]
            else:
                labels = list(run)
            del run[:]
            for lab in labels:
                pend = [(self.emit("action", lab, pend), "")]
            return pend
        for stmt in stmts:
            call = _call_of(stmt)
            if call is not None:
                run.append(call)
                continue
            if not isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith,
                                     ast.Return, ast.Raise)):
                continue
            pending = flush(pending)
            pending = self.compound(stmt, pending)
            if not pending:
                return []
        return flush(pending)

    def compound(self, stmt, pending):
        if isinstance(stmt, ast.Return):
            self.emit("end", "return", pending)
            return []
        if isinstance(stmt, ast.Raise):
            self.emit("error", "raise " + _short(ast.unparse(stmt.exc) if stmt.exc else "", 30), pending)
            return []
        if isinstance(stmt, ast.If):
            dec = self.emit("decision", _short(ast.unparse(stmt.test), 40), pending)
            yes = self.seq(stmt.body, [(dec, "yes")])
            no = self.seq(stmt.orelse, [(dec, "no")]) if stmt.orelse else [(dec, "no")]
            outs = yes + no
            if not outs:
                return []
            return [(self.emit("merge", "merge", outs), "")]
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            label = "while " + ast.unparse(stmt.test) if isinstance(stmt, ast.While) else \
                "for %s in %s" % (ast.unparse(stmt.target), ast.unparse(stmt.iter))
            loop = self.emit("loop", label, pending)
            body = self.seq(stmt.body, [(loop, "each")])
            for src, _lab in body:
                self.edges.append({"from": src, "to": loop, "label": "next"})
            return [(loop, "done")]
        if isinstance(stmt, ast.Try):
            outs = self.seq(stmt.body, pending)
            for handler in stmt.handlers:
                kind = ast.unparse(handler.type) if handler.type else "any"
                err = self.emit("error", "except " + kind, pending)
                outs += self.seq(handler.body, [(err, "")])
            if stmt.orelse:
                outs = self.seq(stmt.orelse, outs) if outs else outs
            if stmt.finalbody and outs:
                outs = self.seq(stmt.finalbody, outs)
            return outs
        return self.seq(stmt.body, pending)


def _flow(item_id, fn):
    flow = _Flow(item_id)
    start = flow.emit("start", fn.name, [])
    try:
        pend = flow.seq(fn.body, [(start, "")])
        if pend:
            flow.emit("end", "end", pend)
    except _Full:
        flow.emit("end", "end", [(flow.steps[-1]["id"], "")])
    seen, edges = set(), []
    for edge in flow.edges:
        key = (edge["from"], edge["to"], edge["label"])
        if key not in seen:
            seen.add(key)
            edges.append(edge)
    return flow.steps, edges


def _score(fn):
    length = (getattr(fn, "end_lineno", fn.lineno) or fn.lineno) - fn.lineno
    hint = fn.name in _ENTRY_HINT or fn.name.startswith(("cmd_", "handle", "run", "serve", "build"))
    return length + (50 if hint else 0)


def activity(root, files, mapped):
    owner, names = _owner(files, mapped)
    per = {}
    for path in _pyfiles(files):
        tree = _parse(_text(root, path))
        if tree is None or path not in owner:
            continue
        for fn in tree.body:
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and not fn.name.startswith("_"):
                per.setdefault(owner[path], []).append((_score(fn), path, fn))
    ranked = {}
    for cid, fns in per.items():
        fns.sort(key=lambda t: (-t[0], t[1], t[2].lineno))
        ranked[cid] = fns[:3]
    order = [c["id"] for c in _comps(mapped) if c["id"] in ranked]
    items = []
    for rank in range(3):
        for cid in order:
            if len(items) < MAX_ITEMS and rank < len(ranked[cid]):
                _s, path, fn = ranked[cid][rank]
                iid = "act:%s:%s" % (path, fn.name)
                steps, edges = _flow(iid, fn)
                items.append({"id": iid, "component": cid, "name": fn.name, "file": path, "line": fn.lineno,
                              "steps": steps, "edges": edges})
    over = _overrides(root, "activities")
    extra = over.get("items") if isinstance(over, dict) else over
    if isinstance(extra, list):
        items = _merge(items, extra, _id)
    return {"items": items}
