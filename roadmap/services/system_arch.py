"""System views (R10.33): the engineering views of one project, derived from its code (docs/SYSTEM-VIEWS-SPEC.md).

From the tracked file list and system.load() components this builds, for any project:
- context (C4 level 1): the person, the system, the external systems it talks to;
- containers (C4 level 2): the runnable units (web app, Python/Node apps, scripts) and the stores;
- components (C4 level 3): components grouped by container, edges from the import scan plus docs/system.json;
- modules: every source folder ranked by dependency tier (entry points on top, foundations at the bottom);
- layers: components in their declared layers (or derived tiers), edges up a layer flagged;
- data: data files and databases and the components that read or write them;
- flows: sequence diagrams from docs/system.json "flows", else derived from each entry point's import chain;
- details: the side panel facts per node id (files, lines, commits in 30 days, depends on, used by, jobs).

A view is {groups: [{id, label}], nodes: [{id, label, sub, kind, group, tone}], edges: [{from, to, label, kind,
count, derived}]}. Node ids carry a prefix: p: person, sys system, x: external, k: container, c: component,
m: module (folder), s: store.

Rules: read only, files are read through system._read_confined (no symlinks, inside the root, 256 KB cap), only
tracked source files (py, js, mjs, cjs, ts, tsx, jsx; at most MAX_SOURCES) are read, never executed. The scan is
cached by (root, sha, system.json mtime). Jobs and commits come in from the caller; nothing here runs git.
"""

import collections
import json
import os
import posixpath
import re
import sys
import threading

from roadmap.services import system

MAX_SOURCES = 4000
MAX_SOURCE_BYTES = 256 * 1024
MAX_MODULES = 60
MAX_STORES = 16
MAX_EXTERNALS = 8
MAX_FLOWS = 6
MAX_FLOW_STEPS = 10
TOP_FILES = 12
CACHE_MAX = 8
SOURCE_EXT = {"py": "py", "js": "js", "mjs": "js", "cjs": "js", "ts": "js", "tsx": "js", "jsx": "js"}
JS_TRY = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures|e2e)/|(^|/)test_[^/]*\.py$|_test\.py$|"
                     r"\.(test|spec)\.[cm]?[jt]sx?$|(^|/)conftest\.py$")
AUX_RE = re.compile(r"(^|/)(docs?|changes|examples?)/|\.(md|txt|rst|png|jpg|svg|gif|lock)$")
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w., \t]+)", re.M)
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#;]+)", re.M)
JS_IMPORT = re.compile(r"(?:import|export)\s[^'\"`;]*?\sfrom\s*['\"]([^'\"\n]+)['\"]|import\s*['\"]([^'\"\n]+)['\"]"
                       r"|(?:require|import)\s*\(\s*['\"]([^'\"\n]+)['\"]\s*\)")
DATA_RE = re.compile(r"['\"]([\w][\w./-]{0,80}\.(?:json|jsonl|ndjson|csv|tsv|db|sqlite3?|ya?ml|parquet))['\"]")
WRITE_RE = re.compile(r"\b(?:write|dump|save|atomic|append|writeFile|insert|update|replace)\w*\s*\(", re.I)
TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)", re.I)
GIT_RE = re.compile(r"['\"]git['\"]")
API_RE = re.compile(r"['\"`]/api\b")
CONFIG_NAMES = {"package.json", "package-lock.json", "tsconfig.json", "jsconfig.json", "pyproject.toml",
                "composer.json", "manifest.json", ".eslintrc.json", "launch.json", "settings.json", "app.json",
                "pnpm-lock.yaml", "yarn.lock", "docker-compose.yml", "docker-compose.yaml", "mkdocs.yml"}
SERVER_MODULES = {"http.server", "socketserver", "wsgiref", "flask", "fastapi", "django", "starlette", "tornado",
                  "aiohttp.web", "express", "koa", "fastify", "hono", "http"}
# import name -> (external id, label, kind, edge label)
CATALOG = {}
for _names, _ext in (
        (("sqlite3", "better-sqlite3", "sqlite"), ("sqlite", "SQLite", "db", "SQL")),
        (("psycopg2", "psycopg", "asyncpg", "pg"), ("postgres", "PostgreSQL", "db", "SQL")),
        (("pymysql", "MySQLdb", "mysql", "mysql2"), ("mysql", "MySQL", "db", "SQL")),
        (("pymongo", "motor", "mongoose", "mongodb"), ("mongo", "MongoDB", "db", "queries")),
        (("redis", "ioredis", "aioredis"), ("redis", "Redis", "db", "cache")),
        (("requests", "httpx", "aiohttp", "urllib3", "urllib.request", "http.client", "axios", "node-fetch", "got"),
         ("http-apis", "External HTTP APIs", "api", "HTTP calls")),
        (("anthropic", "@anthropic-ai/sdk", "openai"), ("ai-api", "AI model API", "api", "prompts")),
        (("boto3", "aws-sdk", "@aws-sdk"), ("aws", "AWS", "api", "SDK calls")),
        (("stripe",), ("stripe", "Stripe", "api", "payments")),
        (("smtplib", "nodemailer"), ("email", "Email (SMTP)", "api", "sends mail")),
        (("subprocess", "child_process"), ("processes", "OS processes", "proc", "runs commands"))):
    for _n in _names:
        CATALOG[_n] = _ext
NODE_BUILTINS = {"fs", "path", "url", "os", "util", "events", "stream", "crypto", "assert", "buffer", "zlib",
                 "readline", "net", "tls", "dns", "querystring", "worker_threads", "https", "http", "process",
                 "child_process", "timers", "module", "perf_hooks", "string_decoder", "vm", "v8"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
AUX_LAYERS = {"docs", "tests", "config", "other"}
SHORT_LANG = {"JavaScript": "JS", "TypeScript": "TS"}
MAX_COMP_FILES = 30
MAX_AUTO = 18
ENTRY_STEMS = {"main", "app", "server", "cli"}
BROWSER_LIBS = {"react", "react-dom", "vue", "svelte", "preact", "solid-js", "@angular", "lit"}

_CACHE = collections.OrderedDict()
_LOCK = threading.Lock()


def analyze(project_root, mapped, commits=(), jobs=(), use_cache=True):
    """The views, flows and details of one project. mapped is system.load(project_root); commits are
    systemheat.history()["commits"]; jobs are job dicts (id, task, model, status, title, started)."""
    root = system._root(project_root)
    scan = system._scan(root, use_cache)
    raw = _declared_raw(root)
    key = (root, scan["sha"], _mtime(root), json.dumps(mapped.get("edges"), sort_keys=True)[:4000])
    base = None
    if use_cache and scan["sha"]:
        with _LOCK:
            base = _CACHE.get(key)
            if base is not None:
                _CACHE.move_to_end(key)
    if base is None:
        base = _build(root, scan["files"], mapped, raw)
        if use_cache and scan["sha"]:
            with _LOCK:
                _CACHE[key] = base
                while len(_CACHE) > CACHE_MAX:
                    _CACHE.popitem(last=False)
    return _with_activity(base, list(commits or ()), list(jobs or ()), mapped)


def _mtime(root):
    try:
        return os.stat(os.path.join(root, "docs", system.SYSTEM_FILE)).st_mtime_ns
    except OSError:
        return 0


def _declared_raw(root):
    """The raw docs/system.json object for the optional keys (containers, flows), or {}."""
    try:
        data = system._read_confined(root, "docs/" + system.SYSTEM_FILE)
        out = json.loads(data.decode("utf-8")) if data else {}
    except (ValueError, UnicodeDecodeError, system._Bad, system._Refuse):
        return {}
    return out if isinstance(out, dict) else {}


# ---------------------------------------------------------------- scan

def _ext(path):
    name = path.rsplit("/", 1)[-1]
    return SOURCE_EXT.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None


def _py_index(paths):
    """dotted module name -> [paths]; every suffix of the dotted path is registered too (for src/ or nested roots)."""
    full, suffix = {}, collections.defaultdict(list)
    for path in paths:
        if not path.endswith(".py"):
            continue
        dotted = path[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            dotted = dotted[:-9]
        if not dotted or "-" in dotted:
            continue
        full.setdefault(dotted, path)
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            suffix[".".join(parts[i:])].append(path)
    return full, suffix


def _py_resolve(name, importer, full, suffix):
    """(path or None, external top name or None) for one absolute dotted import."""
    parts = name.split(".")
    for n in range(len(parts), 0, -1):
        cand = ".".join(parts[:n])
        if cand in full:
            return full[cand], None
    if parts[0] in STDLIB:
        return None, name
    for n in range(len(parts), 0, -1):
        cands = suffix.get(".".join(parts[:n]))
        if cands:
            return max(cands, key=lambda p: (len(posixpath.commonprefix([p, importer])), -len(p))), None
    return None, parts[0]


def _py_imports(text, path, full, suffix):
    """(internal target paths, external names) of one Python file."""
    targets, ext = [], []
    pkg = path.rsplit("/", 1)[0].replace("/", ".") if "/" in path else ""
    for m in PY_IMPORT.finditer(text):
        for item in m.group(1).split(","):
            name = item.strip().split(" ")[0].strip()
            if re.fullmatch(r"[A-Za-z_][\w.]*", name or ""):
                hit, out = _py_resolve(name, path, full, suffix)
                (targets.append(hit) if hit else ext.append(out) if out else None)
    for m in PY_FROM.finditer(text):
        mod, names = m.group(1), m.group(2).strip("() \t\n")
        names = [n.strip().split(" ")[0] for n in names.replace("\n", " ").split(",") if n.strip()]
        if mod.startswith("."):
            dots = len(mod) - len(mod.lstrip("."))
            base = pkg.split(".") if pkg else []
            base = base[:len(base) - (dots - 1)] if dots > 1 else base
            rest = mod.lstrip(".")
            prefix = ".".join(base + ([rest] if rest else []))
            found = False
            for n in names:
                sub = (prefix + "." + n) if prefix else n
                if sub in full:
                    targets.append(full[sub])
                    found = True
            if not found and prefix in full:
                targets.append(full[prefix])
            continue
        hit = None
        for n in names:
            if (mod + "." + n) in full:
                targets.append(full[mod + "." + n])
                hit = True
        if not hit:
            got, out = _py_resolve(mod, path, full, suffix)
            if got:
                targets.append(got)
            elif out:
                ext.append(out)
    return targets, ext


def _js_resolve(spec, importer, known):
    if spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        bases = [base]
    elif spec.startswith("/"):
        top = importer.split("/")[0]
        bases = [spec[1:], top + spec] if "/" in importer else [spec[1:]]
    elif spec.startswith(("@/", "~/")):
        bases = ["src/" + spec[2:], spec[2:]]
    else:
        return None
    for b in bases:
        cands = [b] + [b + e for e in JS_TRY] + [b + "/index" + e for e in JS_TRY]
        if b.endswith(".js"):
            cands += [b[:-3] + ".ts", b[:-3] + ".tsx"]
        for c in cands:
            if c in known:
                return c
    return None


def _js_imports(text, path, known):
    targets, ext = [], []
    for m in JS_IMPORT.finditer(text):
        spec = m.group(1) or m.group(2) or m.group(3)
        if not spec:
            continue
        hit = _js_resolve(spec, path, known)
        if hit:
            targets.append(hit)
        elif not spec.startswith((".", "/")):
            name = spec[5:] if spec.startswith("node:") else spec
            parts = name.split("/")
            top = "/".join(parts[:2]) if name.startswith("@") else parts[0]
            if top in CATALOG or name in CATALOG:
                ext.append(name if name in CATALOG else top)
            elif top not in NODE_BUILTINS and re.fullmatch(r"@?[\w.-]+(/[\w.-]+)?", top):
                ext.append(top)
    return targets, ext


def _read_sources(root, files):
    """{path: text} for the tracked source files (tests included; the caller filters)."""
    out = {}
    for path in files:
        if _ext(path) is None:
            continue
        if len(out) >= MAX_SOURCES:
            break
        try:
            data = system._read_confined(root, path, MAX_SOURCE_BYTES)
        except (system._Bad, system._Refuse):
            continue
        if data is not None:
            out[path] = data.decode("utf-8", "replace")
    return out


def _is_test(path):
    return bool(TEST_RE.search(path))


# ---------------------------------------------------------------- build

def _build(root, files, mapped, raw):
    texts = _read_sources(root, files)
    known = set(files)
    full, suffix = _py_index(files)
    lines = {p: t.count("\n") + (0 if t.endswith("\n") or not t else 1) for p, t in texts.items()}
    file_edges = collections.Counter()
    externals = collections.defaultdict(set)   # external id -> files
    packages = collections.defaultdict(collections.Counter)   # file -> external package names
    servers, fetchers, stores = set(), set(), collections.defaultdict(dict)
    tables = collections.defaultdict(set)
    browser, electron, ipc = set(), set(), set()
    for path, text in texts.items():
        test = _is_test(path)
        kind = _ext(path)
        targets, ext = (_py_imports(text, path, full, suffix) if kind == "py" else _js_imports(text, path, known))
        if test:
            continue
        for t in targets:
            if t != path and not _is_test(t):
                file_edges[(path, t)] += 1
        for name in ext:
            top = name.split(".")[0]
            if name in SERVER_MODULES or top in SERVER_MODULES and top not in ("http",):
                servers.add(path)
            cat = CATALOG.get(name) or (CATALOG.get(top) if top not in ("urllib", "http") else None)
            if cat:
                xid = cat[0]
                if xid == "processes" and GIT_RE.search(text):
                    xid = "git"
                externals[xid].add(path)
            elif top not in STDLIB and name not in NODE_BUILTINS:
                packages[path][top if not name.startswith("@") else name] += 1
        if kind == "js" and "fetch(" in text and API_RE.search(text):
            fetchers.add(path)
        if any(n.split("/")[0] in BROWSER_LIBS for n in ext) or path.endswith((".tsx", ".jsx")):
            browser.add(path)
        if "electron" in ext:
            electron.add(path)
        if "ipcMain" in text:
            ipc.add(("main", path))
        if "ipcRenderer" in text or "contextBridge" in text:
            ipc.add(("renderer", path))
        for m in DATA_RE.finditer(text):
            name = m.group(1).rsplit("/", 1)[-1]
            if name in CONFIG_NAMES or name.startswith(".") or name.count(".") > 2:
                continue
            # A write call within three lines of the name counts as a write; else the file only names (reads) it.
            lo = text.rfind("\n", 0, max(0, m.start() - 1))
            for _ in range(2):
                lo = text.rfind("\n", 0, max(0, lo))
            hi = m.end()
            for _ in range(3):
                nxt = text.find("\n", hi + 1)
                hi = len(text) if nxt < 0 else nxt
            mode = "rw" if WRITE_RE.search(text, max(0, lo), hi) else "r"
            if stores[name].get(path) != "rw":
                stores[name][path] = mode
        for m in TABLE_RE.finditer(text):
            tables[path].add(m.group(1))
    src_files = sorted(p for p in texts if not _is_test(p))
    comps = [c for c in mapped["components"] if isinstance(c, dict) and c.get("id")]
    if mapped.get("source") == "baseline" and src_files:
        comps = _auto_components(files, src_files, comps)
    by_id = {c["id"]: c for c in comps}
    owner_of = {}
    assigned, _ = system.assign_files(files, [{"id": c["id"], "files": c.get("files", [])} for c in comps])
    for cid, paths in assigned.items():
        for p in paths:
            owner_of[p] = cid
    ctx = {"root": root, "files": files, "comps": comps, "by_id": by_id, "owner": owner_of, "lines": lines,
           "browser": browser, "electron": electron, "ipc": ipc,
           "file_edges": file_edges, "externals": externals, "packages": packages, "servers": servers,
           "fetchers": fetchers, "stores": stores, "tables": tables, "src": src_files, "raw": raw,
           "mapped": mapped, "details": {}}
    ctx["aux"] = {c["id"] for c in comps if _aux(c, assigned.get(c["id"], []))}
    comp_edges = _component_edges(ctx)
    ctx["comp_edges"] = comp_edges
    containers = _containers(ctx)
    ctx["containers"] = containers
    views = {"components": _components_view(ctx), "containers": _containers_view(ctx), "context": _context_view(ctx),
             "modules": _modules_view(ctx), "layers": _layers_view(ctx), "data": _data_view(ctx)}
    flows = _flows(ctx)
    _component_details(ctx, assigned)
    langs = collections.Counter(system._language([p]) for p in files if system._language([p]))
    stats = {"files": len(files), "sourceFiles": len(src_files), "lines": sum(lines[p] for p in src_files),
             "languages": dict(langs.most_common(6)), "imports": sum(file_edges.values()),
             "modules": len(views["modules"]["nodes"]), "sourceCapped": len(texts) >= MAX_SOURCES}
    ctx["details"]["sys"] = {"kind": "system", "title": _project_name(root, raw), "stats": stats}
    return {"views": views, "flows": flows, "details": ctx["details"], "stats": stats, "_lines": lines}


def _auto_components(files, src, base):
    """Components for a project without docs/system.json: source folders split until each holds at most
    MAX_COMP_FILES source files (wrapper folders such as src/ are walked through), the largest MAX_AUTO kept and the
    rest merged into "Other code"; then the baseline components that hold no source (docs, config) as support."""
    leaves = []
    limit = MAX_COMP_FILES if len(src) > 2 * MAX_COMP_FILES else 3

    def walk(prefix, paths, depth):
        subs, direct = collections.defaultdict(list), []
        for p in paths:
            rest = p[len(prefix) + 1:] if prefix else p
            (subs[rest.split("/")[0]] if "/" in rest else direct).append(p)
        if (len(paths) <= limit and depth > 0) or depth >= 5 or not subs:
            leaves.append((prefix, paths, True))
            return
        if direct:
            leaves.append((prefix, direct, False))
        for name in sorted(subs):
            walk(prefix + "/" + name if prefix else name, subs[name], depth + 1)
    walk("", src, 0)
    leaves.sort(key=lambda leaf: (-len(leaf[1]), leaf[0]))
    keep, rest = leaves[:MAX_AUTO - 1], leaves[MAX_AUTO - 1:]
    if len(rest) == 1:
        keep, rest = leaves, []
    out, taken = [], set()
    for prefix, paths, deep in sorted(keep, key=lambda leaf: leaf[0]):
        glob = (prefix + "/**" if deep else prefix + "/*") if prefix else ("**" if deep else "*")
        parts = prefix.split("/") if prefix else []
        name = prefix if len(prefix) <= 24 else "/".join(parts[-2:])
        cid = system._slug("auto-" + (prefix or "root"))
        while cid in taken:
            cid += "-2"
        taken.add(cid)
        out.append({"id": cid, "name": name or "Root files", "layer": "code", "kind": "module", "files": [glob],
                    "entries": _entries(paths), "language": system._language(paths), "notes": None})
    if rest:
        globs = [(p + "/**" if deep else p + "/*") if p else "*" for p, _, deep in rest]
        paths = [x for _, ps, _ in rest for x in ps]
        out.append({"id": "auto-other", "name": "Other code", "layer": "code", "kind": "module", "files": globs,
                    "entries": [], "language": system._language(paths), "notes": "Small folders merged."})
    src_set = set(src)
    assigned, _ = system.assign_files(files, [{"id": c["id"], "files": c.get("files", [])} for c in base])
    for c in base:
        if not any(p in src_set for p in assigned.get(c["id"], [])):
            out.append(dict(c, layer=c.get("layer") if c.get("layer") in AUX_LAYERS else "other"))
    return out


def _entries(paths):
    """Entry points among paths: bin scripts, __main__.py, index.html and shallow main/index/app/server/cli files."""
    out = []
    for p in paths:
        base = p.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        index = stem == "index" and p.count("/") <= 2 and (p.count("/") == 0 or p.split("/")[-2] == "src")
        if p.startswith("bin/") or base in ("__main__.py", "index.html", "manage.py") or index or (
                stem in ENTRY_STEMS and p.count("/") <= 3 and _ext(p)):
            out.append(p)
    return sorted(out, key=lambda p: (p.count("/"), p))[:6]


def _project_name(root, raw):
    name = raw.get("name") if isinstance(raw.get("name"), str) else None
    return (name or os.path.basename(root))[:60]


def _aux(comp, paths):
    """True for a component that is mostly tests, fixtures, docs or config (kept out of the C4 views)."""
    layer = comp.get("layer")
    if layer in AUX_LAYERS or str(comp.get("name") or "").startswith("."):
        return True
    if paths and all(p.startswith(".") for p in paths):
        return True
    if layer == "external" or comp.get("kind") in ("store", "agent"):
        return False
    if not paths:
        return comp.get("kind") != "service"
    return sum(1 for p in paths if _is_test(p) or AUX_RE.search(p)) * 2 > len(paths)


def _short(path):
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _label_of(counter, limit=2):
    names = [n for n, _ in counter.most_common()]
    text = ", ".join(names[:limit])
    return text + (" +%d" % (len(names) - limit) if len(names) > limit else "")


def _component_edges(ctx):
    """Declared edges (with labels) plus import edges aggregated by component. {(from, to): edge}."""
    out = {}
    for e in ctx["mapped"].get("edges") or []:
        if e.get("from") in ctx["by_id"] and e.get("to") in ctx["by_id"] and e["from"] != e["to"]:
            out[(e["from"], e["to"])] = {"from": e["from"], "to": e["to"], "label": e.get("label") or "",
                                         "kind": e.get("kind") or "call", "count": 0, "derived": False,
                                         "_names": collections.Counter()}
    for (a, b), n in ctx["file_edges"].items():
        ca, cb = ctx["owner"].get(a), ctx["owner"].get(b)
        if not ca or not cb or ca == cb:
            continue
        e = out.get((ca, cb))
        if e is None:
            e = out[(ca, cb)] = {"from": ca, "to": cb, "label": "", "kind": "import", "count": 0, "derived": True,
                                 "_names": collections.Counter()}
        e["count"] += n
        e["_names"][_short(b)] += n
    for e in out.values():
        if not e["label"]:
            e["label"] = "uses " + _label_of(e["_names"])
    return out


def _edge(e, prefix="c:"):
    return {"from": prefix + e["from"], "to": prefix + e["to"], "label": e["label"], "kind": e["kind"],
            "count": e["count"], "derived": e["derived"]}


def _human(n):
    return "%.1fk" % (n / 1000.0) if n >= 1000 else str(n)


def _comp_sub(ctx, comp, paths=None):
    paths = paths if paths is not None else [p for p, c in ctx["owner"].items() if c == comp["id"]]
    n = sum(ctx["lines"].get(p, 0) for p in paths)
    lang = comp.get("language") or comp.get("kind") or ""
    bits = [SHORT_LANG.get(lang, lang), "%d files" % len(paths)]
    if n:
        bits.append(_human(n) + " loc")
    return " · ".join(b for b in bits if b)


# ---------------------------------------------------------------- containers and context

def _top(path):
    return path.split("/")[0] if "/" in path else ""


def _containers(ctx):
    """[{id, name, tech, comps: [ids], entries, server, web}] for the non-aux components, plus a stores node."""
    raw = ctx["raw"].get("containers")
    comps = [c for c in ctx["comps"] if c["id"] not in ctx["aux"] and c.get("layer") != "external"]
    out = []
    if isinstance(raw, list) and raw:
        taken = set()
        for item in raw[:12]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            cid = system._slug(item["id"])
            members = [m for m in item.get("components") or [] if m in ctx["by_id"] and m not in taken]
            taken.update(members)
            out.append({"id": cid, "name": str(item.get("name") or cid)[:60], "tech": str(item.get("tech") or "")[:60],
                        "notes": str(item.get("notes") or "")[:300], "comps": members})
        rest = [c["id"] for c in comps if c["id"] not in taken]
        if rest:
            out.append({"id": "other", "name": "Other code", "tech": "", "notes": "", "comps": rest})
    else:
        groups = collections.OrderedDict()
        files = ctx["files"]
        web_tops = {_top(p) for p in files if p.rsplit("/", 1)[-1] == "index.html" and not _is_test(p)}
        py_tops = {_top(p) for p in files if p.endswith("/__init__.py") and p.count("/") <= 2 and not _is_test(p)}
        runtime = {}
        for c in comps:
            src = [p for p, o in ctx["owner"].items() if o == c["id"] and _ext(p)]
            if src and sum(1 for p in src if p in ctx["browser"]) * 3 >= len(src):
                runtime[c["id"]] = "browser"
            elif any(p in ctx["electron"] for p in src):
                runtime[c["id"]] = "electron"
        bases = {c["id"]: (c.get("files") or [""])[0].rsplit("/", 1)[0] for c in comps}
        for c in comps:
            if c["id"] not in runtime:
                parents = [o for o in runtime if bases[o] and bases[c["id"]].startswith(bases[o] + "/")]
                if parents:
                    runtime[c["id"]] = runtime[max(parents, key=lambda o: len(bases[o]))]
        for c in comps:
            paths = [p for p, o in ctx["owner"].items() if o == c["id"]]
            src = [p for p in paths if _ext(p)] or paths
            tops = collections.Counter(_top(p) for p in src)
            top = tops.most_common(1)[0][0] if tops else ""
            where = (top + ": ") if top else ""
            browser = runtime.get(c["id"]) == "browser"
            if runtime.get(c["id"]) == "electron":
                key, name, tech = "electron-" + system._slug(top or "root"), where + "Electron main", "Electron, Node"
            elif browser or top in web_tops:
                key, name, tech = "web-" + system._slug(top or "root"), where + "Web UI", "browser"
            elif top in ("bin", "tools", "scripts"):
                key, name, tech = "scripts", "Scripts and tools", ""
            elif top in py_tops or c.get("language") == "Python":
                key, name, tech = "py-" + system._slug(top or "root"), (top + " (Python)") if top else "Python app", ""
            elif c.get("kind") == "store":
                continue
            else:
                key, name, tech = "code-" + system._slug(top or "root"), (top or "Root") + " code", ""
            g = groups.setdefault(key, {"id": key, "name": name, "tech": tech, "notes": "", "comps": []})
            g["comps"].append(c["id"])
        out = list(groups.values())
    for k in out:
        paths = [p for p, o in ctx["owner"].items() if o in set(k["comps"])]
        k["server"] = any(p in ctx["servers"] for p in paths)
        k["web"] = any(p.rsplit("/", 1)[-1] == "index.html" for p in paths) or any(p in ctx["fetchers"] for p in paths)
        k["entries"] = [e for cid in k["comps"] for e in (ctx["by_id"][cid].get("entries") or [])][:6]
        k["cli"] = any(e.startswith("bin/") or e.endswith("__main__.py") for e in k["entries"])
        if k["tech"]:
            continue
        langs = collections.Counter(ctx["by_id"][cid].get("language") for cid in k["comps"]
                                    if ctx["by_id"][cid].get("language"))
        bits = [langs.most_common(1)[0][0] if langs else ""]
        if k["server"]:
            bits.append("HTTP server")
        if k["cli"]:
            bits.append("CLI")
        k["tech"] = ", ".join(b for b in bits if b)
    return out


def _container_of(ctx):
    return {cid: k["id"] for k in ctx["containers"] for cid in k["comps"]}


def _external_nodes(ctx):
    """External systems: catalogue hits from imports plus declared components in the 'external' layer."""
    labels = {v[0]: v for v in CATALOG.values()}
    labels["git"] = ("git", "Git", "proc", "runs git")
    out = []
    for xid, paths in sorted(ctx["externals"].items(), key=lambda kv: -len(kv[1]))[:MAX_EXTERNALS]:
        _, label, kind, verb = labels[xid]
        out.append({"id": "x:" + xid, "label": label, "sub": "used by %d files" % len(paths), "kind": "external",
                    "verb": verb, "files": sorted(paths), "store": kind == "db"})
    for c in ctx["comps"]:
        if c.get("layer") == "external":
            out.append({"id": "x:" + c["id"], "label": c["name"], "sub": c.get("kind") or "external",
                        "kind": "external", "verb": "", "files": [], "store": False, "comp": c["id"]})
    return out


def _ext_edges(ctx, owner_map, prefix_of):
    """Edges from inner nodes to external systems: (from node id, to node id, label)."""
    edges = {}
    for x in _external_nodes(ctx):
        if x.get("comp"):
            for e in ctx["comp_edges"].values():
                if e["from"] == x["comp"] and e["to"] in owner_map:
                    edges[(x["id"], prefix_of(owner_map[e["to"]]))] = e["label"]
                elif e["to"] == x["comp"] and e["from"] in owner_map:
                    edges[(prefix_of(owner_map[e["from"]]), x["id"])] = e["label"]
            continue
        for p in x["files"]:
            cid = ctx["owner"].get(p)
            if cid in owner_map:
                edges.setdefault((prefix_of(owner_map[cid]), x["id"]), x["verb"])
    return [{"from": a, "to": b, "label": lab, "kind": "event" if a.startswith("x:") else "call", "count": 0,
             "derived": True} for (a, b), lab in edges.items()]


def _context_view(ctx):
    name = _project_name(ctx["root"], ctx["raw"])
    ks = ctx["containers"]
    how = sorted({"browser" for k in ks if k["web"]} | {"CLI" for k in ks if k["cli"]})
    langs = collections.Counter(system._language([p]) for p in ctx["src"])
    nodes = [{"id": "p:user", "label": "User", "sub": "developer or operator", "kind": "person", "group": "people"},
             {"id": "sys", "label": name, "sub": " · ".join([n for n, _ in langs.most_common(2)] +
                                                             ["%d containers" % len(ks)]),
              "kind": "system", "group": "system"}]
    edges = [{"from": "p:user", "to": "sys", "label": "uses via " + (" and ".join(how) or "its tools"),
              "kind": "call", "count": 0, "derived": True}]
    ext = _external_nodes(ctx)
    for x in ext:
        nodes.append({"id": x["id"], "label": x["label"], "sub": x["sub"], "kind": "store" if x["store"] else
                      "external", "group": "external"})
    every = {c["id"]: "sys" for c in ctx["comps"]}
    seen = set()
    for e in _ext_edges(ctx, every, lambda v: v):
        if (e["from"], e["to"]) not in seen:
            seen.add((e["from"], e["to"]))
            edges.append(e)
    ctx["details"]["p:user"] = {"kind": "person", "title": "User",
                                "notes": "Uses the system via " + (" and ".join(how) or "its tools") + "."}
    for x in ext:
        ctx["details"][x["id"]] = {"kind": "external", "title": x["label"], "files": [{"path": p} for p in
                                                                                      x["files"][:TOP_FILES]],
                                   "notes": (ctx["by_id"].get(x.get("comp")) or {}).get("notes") or
                                   "Detected from imports in %d files." % len(x["files"])}
    groups = [{"id": "people", "label": "People"}, {"id": "system", "label": "Software system"}]
    if ext:
        groups.append({"id": "external", "label": "External systems"})
    return {"groups": groups, "nodes": nodes, "edges": edges}


def _store_nodes(ctx):
    """Stores referenced from code: [{id, label, sub, files (readers: path -> mode), tracked}] top MAX_STORES."""
    ranked = sorted(ctx["stores"].items(), key=lambda kv: (-len(kv[1]), kv[0]))[:MAX_STORES]
    out = []
    for name, users in ranked:
        tracked = sorted(p for p in ctx["files"] if p.rsplit("/", 1)[-1] == name)[:6]
        ext = name.rsplit(".", 1)[-1].upper()
        kind = "SQLite file" if ext in ("DB", "SQLITE", "SQLITE3") else ext + " file"
        out.append({"id": "s:" + system._slug(name), "label": name, "sub": "%s · %d users" % (kind, len(users)),
                    "users": users, "tracked": tracked})
    return out


def _containers_view(ctx):
    owner = _container_of(ctx)
    nodes = [{"id": "p:user", "label": "User", "sub": "", "kind": "person", "group": "people"}]
    for i, k in enumerate(ctx["containers"]):
        n = sum(1 for p, c in ctx["owner"].items() if c in set(k["comps"]))
        nodes.append({"id": "k:" + k["id"], "label": k["name"], "sub": " · ".join(b for b in (k["tech"], "%d files" % n)
                                                                                    if b),
                      "kind": "container", "group": "containers", "tone": i})
        ctx["details"]["k:" + k["id"]] = {"kind": "container", "title": k["name"], "tech": k["tech"],
                                          "notes": k.get("notes") or "", "entries": k["entries"],
                                          "components": [{"id": "c:" + c, "label": ctx["by_id"][c]["name"]}
                                                         for c in k["comps"]]}
    edges = []
    for k in ctx["containers"]:
        if k["web"]:
            edges.append({"from": "p:user", "to": "k:" + k["id"], "label": "opens in browser", "kind": "call",
                          "count": 0, "derived": True})
        elif k["cli"]:
            edges.append({"from": "p:user", "to": "k:" + k["id"], "label": "runs commands", "kind": "call",
                          "count": 0, "derived": True})
    agg = {}
    for e in ctx["comp_edges"].values():
        a, b = owner.get(e["from"]), owner.get(e["to"])
        if a and b and a != b:
            g = agg.setdefault((a, b), {"count": 0, "labels": collections.Counter(), "kind": e["kind"]})
            g["count"] += e["count"] or 1
            if not e["derived"]:
                g["labels"][e["label"]] += 1000
    servers = [k for k in ctx["containers"] if k["server"]]
    for k in ctx["containers"]:
        if any(p in ctx["fetchers"] for p in ctx["owner"] if ctx["owner"][p] in set(k["comps"])):
            for s in servers:
                if s["id"] != k["id"] and (k["id"], s["id"]) not in agg:
                    agg[(k["id"], s["id"])] = {"count": 1, "labels": collections.Counter({"HTTP JSON /api": 9}),
                                               "kind": "call"}
    if any(side == "renderer" for side, _ in ctx["ipc"]):
        mains = {owner.get(ctx["owner"].get(p)) for side, p in ctx["ipc"] if side == "main"}
        for k in ctx["containers"]:
            if k["id"].startswith("web-"):
                for m in mains:
                    if m and m != k["id"]:
                        agg[(k["id"], m)] = {"count": 1, "labels": collections.Counter({"IPC (invoke)": 1}),
                                             "kind": "call"}
    for (a, b), g in agg.items():
        plural = "" if g["count"] == 1 else "s"
        label = _label_of(g["labels"], 1) if g["labels"] else "%d import%s" % (g["count"], plural)
        edges.append({"from": "k:" + a, "to": "k:" + b, "label": label, "kind": g["kind"],
                      "count": g["count"], "derived": True})
    stores = _store_nodes(ctx)
    groups = [{"id": "people", "label": "People"}, {"id": "containers", "label": "Containers (run separately)"}]
    if stores:
        users = collections.defaultdict(set)
        for s in stores:
            for p, mode in s["users"].items():
                if owner.get(ctx["owner"].get(p)):
                    users[owner[ctx["owner"][p]]].add(mode)
        names = ", ".join(s["label"] for s in stores[:3]) + (" +%d" % (len(stores) - 3) if len(stores) > 3 else "")
        nodes.append({"id": "s:files", "label": "Data files", "sub": names, "kind": "store", "group": "stores"})
        ctx["details"]["s:files"] = {"kind": "store", "title": "Data files", "notes": "Files the code names: " +
                                     ", ".join(s["label"] for s in stores) + "."}
        for kid, modes in users.items():
            edges.append({"from": "k:" + kid, "to": "s:files", "label": "reads, writes" if "rw" in modes else "reads",
                          "kind": "data", "count": 0, "derived": True})
        groups.append({"id": "stores", "label": "Stores"})
    ext = _external_nodes(ctx)
    if ext:
        groups.append({"id": "external", "label": "External systems"})
        for x in ext:
            nodes.append({"id": x["id"], "label": x["label"], "sub": x["sub"], "kind": "store" if x["store"] else
                          "external", "group": "external"})
        edges.extend(_ext_edges(ctx, owner, lambda v: "k:" + v))
    return {"groups": groups, "nodes": nodes, "edges": _dedupe(edges)}


def _dedupe(edges):
    seen, out = set(), []
    for e in edges:
        k = (e["from"], e["to"])
        if k not in seen and e["from"] != e["to"]:
            seen.add(k)
            out.append(e)
    return out


def _components_view(ctx):
    owner = _container_of(ctx)
    tone = {k["id"]: i for i, k in enumerate(ctx["containers"])}
    groups = [{"id": "k:" + k["id"], "label": k["name"] + (" [" + k["tech"] + "]" if k["tech"] else "")}
              for k in ctx["containers"] if k["comps"]]
    nodes, ids = [], set()
    for c in ctx["comps"]:
        if c["id"] in ctx["aux"]:
            continue
        if c.get("layer") == "external":
            group = "external"
        elif owner.get(c["id"]):
            group = "k:" + owner[c["id"]]
        elif c.get("kind") == "store":
            group = "stores"
        else:
            continue
        ids.add(c["id"])
        nodes.append({"id": "c:" + c["id"], "label": c["name"], "sub": _comp_sub(ctx, c), "group": group,
                      "kind": "external" if group == "external" else "store" if c.get("kind") == "store" else
                      "component", "tone": tone.get(owner.get(c["id"]), 0)})
    if any(n["group"] == "stores" for n in nodes):
        groups.append({"id": "stores", "label": "Stores"})
    if any(n["group"] == "external" for n in nodes):
        groups.insert(0, {"id": "external", "label": "External"})
    edges = [_edge(e) for e in ctx["comp_edges"].values() if e["from"] in ids and e["to"] in ids]
    return {"groups": groups, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- tiers, modules, layers, data

def _tiers(nodes, edges):
    """Row per node: dependency height, sinks at the bottom (row = max height - height). Cycles share a row."""
    adj = collections.defaultdict(set)
    for a, b in edges:
        if a != b:
            adj[a].add(b)
    comp = _scc(nodes, adj)
    cadj = collections.defaultdict(set)
    for a in nodes:
        for b in adj[a]:
            if comp[a] != comp[b]:
                cadj[comp[a]].add(comp[b])
    height = {}

    def h(c):
        stack = [(c, False)]
        while stack:
            node, done = stack.pop()
            if node in height:
                continue
            if done:
                height[node] = 1 + max((height[x] for x in cadj[node]), default=-1)
                continue
            stack.append((node, True))
            stack.extend((x, False) for x in cadj[node] if x not in height)
        return height[c]
    top = max((h(comp[n]) for n in nodes), default=0)
    return {n: top - height[comp[n]] for n in nodes}, comp


def _scc(nodes, adj):
    """Tarjan, iterative. node -> component index."""
    index, low, on, stack, out = {}, {}, set(), [], {}
    counter = [0]
    for start in nodes:
        if start in index:
            continue
        work = [(start, iter(sorted(adj[start])))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on.add(start)
        while work:
            v, it = work[-1]
            pushed = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(adj[w]))))
                    pushed = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if pushed:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on.discard(w)
                    out[w] = v
                    if w == v:
                        break
    return out


def _tier_name(i, n):
    if n <= 1:
        return "Tier 1"
    if i == 0:
        return "Tier 1 · entry points"
    if i == n - 1:
        return "Tier %d · foundation" % (i + 1)
    return "Tier %d" % (i + 1)


def _modules_view(ctx):
    files_by_dir = collections.defaultdict(list)
    for p in ctx["src"]:
        files_by_dir[posixpath.dirname(p) or "(root)"].append(p)
    dirs = sorted(files_by_dir, key=lambda d: (-len(files_by_dir[d]), d))[:MAX_MODULES]
    keep = set(dirs)
    edge_n, names = collections.Counter(), collections.defaultdict(collections.Counter)
    for (a, b), n in ctx["file_edges"].items():
        da, db = posixpath.dirname(a) or "(root)", posixpath.dirname(b) or "(root)"
        if da != db and da in keep and db in keep:
            edge_n[(da, db)] += n
            names[(da, db)][_short(b)] += n
    rows, comp = _tiers(dirs, list(edge_n))
    n_rows = max(rows.values(), default=0) + 1
    comp_tone = {c["id"]: i for i, c in enumerate(ctx["comps"])}
    nodes = []
    for d in dirs:
        owners = collections.Counter(ctx["owner"].get(p) for p in files_by_dir[d])
        cid = owners.most_common(1)[0][0] if owners else None
        n = sum(ctx["lines"].get(p, 0) for p in files_by_dir[d])
        nodes.append({"id": "m:" + d, "label": d, "sub": "%d files · %s loc" % (len(files_by_dir[d]), _human(n)),
                      "kind": "module", "group": "t%d" % rows[d], "tone": comp_tone.get(cid, 0)})
        out_deps = [{"id": "m:" + b, "label": b, "count": c} for (a, b), c in edge_n.most_common() if a == d]
        in_deps = [{"id": "m:" + a, "label": a, "count": c} for (a, b), c in edge_n.most_common() if b == d]
        pk = collections.Counter()
        for p in files_by_dir[d]:
            pk.update(ctx["packages"].get(p, {}))
        ctx["details"]["m:" + d] = {"kind": "module", "title": d,
                                    "component": {"id": "c:" + cid, "label": ctx["by_id"][cid]["name"]}
                                    if cid in ctx["by_id"] else None,
                                    "files": [{"path": p, "lines": ctx["lines"].get(p, 0)} for p in
                                              sorted(files_by_dir[d], key=lambda p: -ctx["lines"].get(p, 0))
                                              ][:TOP_FILES * 2],
                                    "fileCount": len(files_by_dir[d]), "lines": n,
                                    "dependsOn": out_deps, "usedBy": in_deps,
                                    "packages": [k for k, _ in pk.most_common(10)]}
    edges = []
    for (a, b), n in edge_n.items():
        cyc = comp[a] == comp[b]
        edges.append({"from": "m:" + a, "to": "m:" + b, "label": _label_of(names[(a, b)]), "count": n,
                      "kind": "cycle" if cyc else "import", "derived": True})
    groups = [{"id": "t%d" % i, "label": _tier_name(i, n_rows)} for i in range(n_rows)]
    return {"groups": groups, "nodes": nodes, "edges": edges}


def _layers_view(ctx):
    mapped = ctx["mapped"]
    comps = ctx["comps"]
    declared = mapped.get("source") != "baseline"
    edges = list(ctx["comp_edges"].values())
    nodes = []
    if declared:
        order = list(mapped.get("layers") or [])
        groups = [{"id": "l:" + name, "label": name} for name in order]
        rank = {name: i for i, name in enumerate(order)}
        for c in comps:
            nodes.append({"id": "c:" + c["id"], "label": c["name"], "sub": _comp_sub(ctx, c), "kind": "component" if
                          c.get("layer") != "external" else "external", "group": "l:" + c["layer"], "tone": rank.get(
                              c["layer"], 0)})
        out = []
        for e in edges:
            ra, rb = rank.get(ctx["by_id"][e["from"]]["layer"], 0), rank.get(ctx["by_id"][e["to"]]["layer"], 0)
            item = _edge(e)
            if rb < ra and ctx["by_id"][e["from"]]["layer"] != "external" and e["from"] not in ctx["aux"]:
                item["kind"] = "violation"
                item["label"] = "up: " + item["label"]
            out.append(item)
        return {"groups": [g for g in groups if any(n["group"] == g["id"] for n in nodes)], "nodes": nodes,
                "edges": out}
    core = [c["id"] for c in comps if c["id"] not in ctx["aux"]]
    rows, comp = _tiers(core, [(e["from"], e["to"]) for e in edges if e["from"] in core and e["to"] in core])
    n_rows = max(rows.values(), default=0) + 1
    groups = [{"id": "t%d" % i, "label": _tier_name(i, n_rows)} for i in range(n_rows)]
    for c in comps:
        aux = c["id"] in ctx["aux"]
        nodes.append({"id": "c:" + c["id"], "label": c["name"], "sub": _comp_sub(ctx, c), "kind": "component",
                      "group": "aux" if aux else "t%d" % rows[c["id"]], "tone": 0 if aux else rows[c["id"]]})
    if ctx["aux"]:
        groups.append({"id": "aux", "label": "Support (tests, docs, config)"})
    out = []
    for e in edges:
        item = _edge(e)
        if e["from"] in comp and e["to"] in comp and comp[e["from"]] == comp[e["to"]]:
            item["kind"] = "cycle"
        out.append(item)
    return {"groups": groups, "nodes": nodes, "edges": out}


def _data_view(ctx):
    stores = _store_nodes(ctx)
    ext = [x for x in _external_nodes(ctx) if x["store"]]
    users = collections.defaultdict(dict)   # component -> store id -> mode
    for s in stores:
        for p, mode in s["users"].items():
            cid = ctx["owner"].get(p)
            if cid:
                prev = users[cid].get(s["id"])
                users[cid][s["id"]] = "rw" if "rw" in (prev, mode) else "r"
    for x in ext:
        for p in x["files"]:
            cid = ctx["owner"].get(p)
            if cid:
                users[cid][x["id"]] = "rw"
    nodes, edges = [], []
    for c in ctx["comps"]:
        if c["id"] in users:
            nodes.append({"id": "c:" + c["id"], "label": c["name"], "sub": _comp_sub(ctx, c), "kind": "component",
                          "group": "code", "tone": 0})
            for sid, mode in sorted(users[c["id"]].items()):
                edges.append({"from": "c:" + c["id"], "to": sid, "label": "reads, writes" if mode == "rw" else "reads",
                              "kind": "data", "count": 0, "derived": True})
    for s in stores:
        nodes.append({"id": s["id"], "label": s["label"], "sub": s["sub"], "kind": "store", "group": "files"})
        ctx["details"][s["id"]] = {"kind": "store", "title": s["label"], "tracked": s["tracked"],
                                   "readers": [{"path": p, "mode": "reads, writes" if m == "rw" else "reads"}
                                               for p, m in sorted(s["users"].items())][:TOP_FILES * 2],
                                   "tables": sorted({t for p in s["users"] for t in ctx["tables"].get(p, ())})[:20]}
    for x in ext:
        tabs = sorted({t for p in x["files"] for t in ctx["tables"].get(p, ())})[:20]
        nodes.append({"id": x["id"], "label": x["label"], "sub": ("%d tables" % len(tabs)) if tabs else x["sub"],
                      "kind": "store", "group": "dbs"})
    groups = [{"id": "code", "label": "Code that touches data"}]
    if stores:
        groups.append({"id": "files", "label": "Data files"})
    if ext:
        groups.append({"id": "dbs", "label": "Databases"})
    return {"groups": groups, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- flows

def _participant(ctx, ref):
    """(node id, label) for a flow participant: a component id, a container id, 'user' or free text."""
    if ref in ("user", "person", "p:user"):
        return "p:user", "User"
    if ref in ctx["by_id"]:
        c = ctx["by_id"][ref]
        return ("x:" if c.get("layer") == "external" else "c:") + ref, c["name"]
    for k in ctx["containers"]:
        if k["id"] == ref:
            return "k:" + ref, k["name"]
    text = str(ref)[:40]
    return "t:" + system._slug(text), text


def _flows(ctx):
    out = []
    raw = ctx["raw"].get("flows")
    for item in (raw if isinstance(raw, list) else [])[:MAX_FLOWS]:
        if not isinstance(item, dict) or not isinstance(item.get("steps"), list):
            continue
        steps, parts = [], collections.OrderedDict()
        for s in item["steps"][:MAX_FLOW_STEPS * 2]:
            if not isinstance(s, dict) or "from" not in s or "to" not in s:
                continue
            a, b = _participant(ctx, s["from"]), _participant(ctx, s["to"])
            parts.setdefault(a[0], a[1])
            parts.setdefault(b[0], b[1])
            steps.append({"from": a[0], "to": b[0], "label": str(s.get("label") or "")[:60],
                          "reply": bool(s.get("reply"))})
        if steps:
            out.append({"id": system._slug(str(item.get("id") or item.get("name") or "flow")),
                        "name": str(item.get("name") or item.get("id") or "Flow")[:60],
                        "notes": str(item.get("notes") or "")[:300], "derived": False,
                        "participants": [{"id": k, "label": v} for k, v in parts.items()], "steps": steps})
    out.extend(_derived_flows(ctx, MAX_FLOWS - len(out)))
    return out


def _derived_flows(ctx, room):
    """One flow per entry component: the user starts it, then the heaviest import edges, depth first."""
    if room <= 0:
        return []
    adj = collections.defaultdict(list)
    for e in ctx["comp_edges"].values():
        if e["from"] not in ctx["aux"] and e["to"] not in ctx["aux"]:
            adj[e["from"]].append(e)
    for k in adj:
        adj[k].sort(key=lambda e: (-e["count"], e["to"]))
    out = []
    starts = [c for c in ctx["comps"] if c["id"] not in ctx["aux"] and c.get("entries") and adj.get(c["id"])]
    starts.sort(key=lambda c: (-len(adj[c["id"]]), c["id"]))
    for c in starts[:min(room, 4)]:
        entry = c["entries"][0]
        verb = "opens " if entry.endswith(".html") else "runs "
        steps = [{"from": "p:user", "to": "c:" + c["id"], "label": verb + entry.rsplit("/", 1)[-1], "reply": False}]
        parts = collections.OrderedDict([("p:user", "User"), ("c:" + c["id"], c["name"])])
        seen = {c["id"]}

        def walk(cid, depth):
            for e in adj.get(cid, [])[:3]:
                if len(steps) >= MAX_FLOW_STEPS or len(parts) >= 7 and ("c:" + e["to"]) not in parts:
                    return
                if e["to"] in seen:
                    continue
                seen.add(e["to"])
                parts.setdefault("c:" + e["to"], ctx["by_id"][e["to"]]["name"])
                steps.append({"from": "c:" + cid, "to": "c:" + e["to"], "label": e["label"][:60], "reply": False})
                if depth < 3:
                    walk(e["to"], depth + 1)
        walk(c["id"], 0)
        if len(steps) > 1:
            out.append({"id": "auto-" + c["id"], "name": "From " + entry, "derived": True,
                        "notes": "Derived from imports: who calls whom, starting at " + entry + ".",
                        "participants": [{"id": k, "label": v} for k, v in parts.items()], "steps": steps})
    return out


# ---------------------------------------------------------------- details and activity

def _component_details(ctx, assigned):
    for c in ctx["comps"]:
        paths = assigned.get(c["id"], [])
        deps = [{"id": "c:" + e["to"], "label": ctx["by_id"][e["to"]]["name"], "count": e["count"],
                 "note": e["label"]} for e in ctx["comp_edges"].values() if e["from"] == c["id"]]
        used = [{"id": "c:" + e["from"], "label": ctx["by_id"][e["from"]]["name"], "count": e["count"],
                 "note": e["label"]} for e in ctx["comp_edges"].values() if e["to"] == c["id"]]
        langs = collections.Counter(system._language([p]) for p in paths if system._language([p]))
        stores = sorted({name for name, users in ctx["stores"].items() for p in users if ctx["owner"].get(p) ==
                         c["id"]})[:12]
        ctx["details"]["c:" + c["id"]] = {
            "kind": "component", "title": c["name"], "layer": c.get("layer"), "type": c.get("kind"),
            "language": c.get("language"), "notes": c.get("notes") or "", "entries": c.get("entries") or [],
            "globs": c.get("files") or [], "fileCount": len(paths),
            "lines": sum(ctx["lines"].get(p, 0) for p in paths), "languages": dict(langs.most_common(4)),
            "dependsOn": sorted(deps, key=lambda d: -d["count"]), "usedBy": sorted(used, key=lambda d: -d["count"]),
            "stores": stores, "_paths": paths}


def _with_activity(base, commits, jobs, mapped):
    """Copy of the cached base with commits per file, recent commits and jobs per component (cheap, per request)."""
    details = {k: dict(v) for k, v in base["details"].items()}
    per_file = collections.Counter()
    for cm in commits:
        per_file.update(cm.get("files") or [])
    jobs_by_task = collections.defaultdict(list)
    for j in jobs:
        if isinstance(j, dict) and j.get("task"):
            jobs_by_task[j["task"]].append(j)
    heat = {c["id"]: c.get("heat") or {} for c in mapped.get("components", []) if isinstance(c, dict)}
    for key, d in details.items():
        if d.get("kind") == "module":
            d["files"] = [dict(f, commits=per_file.get(f["path"], 0)) for f in d["files"]]
        if d.get("kind") != "component":
            continue
        paths = d.pop("_paths", [])
        mine = set(paths)
        ranked = sorted(paths, key=lambda p: (-per_file.get(p, 0), -base_lines(base, p), p))[:TOP_FILES]
        d["files"] = [{"path": p, "lines": base_lines(base, p), "commits": per_file.get(p, 0)} for p in ranked]
        recent = [cm for cm in commits if mine & set(cm.get("files") or [])]
        d["commits"] = [{"sha": cm["sha"][:7], "subject": cm["subject"][:100], "at": cm["at"]} for cm in recent[:6]]
        d["commits30"] = len(recent)
        tasks = []
        for cm in recent:
            for t in cm.get("tasks") or []:
                if t not in tasks:
                    tasks.append(t)
        d["tasks"] = tasks[:12]
        js = [j for t in tasks for j in jobs_by_task.get(t, [])]
        js.sort(key=lambda j: (j.get("status") != "running", str(j.get("started") or "")), reverse=False)
        running = [j for j in js if j.get("status") == "running"]
        rest = sorted([j for j in js if j.get("status") != "running"], key=lambda j: str(j.get("started") or ""),
                      reverse=True)
        d["jobs"] = [{"id": j.get("id"), "task": j.get("task"), "model": j.get("model"), "status": j.get("status"),
                      "title": str(j.get("title") or "")[:80], "started": j.get("started")}
                     for j in (running + rest)[:6]]
        d["heat"] = heat.get(key[2:], {})
    views = base["views"]
    return {"views": views, "flows": base["flows"], "details": details, "stats": base["stats"]}


def base_lines(base, path):
    return base.get("_lines", {}).get(path, 0)
