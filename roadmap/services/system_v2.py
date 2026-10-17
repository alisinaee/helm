"""System v2 backend (docs/SYSTEM-V2-SPEC.md sections 2 and 3): extends the arch dict system_arch.analyze() returns.

extend(project_root, mapped, arch, data_dir, commits) adds
- board / work / progress / refId to arch["details"]["c:<id>"] and (as the union) to the "k:<id>" container details,
  from system_tasks.bind;
- arch["diagrams"]: classes, deployment, usecases, activity (system_behave) and states, er (system_data). The modules
  are imported lazily and each call is guarded: a missing module or any exception only adds a warning;
- arch["catalog"]: one row per view id with family, label, score 0..100, available, reason, derived.
Diagram results are cached by (root, HEAD sha, docs/system.json mtime). Same file list and caps as system_arch.
"""

import collections
import importlib
import json
import os
import threading

from roadmap.errors import RoadmapError
from roadmap.services import system, system_arch, system_tasks

MAX_FILES = 4000
CACHE_MAX = 16
SCORE_PER_ITEM = 4
DECLARED_BONUS = 40
FAMILIES = ("structure", "behaviour", "data")
# id -> (family, label, docs/system.json keys that declare it)
VIEWS = collections.OrderedDict([
    ("context", ("structure", "Context", ("external",))),
    ("containers", ("structure", "Containers", ("containers",))),
    ("components", ("structure", "Components", ("components", "edges"))),
    ("modules", ("structure", "Modules", ())),
    ("layers", ("structure", "Layers", ("layers",))),
    ("classes", ("structure", "Classes", ("classes",))),
    ("deployment", ("structure", "Deployment", ("deployment",))),
    ("usecases", ("behaviour", "Use cases", ("usecases",))),
    ("flows", ("behaviour", "Flows", ("flows",))),
    ("activity", ("behaviour", "Activity", ("activities",))),
    ("states", ("behaviour", "States", ("machines",))),
    ("data", ("data", "Data flow", ())),
    ("er", ("data", "ER", ("entities",))),
])
# diagram id -> (module, function)
DIAGRAMS = (("classes", "system_behave", "classes"), ("deployment", "system_behave", "deployment"),
            ("usecases", "system_behave", "usecases"), ("activity", "system_behave", "activity"),
            ("states", "system_data", "states"), ("er", "system_data", "er"))

_CACHE = collections.OrderedDict()
_LOCK = threading.Lock()


def extend(project_root, mapped, arch, data_dir, commits=()):
    """Add the v2 keys to arch (mutated and returned). Raises nothing for a bad diagram module; a RoadmapError for a
    bad project folder."""
    if not isinstance(arch, dict):
        return arch
    root = system._root(project_root)
    warnings = arch.setdefault("warnings", [])
    _bind_tasks(root, mapped, arch, data_dir, commits, warnings)
    scan = system._scan(root, True)
    diagrams, dwarn = _diagrams(root, scan, mapped)
    arch["diagrams"] = diagrams
    warnings.extend(dwarn)
    arch["catalog"] = _catalog(arch, diagrams, dwarn, _declared(root), (mapped or {}).get("views") or [])
    return arch


# ---------------------------------------------------------------- tasks

def _bind_tasks(root, mapped, arch, data_dir, commits, warnings):
    try:
        from roadmap.services import tasks as tasks_svc
        from roadmap.services import work as work_svc
        task_list = [t for t in tasks_svc.load(data_dir).get("tasks", []) if isinstance(t, dict)]
        try:
            work = work_svc.list_views(data_dir)
        except (RoadmapError, OSError, ValueError, KeyError):
            work = []
        bound = system_tasks.bind(mapped, list(commits or ()), task_list, work, system_arch._declared_raw(root))
    except Exception as err:   # one failure never loses the map
        warnings.append("system tasks unavailable: " + str(err)[:120])
        return
    details = arch.get("details") or {}
    for cid, row in bound.items():
        entry = details.get("c:" + cid)
        if isinstance(entry, dict):
            entry.update(board=row["board"], work=row["work"], progress=row["progress"], refId=cid)
    for key, entry in details.items():
        if not (key.startswith("k:") and isinstance(entry, dict)):
            continue
        parts = [bound[c["id"][2:]] for c in entry.get("components") or []
                 if isinstance(c, dict) and str(c.get("id", ""))[2:] in bound]
        merged = system_tasks.union(parts)
        entry.update(board=merged["board"], work=merged["work"], progress=merged["progress"], refId=key[2:])


# ---------------------------------------------------------------- diagrams

def _mtime(root):
    try:
        return os.stat(os.path.join(root, "docs", system.SYSTEM_FILE)).st_mtime_ns
    except OSError:
        return 0


def _declared(root):
    return system_arch._declared_raw(root)


def _diagrams(root, scan, mapped):
    """(diagram results by id, warnings). Cached by (root, sha, system.json mtime); no sha, no cache."""
    sha = scan.get("sha")
    key = (root, sha, _mtime(root))
    if sha:
        with _LOCK:
            hit = _CACHE.get(key)
            if hit is not None:
                _CACHE.move_to_end(key)
                return dict(hit[0]), list(hit[1])
    files = list(scan.get("files") or [])[:MAX_FILES]
    out, warnings = {}, []
    modules = {}
    for did, mod_name, fn_name in DIAGRAMS:
        try:
            if mod_name not in modules:
                modules[mod_name] = importlib.import_module("roadmap.services." + mod_name)
            result = getattr(modules[mod_name], fn_name)(root, files, mapped)
            if result is not None:
                out[did] = result
        except ImportError:
            warnings.append("diagram %s unavailable: module %s is not installed" % (did, mod_name))
        except Exception as err:
            warnings.append("diagram %s failed: %s" % (did, str(err)[:120]))
    if sha:
        with _LOCK:
            _CACHE[key] = (dict(out), list(warnings))
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
    return out, warnings


# ---------------------------------------------------------------- catalog

def _count(view):
    if not isinstance(view, dict):
        return len(view) if isinstance(view, list) else 0
    total = 0
    for key, value in view.items():
        if key in ("groups",):
            continue
        if isinstance(value, list):
            total += len(value)
            if key == "items":   # activity steps / state transitions count too
                total += sum(len(i.get("steps") or []) + len(i.get("transitions") or []) for i in value
                             if isinstance(i, dict))
    return total


def _size(vid, arch, diagrams):
    if vid == "flows":
        return len(arch.get("flows") or [])
    if vid in diagrams:
        return _count(diagrams[vid])
    return _count((arch.get("views") or {}).get(vid))


def _catalog(arch, diagrams, dwarn, raw, pinned):
    rows = []
    for vid, (family, label, keys) in VIEWS.items():
        size = _size(vid, arch, diagrams)
        declared = any(raw.get(k) for k in keys)
        derived_view = vid in dict((d[0], d) for d in DIAGRAMS)
        score = min(100, size * SCORE_PER_ITEM + (DECLARED_BONUS if declared and size else 0))
        if size:
            reason = "declared in docs/system.json" if declared else "derived from the code"
        elif derived_view:
            failed = [w for w in dwarn if w.startswith("diagram " + vid + " ")]
            reason = failed[0] if failed else "nothing found in the code"
        else:
            reason = "nothing to show"
        rows.append({"id": vid, "family": family, "label": label, "score": score, "available": size > 0,
                     "reason": reason, "derived": not declared})
    pin = {v: i for i, v in enumerate(v for v in pinned if v in VIEWS)}
    rows.sort(key=lambda r: (0 if r["id"] in pin else 1, pin.get(r["id"], 0), FAMILIES.index(r["family"]),
                             -r["score"], r["id"]))
    return rows
