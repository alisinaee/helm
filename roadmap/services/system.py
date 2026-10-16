"""System map A1: load and validate the optional docs/system.json, or build an automatic baseline from the repo tree.

Sources, in order: docs/system.json (hand or agent kept, version 1), else the baseline. The baseline lists the tracked
files (git ls-files, or a plain walk outside git), makes one component per top-level dir (a dir with several packages
is split into them when it holds at least half the files), at most 24 cards (the smallest are merged into "misc"),
and reads only the names of entry points plus the "bin" paths of a root package.json. The baseline is cached by the
HEAD sha (no sha, no cache). system.json is read on every call (it is small).

Source values: "baseline" (no usable file), "file" (system.json used, every file matched, nothing dropped), "merged"
(system.json used, but some entries were dropped or some files only fall into auto "other" components).

Rules: the project root is canonical and every path read is inside it; symlinks are refused; system.json is capped at
256 KB; git runs only through roadmap.services.git (argv list, no shell). A bad system.json never raises: a broken
file gives the baseline plus a warning, and a bad entry is dropped with a warning. Files are only named here, never
read, except system.json and a root package.json. Glob syntax: "*" and "?" stay inside one path segment, "**" crosses
segments, and "dir/**" matches everything below dir but not dir itself.
"""

import collections
import copy
import functools
import json
import os
import re
import stat
import threading

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import git

SPEC_VERSION = 1
SYSTEM_FILE = "system.json"
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 20000
MAX_CARDS = 24
MAX_DECLARED = 100
MAX_ENTRIES = 10
CACHE_MAX = 16
KINDS = ("module", "store", "tool", "agent", "service")
EDGE_KINDS = ("call", "data", "event")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
ID_RE = re.compile(r"[a-z0-9-]{1,40}")
LAYER_RE = re.compile(r"[a-z0-9-]{1,24}")
LANGUAGES = {"py": "Python", "js": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript", "ts": "TypeScript",
             "tsx": "TypeScript", "html": "HTML", "css": "CSS", "sh": "Shell", "bash": "Shell", "zsh": "Shell",
             "go": "Go", "rs": "Rust", "rb": "Ruby", "java": "Java", "swift": "Swift", "kt": "Kotlin", "c": "C",
             "h": "C", "cpp": "C++"}
ENTRY_NAMES = {"Makefile", "pyproject.toml", "package.json", "Dockerfile"}
ENTRY_BASENAMES = {"__main__.py", "index.html", "Dockerfile"}
BASE_LAYER_ORDER = ("code", "cli", "tests", "docs", "config")

_CACHE = collections.OrderedDict()
_LOCK = threading.Lock()


class _Bad(Exception):
    """The whole system.json is unusable: the baseline is used and this text becomes a warning."""


class _Drop(Exception):
    """One entry of system.json is unusable: it is skipped and this text becomes a warning."""


class _Refuse(Exception):
    """A path that is not allowed to be read (symlink, outside the project, not a plain file)."""


def load(project_root, use_cache=True):
    """The system map for one project folder. Returns a dict with source, warnings, layers, components, edges,
    sha, fileCount and truncated. Never raises for a bad system.json; raises RoadmapError only for a path that is
    not an absolute folder."""
    root = _root(project_root)
    scan = _scan(root, use_cache)
    warnings = list(scan["warnings"])
    try:
        declared = _read_declared(root)
    except _Bad as err:
        warnings.append("system.json: " + str(err))
        declared = None
    except _Refuse as err:
        warnings.append("system.json: " + str(err))
        declared = None
    if declared is None:
        specs, layers, edges = copy.deepcopy(scan["specs"]), list(scan["layers"]), []
        source = "baseline"
    else:
        specs, layers, edges, dropped = declared
        warnings.extend(dropped)
        specs, layers = _with_others(specs, layers, scan["files"])
        source = "file" if not dropped and len(specs) == len(declared[0]) else "merged"
    comps = _materialize(specs, scan["files"], scan["bins"])
    return {"source": source, "warnings": warnings, "layers": layers, "components": comps, "edges": edges,
            "sha": scan["sha"], "fileCount": len(scan["files"]), "truncated": scan["truncated"]}


def assign_files(paths, components):
    """Map each path to the first component whose glob matches it. Returns (dict id -> [paths], [unmatched paths]).
    Components are dicts with "id" and "files" (a list of globs). Used by the heat and the detail views."""
    compiled = [(comp["id"], [_glob_re(g) for g in comp.get("files", [])]) for comp in components]
    out = {comp["id"]: [] for comp in components}
    unmatched = []
    for path in paths:
        for cid, regexes in compiled:
            if any(rx.match(path) for rx in regexes):
                out[cid].append(path)
                break
        else:
            unmatched.append(path)
    return out, unmatched


def valid_glob(pattern):
    """True for a relative glob we accept: a plain string, no absolute start, no '..' segment, no control characters."""
    return _plain(pattern, allow_glob=True)


def _root(project_root):
    if not project_root or not os.path.isabs(str(project_root)):
        raise RoadmapError("usage", "project path must be absolute", EXIT_USAGE)
    real = os.path.realpath(project_root)
    if not os.path.isdir(real):
        raise RoadmapError("not_found", "project folder not found", EXIT_USAGE)
    return real


def _plain(text, allow_glob=False):
    if not isinstance(text, str) or not text or len(text) > 200:
        return False
    if any(ch in text for ch in "\0\n\r\\") or text.startswith(("/", "-")):
        return False
    if any(part in ("..", "") for part in text.split("/")):
        return False
    return allow_glob or "*" not in text


@functools.lru_cache(maxsize=512)
def _glob_re(pattern):
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        ch = pattern[i]
        out.append("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _scan(root, use_cache):
    """The file list, sha, baseline specs and package bins. Cached by (root, HEAD sha) when there is a sha."""
    sha = _head_sha(root)
    key = (root, sha)
    if use_cache and sha:
        with _LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key]
    files, truncated, warnings = _list_files(root, sha)
    bins = _package_bins(root, files)
    specs, layers = _baseline_specs(files)
    result = {"sha": sha, "files": files, "truncated": truncated, "warnings": warnings, "bins": bins,
              "specs": specs, "layers": layers}
    if use_cache and sha:
        with _LOCK:
            _CACHE[key] = result
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
    return result


def _head_sha(root):
    try:
        git.repo_root(root)
        text = git.run(root, ["rev-parse", "HEAD"]).strip()
        return git.valid_sha(text) if text else None
    except RoadmapError:
        return None


def _list_files(root, sha):
    """Tracked files when root is its own git repo, else a walk. Symlinks and skipped dirs are left out."""
    names = None
    if sha:
        try:
            names = [n for n in git.run(root, ["ls-files", "-z"]).split("\0") if n]
        except RoadmapError:
            names = None
    if names is None:
        names = _walk(root)
    files = []
    truncated = False
    for name in sorted(set(names)):
        if not _plain(name, allow_glob=True) or any(p in SKIP_DIRS for p in name.split("/")[:-1]):
            continue
        if os.path.islink(os.path.join(root, name)):
            continue
        if len(files) >= MAX_FILES:
            truncated = True
            break
        files.append(name)
    warnings = ["file list capped at %d files; the map covers the first %d" % (MAX_FILES, MAX_FILES)] \
        if truncated else []
    return files, truncated, warnings


def _walk(root):
    names = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                             and not os.path.islink(os.path.join(dirpath, d)))
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            names.append(rel)
            if len(names) > MAX_FILES:
                return names
    return names


def _read_confined(root, rel, limit=MAX_FILE_BYTES):
    """The bytes of one file inside root, or None when it is missing. Refuses a symlink on any part of the path and
    anything that resolves outside root. Never reads past limit."""
    cur = root
    parts = rel.split("/")
    for part in parts[:-1]:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise _Refuse("refused: a folder on the path is a symlink")
    path = os.path.join(root, rel)
    if os.path.islink(path):
        raise _Refuse("refused: the file is a symlink")
    if not os.path.exists(path):
        return None
    real = os.path.realpath(path)
    if not real.startswith(root + os.sep):
        raise _Refuse("refused: the file is outside the project")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise _Refuse("refused: the file cannot be opened")
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise _Refuse("refused: not a plain file")
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise _Bad("file is larger than %d KB" % (limit // 1024))
    return data


def _package_bins(root, files):
    """The bin paths of a root package.json that are real files of the project (at most MAX_ENTRIES)."""
    if "package.json" not in files:
        return []
    try:
        data = json.loads((_read_confined(root, "package.json") or b"{}").decode("utf-8", "replace"))
    except (ValueError, _Refuse, _Bad):
        return []
    bins = data.get("bin") if isinstance(data, dict) else None
    values = [bins] if isinstance(bins, str) else list(bins.values()) if isinstance(bins, dict) else []
    known = set(files)
    out = []
    for value in values:
        if isinstance(value, str) and _plain(value) and value in known and value not in out:
            out.append(value)
    return out[:MAX_ENTRIES]


def _layer_for(top):
    if top in ("docs", "doc"):
        return "docs"
    if top in ("tests", "test", "fixtures"):
        return "tests"
    if top in ("bin", "tools", "scripts"):
        return "cli"
    return "code"


def _kind_for(top):
    if top in ("bin", "tools", "scripts"):
        return "tool"
    if top in ("docs", "doc", "fixtures"):
        return "store"
    return "module"


def _baseline_specs(files):
    """Component specs (id, name, layer, kind, files globs) from the tree. At most MAX_CARDS; the smallest are
    merged into one 'misc' component."""
    visible = [f for f in files if not any(p in SKIP_DIRS for p in f.split("/")[:-1])]
    total = len(visible)
    tops = collections.Counter(f.split("/")[0] for f in visible if "/" in f)
    specs = []
    if any("/" not in f for f in visible):
        specs.append({"id": "root-files", "name": "Root files", "layer": "config", "kind": "module",
                      "files": ["*"], "_top": None})
    for top in sorted(tops):
        direct = [f for f in visible if f.startswith(top + "/") and f.count("/") == 1]
        subdirs = sorted({f.split("/")[1] for f in visible if f.startswith(top + "/") and f.count("/") >= 2})
        layer, kind = _layer_for(top), _kind_for(top)
        if len(subdirs) >= 2 and tops[top] * 2 >= total:
            if direct:
                specs.append({"id": _slug(top), "name": top, "layer": layer, "kind": kind,
                              "files": [top + "/*"], "_top": top})
            for sub in subdirs:
                specs.append({"id": _slug(top + "/" + sub), "name": top + "/" + sub, "layer": layer, "kind": kind,
                              "files": [top + "/" + sub + "/**"], "_top": top})
        else:
            specs.append({"id": _slug(top), "name": top, "layer": layer, "kind": kind,
                          "files": [top + "/**"], "_top": top})
    specs = _unique_ids(specs)
    if len(specs) > MAX_CARDS:
        counts, _ = assign_files(visible, specs)
        ranked = sorted(specs, key=lambda s: (-len(counts[s["id"]]), s["id"]))
        keep_ids = {s["id"] for s in ranked[:MAX_CARDS - 1]}
        globs = [g for s in ranked[MAX_CARDS - 1:] for g in s["files"]]
        specs = [s for s in specs if s["id"] in keep_ids]
        specs.append({"id": "misc", "name": "Other files", "layer": "config", "kind": "module", "files": globs,
                      "_top": None})
    for spec in specs:
        spec.pop("_top", None)
    layers = [name for name in BASE_LAYER_ORDER if any(s["layer"] == name for s in specs)]
    return specs, layers


def _slug(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return slug or "root"


def _unique_ids(specs):
    seen = set()
    for spec in specs:
        base = spec["id"]
        cid, n = base, 2
        while cid in seen:
            cid = (base[:36] + "-" + str(n))
            n += 1
        spec["id"] = cid
        seen.add(cid)
    return specs


def _with_others(specs, layers, files):
    """Add one auto 'other' component per top-level dir (and one for root files) for files no declared glob matches."""
    _, unmatched = assign_files(files, specs)
    if not unmatched:
        return specs, layers
    tops = sorted({f.split("/")[0] if "/" in f else "" for f in unmatched})
    extra = []
    taken = {s["id"] for s in specs}
    for top in tops:
        base = "other-" + _slug(top) if top else "other-root"
        cid, n = base[:40], 2
        while cid in taken:
            cid = base[:36] + "-" + str(n)
            n += 1
        taken.add(cid)
        glob = top + "/**" if top else "*"
        extra.append({"id": cid, "name": "Other (" + (top or "root") + ")", "layer": "other", "kind": "module",
                      "files": [glob], "notes": "auto: files not matched by docs/system.json"})
    return specs + extra, (layers if "other" in layers else layers + ["other"])


def _materialize(specs, files, bins):
    """Full component dicts with file counts, language and entry points, from the file list."""
    assigned, _ = assign_files(files, specs)
    out = []
    for spec in specs:
        mine = assigned[spec["id"]]
        mine_set = set(mine)
        entries = []
        if spec.get("entry") and spec["entry"] in mine_set:
            entries.append(spec["entry"])
        for path in mine:
            base = path.rsplit("/", 1)[-1]
            if base in ENTRY_BASENAMES or path in ENTRY_NAMES or path.startswith("bin/"):
                entries.append(path)
        entries.extend(b for b in bins if b in mine_set)
        entries = list(dict.fromkeys(entries))[:MAX_ENTRIES]
        out.append({"id": spec["id"], "name": spec.get("name") or spec["id"], "layer": spec["layer"],
                    "kind": spec.get("kind", "module"), "files": list(spec.get("files", [])),
                    "entry": entries[0] if entries else None, "entries": entries,
                    "notes": spec.get("notes"), "owner": spec.get("owner"),
                    "language": _language(mine), "fileCount": len(mine)})
    return out


def _language(paths):
    counts = collections.Counter()
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        lang = LANGUAGES.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
        if lang:
            counts[lang] += 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _read_declared(root):
    """The validated system.json as (specs, layers, edges, dropped_warnings), or None when there is no file."""
    raw = _read_confined(root, "docs/" + SYSTEM_FILE)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as err:
        raise _Bad("not valid JSON (" + getattr(err, "msg", "bad text") + ")")
    return _parse_declared(data)


def _parse_declared(data):
    if not isinstance(data, dict):
        raise _Bad("the top level must be an object")
    if data.get("version") != SPEC_VERSION:
        raise _Bad("unsupported version (need version 1)")
    comps_raw = data.get("components", [])
    edges_raw = data.get("edges", [])
    if not isinstance(comps_raw, list) or not isinstance(edges_raw, list):
        raise _Bad("components and edges must be lists")
    layers = data.get("layers")
    if layers is None:
        layers = []
        for item in comps_raw:
            name = item.get("layer") if isinstance(item, dict) else None
            if isinstance(name, str) and LAYER_RE.fullmatch(name) and name not in layers:
                layers.append(name)
    elif not isinstance(layers, list) or not all(isinstance(x, str) and LAYER_RE.fullmatch(x) for x in layers) \
            or len(set(layers)) != len(layers):
        raise _Bad("layers must be a list of unique short names")
    dropped = []
    specs = []
    seen = set()
    for index, item in enumerate(comps_raw):
        if len(specs) >= MAX_DECLARED:
            dropped.append("system.json: more than %d components; the rest are skipped" % MAX_DECLARED)
            break
        try:
            spec = _check_component(item, layers, seen, dropped, index)
        except _Drop as err:
            dropped.append("system.json: components[%d] %s" % (index, err))
            continue
        seen.add(spec["id"])
        specs.append(spec)
    edges = []
    for index, item in enumerate(edges_raw):
        try:
            edges.append(_check_edge(item, seen))
        except _Drop as err:
            dropped.append("system.json: edges[%d] %s" % (index, err))
    return specs, layers, edges, dropped


def _check_component(item, layers, seen, dropped, index):
    if not isinstance(item, dict):
        raise _Drop("is not an object")
    cid = item.get("id")
    if not isinstance(cid, str) or not ID_RE.fullmatch(cid):
        raise _Drop("id must be 1-40 of a-z, 0-9 or '-'")
    if cid in seen:
        raise _Drop("id '" + cid + "' is used twice")
    name = item.get("name", cid)
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise _Drop("name must be text of 1-80 characters")
    layer = item.get("layer")
    if layer not in layers:
        raise _Drop("layer " + repr(layer)[:40] + " is not in layers")
    kind = item.get("kind", "module")
    if kind not in KINDS:
        raise _Drop("kind must be one of " + ", ".join(KINDS))
    files_raw = item.get("files", [])
    if not isinstance(files_raw, list):
        raise _Drop("files must be a list of globs")
    files = [g for g in files_raw if valid_glob(g)]
    if len(files) != len(files_raw):
        dropped.append("system.json: components[%d] refused %d file glob(s) outside the project or malformed"
                       % (index, len(files_raw) - len(files)))
    notes = item.get("notes")
    notes = notes[:500] if isinstance(notes, str) else None
    owner = item.get("owner")
    owner = owner[:40] if isinstance(owner, str) else None
    entry = item.get("entry")
    if entry is not None and not (isinstance(entry, str) and _plain(entry)):
        dropped.append("system.json: components[%d] entry refused (must be a plain path inside the project)" % index)
        entry = None
    spec = {"id": cid, "name": name.strip(), "layer": layer, "kind": kind, "files": files, "notes": notes,
            "owner": owner, "entry": entry}
    return spec


def _check_edge(item, ids):
    if not isinstance(item, dict):
        raise _Drop("is not an object")
    src, dst = item.get("from"), item.get("to")
    if not (isinstance(src, str) and isinstance(dst, str)) or src not in ids or dst not in ids:
        raise _Drop("from and to must be ids of declared components")
    kind = item.get("kind", "call")
    if kind not in EDGE_KINDS:
        kind = "call"
    label = item.get("label")
    label = label[:120] if isinstance(label, str) else None
    return {"from": src, "to": dst, "label": label, "kind": kind}
