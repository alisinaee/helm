"""System v2 data diagrams: ER / EER entities and state machines derived from the tracked files (stdlib only).

er(root, files, mapped)     -> {"entities": [...], "relations": [...]}
states(root, files, mapped) -> {"items": [...]}
Both read files confined to root (no symlinks, at most MAX_FILE_BYTES each, at most MAX_FILES files) and merge the
optional docs/system.json keys "entities" and "machines" over the derived items by id."""
import ast
import json
import os
import re
import stat

MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 4000
MAX_ENTITIES = 60
MAX_RELATIONS = 150
MAX_ATTRS = 30
MAX_MACHINES = 12
MAX_TEXT = 80
SOURCE_RANK = {"sql": 0, "schema": 1, "dataclass": 2, "json": 3}
CARDS = ("1-1", "1-n", "n-n")


def _read(root, rel):
    """Text of one tracked file inside root, or None (missing, symlink, outside root, too big, unreadable)."""
    try:
        cur = root
        parts = rel.split("/")
        if not rel or rel.startswith("/") or ".." in parts:
            return None
        for part in parts[:-1]:
            cur = os.path.join(cur, part)
            if os.path.islink(cur):
                return None
        path = os.path.join(root, rel)
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        if not os.path.realpath(path).startswith(os.path.realpath(root) + os.sep):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return None
            data = fh.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return None
        return data.decode("utf-8", "replace")
    except (OSError, ValueError):
        return None


SKIP_DIRS = {"tests", "test", "fixtures", "__tests__", "examples"}
SKIP_NAME_RE = re.compile(r"^test_.*\.py$|_test\.py$|\.(?:test|spec)\.[cm]?[jt]sx?$")


def _is_fixture(rel):
    parts = rel.split("/")
    return any(p in SKIP_DIRS for p in parts[:-1]) or bool(SKIP_NAME_RE.search(parts[-1]))


def _paths(files):
    out = []
    for rel in files or []:
        if isinstance(rel, str) and rel not in out and not _is_fixture(rel):
            out.append(rel)
        if len(out) >= MAX_FILES:
            break
    return out


def _ext(rel):
    name = rel.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _stem(rel):
    name = rel.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _text(value, limit=MAX_TEXT):
    return value[:limit] if isinstance(value, str) else ""


def _overrides(root, key):
    raw = _read(root, "docs/system.json")
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    items = data.get(key) if isinstance(data, dict) else None
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


# ----------------------------------------------------------------------------------------------- ER: SQL

CREATE_RE = re.compile(r"CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.`\"\[\]]+)\s*\(", re.I)


def _clean_name(raw):
    return raw.strip().strip('`"[]').split(".")[-1].strip('`"[]')


def _split_top(body):
    parts, depth, cur, quote = [], 0, [], None
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _paren_body(text, start):
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    return text[start:i - 1] if depth == 0 else None


def _sql_entities(rel, text):
    out = []
    for match in CREATE_RE.finditer(text):
        body = _paren_body(text, match.end())
        name = _clean_name(match.group(1))
        if body is None or not name:
            continue
        attrs, pks, fks = [], set(), []
        for part in _split_top(body):
            part = " ".join(part.split())
            if not part:
                continue
            up = part.upper()
            cols = lambda s: [_clean_name(c) for c in s.split(",") if c.strip()]
            if up.startswith("CONSTRAINT "):
                part = part.split(" ", 2)[2] if part.count(" ") >= 2 else ""
                up = part.upper()
            if up.startswith("PRIMARY KEY"):
                found = re.search(r"\(([^)]*)\)", part)
                pks.update(cols(found.group(1)) if found else [])
                continue
            if up.startswith("FOREIGN KEY"):
                found = re.search(r"\(([^)]*)\)\s*REFERENCES\s+([\w.`\"\[\]]+)", part, re.I)
                if found:
                    for col in cols(found.group(1)):
                        fks.append((col, _clean_name(found.group(2))))
                continue
            if up.startswith(("UNIQUE", "CHECK", "INDEX", "KEY ", "FULLTEXT")) or not part:
                continue
            bits = part.split(" ", 2)
            col = _clean_name(bits[0])
            if not col:
                continue
            typ = bits[1].split("(")[0].lower() if len(bits) > 1 else ""
            if "PRIMARY KEY" in up:
                pks.add(col)
            ref = re.search(r"REFERENCES\s+([\w.`\"\[\]]+)", part, re.I)
            if ref:
                fks.append((col, _clean_name(ref.group(1))))
            attrs.append({"name": col, "type": typ, "pk": False, "fk": False, "many": False})
        fkcols = {c for c, _ in fks}
        for attr in attrs:
            attr["pk"] = attr["name"] in pks
            attr["fk"] = attr["name"] in fkcols
        out.append({"label": name, "source": "sql", "file": rel, "attrs": attrs, "parent": None,
                    "_links": [(t, c, "1-n", False, True) for c, t in fks]})
    return out


# ----------------------------------------------------------------------------------- ER: JSON Schema

def _ref_name(ref):
    if not isinstance(ref, str):
        return ""
    tail = ref.split("#")[-1].rstrip("/").rsplit("/", 1)[-1] if "#" in ref and ref.split("#")[-1] else ref
    return _stem(tail.rsplit("/", 1)[-1])


def _schema_type(spec):
    if not isinstance(spec, dict):
        return "", False, ""
    ref = spec.get("$ref")
    if ref:
        return _ref_name(ref), False, _ref_name(ref)
    typ = spec.get("type")
    if isinstance(typ, list):
        typ = "|".join(str(x) for x in typ)
    if typ == "array":
        inner = spec.get("items") if isinstance(spec.get("items"), dict) else {}
        itype, _, iref = _schema_type(inner)
        return (itype or "array"), True, iref
    return str(typ or ""), False, ""


def _schema_entity(label, node, rel):
    attrs, links, parent = [], [], None
    sources = [node]
    for sub in node.get("allOf") or []:
        if not isinstance(sub, dict):
            continue
        if sub.get("$ref") and parent is None:
            parent = _ref_name(sub["$ref"])
        else:
            sources.append(sub)
    required = set()
    for src in sources:
        req = src.get("required")
        if isinstance(req, list):
            required.update(x for x in req if isinstance(x, str))
        props = src.get("properties")
        if not isinstance(props, dict):
            continue
        for name, spec in props.items():
            typ, many, ref = _schema_type(spec)
            attrs.append({"name": _text(str(name)), "type": _text(typ), "pk": str(name) == "id",
                          "fk": bool(ref), "many": many})
            if ref:
                links.append((ref, str(name), "1-n" if many else "1-1", False, False))
    return {"label": label, "source": "schema", "file": rel, "attrs": attrs, "parent": parent, "_links": links}


def _schema_entities(rel, data):
    if not isinstance(data, dict) or not ("$schema" in data or "properties" in data):
        return None
    out = []
    title = data.get("title") if isinstance(data.get("title"), str) else ""
    if data.get("properties") or data.get("allOf"):
        out.append(_schema_entity(_text(title) or _stem(rel), data, rel))
    for key in ("definitions", "$defs"):
        defs = data.get(key)
        if isinstance(defs, dict):
            for name, node in defs.items():
                if isinstance(node, dict) and (node.get("properties") or node.get("allOf")):
                    out.append(_schema_entity(_text(str(name)), node, rel))
    return out


# --------------------------------------------------------------------------------- ER: JSON stores

def _guess(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "null"


def _records_entity(label, records, rel):
    cols = {}
    for rec in records[:50]:
        if not isinstance(rec, dict):
            continue
        for key, val in rec.items():
            typ = _guess(val)
            if key not in cols or cols[key] == "null":
                cols[key] = typ
    if not cols:
        return None
    attrs = [{"name": _text(str(k)), "type": t, "pk": k == "id", "fk": False, "many": t == "list"}
             for k, t in cols.items()]
    return {"label": _text(label), "source": "json", "file": rel, "attrs": attrs, "parent": None, "_links": []}


def _store_entities(rel, text):
    ext = _ext(rel)
    if ext == "jsonl":
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
            if len(records) >= 50:
                break
        ent = _records_entity(_stem(rel), records, rel) if records else None
        return [ent] if ent else []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []
    if isinstance(data, list):
        ent = _records_entity(_stem(rel), [x for x in data if isinstance(x, dict)], rel)
        return [ent] if ent else []
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list) and val and all(isinstance(x, dict) for x in val[:50]):
                ent = _records_entity(str(key), val, rel)
                if ent:
                    out.append(ent)
    return out


# ------------------------------------------------------------------------------------ ER: dataclasses

SIMPLE_BASES = {"object", "NamedTuple", "TypedDict", "Generic", "Protocol", "ABC", "Enum"}


def _ann_text(node):
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _dataclass_entities(rel, text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [_ann_text(b).split("[")[0].split(".")[-1] for b in node.bases]
        deco = [_ann_text(d.func if isinstance(d, ast.Call) else d).split(".")[-1] for d in node.decorator_list]
        if "dataclass" not in deco and not any(b in ("NamedTuple", "TypedDict") for b in bases):
            continue
        attrs = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                ann = _ann_text(item.annotation)
                many = bool(re.match(r"(?:typing\.)?(?:[Ll]ist|[Ss]et|[Tt]uple|[Ss]equence|frozenset)\b", ann))
                attrs.append({"name": item.target.id, "type": _text(ann), "pk": item.target.id == "id",
                              "fk": False, "many": many})
        parent = next((b for b in bases if b and b not in SIMPLE_BASES), None)
        out.append({"label": node.name, "source": "dataclass", "file": rel, "attrs": attrs, "parent": parent,
                    "_links": []})
    return out


# --------------------------------------------------------------------------------------- ER: assembly

def _singular(word):
    word = word.lower().replace("_", "").replace("-", "")
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("sses") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _derive_entities(root, paths):
    found = []
    for rel in paths:
        ext = _ext(rel)
        if ext not in ("sql", "py", "js", "ts", "mjs", "cjs", "jsx", "tsx", "json", "jsonl"):
            continue
        if rel.rsplit("/", 1)[-1] in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock"):
            continue
        text = _read(root, rel)
        if text is None:
            continue
        if ext in ("sql", "py", "js", "ts", "mjs", "cjs", "jsx", "tsx") and re.search(r"CREATE\s+(?:\w+\s+)*TABLE",
            text, re.I):
            found.extend(_sql_entities(rel, text))
        if ext == "py":
            found.extend(_dataclass_entities(rel, text))
        elif ext in ("json", "jsonl"):
            schema = None
            if ext == "json":
                try:
                    schema = _schema_entities(rel, json.loads(text))
                except ValueError:
                    schema = None
            if schema is not None:
                found.extend(schema)
            else:
                found.extend(_store_entities(rel, text))
    return found


def _override_entity(item):
    label = _text(item.get("label") or item.get("name") or str(item.get("id", "")).replace("e:", "", 1))
    if not label:
        return None
    attrs = []
    for a in item.get("attrs") or []:
        if isinstance(a, str):
            a = {"name": a}
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            attrs.append({"name": _text(a["name"]), "type": _text(a.get("type")), "pk": bool(a.get("pk")),
                          "fk": bool(a.get("fk")), "many": bool(a.get("many"))})
    links = []
    for r in item.get("relations") or []:
        if isinstance(r, dict) and isinstance(r.get("to"), str):
            card = r.get("card") if r.get("card") in CARDS else "1-n"
            links.append((_text(r["to"]), _text(r.get("label")), card, False, False))
    ident = item.get("id") if isinstance(item.get("id"), str) and item["id"] else label
    return {"id": ident if ident.startswith("e:") else "e:" + ident, "label": label,
            "source": item.get("source") if item.get("source") in SOURCE_RANK else "json",
            "file": _text(item.get("file"), 200), "attrs": attrs[:MAX_ATTRS],
            "parent": item.get("parent") if isinstance(item.get("parent"), str) else None, "_links": links}


def er(root, files, mapped=None):
    root = os.path.realpath(root)
    derived = _derive_entities(root, _paths(files))
    best = {}
    order = []
    for ent in derived:
        key = ent["label"].lower()
        if key not in best:
            order.append(key)
            best[key] = ent
        elif SOURCE_RANK[ent["source"]] < SOURCE_RANK[best[key]["source"]]:
            best[key] = ent
    ents = [best[k] for k in order]
    for ent in ents:
        ent["id"] = "e:" + ent["label"]
    byid = {e["id"]: e for e in ents}
    for item in _overrides(root, "entities"):
        ov = _override_entity(item)
        if not ov:
            continue
        if ov["id"] in byid:
            old = byid[ov["id"]]
            ents[ents.index(old)] = ov
        else:
            ents.append(ov)
        byid[ov["id"]] = ov
    ents.sort(key=lambda e: SOURCE_RANK[e["source"]])
    ents = ents[:MAX_ENTITIES]
    byid = {e["id"]: e for e in ents}
    bylabel = {e["label"].lower(): e["id"] for e in ents}
    bynorm = {}
    for e in ents:
        bynorm.setdefault(_singular(e["label"]), e["id"])

    def resolve(name):
        if not name:
            return None
        if name in byid:
            return name
        return bylabel.get(name.lower()) or bylabel.get(_stem(name).lower()) or bynorm.get(_singular(name))

    relations, seen = [], set()

    def add(frm, to, label, card, implied):
        key = (frm, to, label)
        if frm and to and key not in seen and len(relations) < MAX_RELATIONS:
            seen.add(key)
            relations.append({"from": frm, "to": to, "label": _text(label), "card": card, "implied": implied})

    for ent in ents:
        ent["attrs"] = ent["attrs"][:MAX_ATTRS]
        if ent["parent"]:
            ent["parent"] = resolve(ent["parent"])
            if ent["parent"] == ent["id"]:
                ent["parent"] = None
        for target, col, card, implied, fk_style in ent.get("_links", []):
            tid = resolve(target)
            if not tid:
                continue
            if fk_style:
                add(tid, ent["id"], col, card, implied)
            else:
                add(ent["id"], tid, col, card, implied)
    for ent in ents:
        linked = {r["label"] for r in relations if r["to"] == ent["id"] or r["from"] == ent["id"]}
        for attr in ent["attrs"]:
            name = attr["name"]
            if name in linked or attr["pk"] or name.lower() == "id":
                continue
            low = name.lower()
            tid = None
            card = "1-n"
            if low.endswith("id") and len(low) > 2 and (low.endswith("_id") or name[-2:] == "Id"):
                tid = resolve(name[:-2].rstrip("_"))
            elif attr["many"] and _singular(name) in bynorm:
                tid, card = bynorm[_singular(name)], "n-n"
            elif _singular(name) in bynorm:
                tid = bynorm[_singular(name)]
            if tid and (tid != ent["id"] or card == "n-n"):
                attr["fk"] = True
                add(tid, ent["id"], name, card, True)
    for ent in ents:
        ent.pop("_links", None)
    return {"entities": ents, "relations": relations}


# ------------------------------------------------------------------------------------------ states

NAME_RE = re.compile(r"STATUS|STATE")
JS_EXTS = ("js", "mjs", "cjs", "ts", "jsx", "tsx")
JS_DECL_RE = re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:Object\.freeze\(\s*)?\[([^\]]*)"
                        r"\]")
JS_STR_RE = re.compile(r"""^\s*(?:'([^']*)'|"([^"]*)"|`([^`$]*)`)\s*$""")


def _valid_states(vals):
    vals = [v for v in vals if v is not None]
    return vals if 2 <= len(vals) <= 12 and len(set(vals)) == len(vals) else None


def _py_const_states(value):
    if isinstance(value, ast.Call) and getattr(value.func, "id", "") in ("frozenset", "set", "tuple", "list") \
            and len(value.args) == 1:
        value = value.args[0]
    if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return None
    vals = []
    for el in value.elts:
        if not (isinstance(el, ast.Constant) and isinstance(el.value, str)):
            return None
        vals.append(el.value)
    return _valid_states(vals)


def _is_status(node):
    if isinstance(node, ast.Name):
        return node.id == "status"
    if isinstance(node, ast.Attribute):
        return node.attr == "status"
    if isinstance(node, ast.Subscript):
        sl = node.slice
        return isinstance(sl, ast.Constant) and sl.value == "status"
    return False


def _const_strs(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        vals = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return vals
    return []


def _py_transitions(tree, states):
    known = set(states)
    pairs = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        conds, sets = [], []
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare) and _is_status(node.left) and len(node.ops) == 1 \
                    and isinstance(node.ops[0], (ast.Eq, ast.In)):
                vals = [v for v in _const_strs(node.comparators[0]) if v in known]
                if vals:
                    conds.append((node.lineno, vals))
            elif isinstance(node, ast.Assign) and any(_is_status(t) for t in node.targets) \
                    and isinstance(node.value, ast.Constant) and node.value.value in known:
                sets.append((node.lineno, node.value.value))
        for line, to in sets:
            before = [c for c in conds if c[0] < line]
            if not before:
                continue
            for frm in max(before, key=lambda c: c[0])[1]:
                if frm != to and (frm, to, fn.name) not in pairs:
                    pairs.append((frm, to, fn.name))
    return pairs


def _chain(states):
    return [(a, b, "") for a, b in zip(states, states[1:])]


def _machine(rel, name, states, pairs):
    guessed = not pairs
    pairs = pairs or _chain(states)
    seen, trans = set(), []
    for frm, to, label in pairs:
        if (frm, to) in seen:
            continue
        seen.add((frm, to))
        trans.append({"from": frm, "to": to, "label": _text(label), "guessed": guessed})
    return {"id": "s:%s:%s" % (rel, name), "name": name, "file": rel, "states": list(states),
            "transitions": trans, "initial": states[0]}


def _py_machines(rel, text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id == tgt.id.upper() and NAME_RE.search(tgt.id):
                sts = _py_const_states(value)
                if sts:
                    out.append(_machine(rel, tgt.id, sts, _py_transitions(tree, sts)))
    return out


def _js_chunks(text):
    starts = [m.start() for m in re.finditer(
        r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b|^[ \t]*(?:export\s+)?(?:const|let)"
        r"\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
        text, re.M)]
    if not starts:
        return [text]
    bounds = starts + [len(text)]
    return [text[bounds[i]:bounds[i + 1]] for i in range(len(starts))]


def _js_transitions(text, states):
    known = set(states)
    pairs = []
    cmp_re = re.compile(r"""\bstatus\s*={2,3}\s*(?:'([^']*)'|"([^"]*)")""")
    set_re = re.compile(r"""\bstatus\s*=(?!=)\s*(?:'([^']*)'|"([^"]*)")""")
    for chunk in _js_chunks(text):
        conds = [(m.start(), m.group(1) or m.group(2)) for m in cmp_re.finditer(chunk)]
        for m in set_re.finditer(chunk):
            to = m.group(1) or m.group(2)
            prev = [c for c in conds if c[0] < m.start() and c[1] in known]
            if to in known and prev:
                frm = prev[-1][1]
                if frm != to and (frm, to, "") not in pairs:
                    pairs.append((frm, to, ""))
    return pairs


def _js_machines(rel, text):
    out = []
    for m in JS_DECL_RE.finditer(text):
        name = m.group(1)
        if name != name.upper() or not NAME_RE.search(name):
            continue
        vals = []
        for piece in m.group(2).split(","):
            if not piece.strip():
                continue
            s = JS_STR_RE.match(piece)
            if not s:
                vals = None
                break
            vals.append(next(g for g in s.groups() if g is not None))
        sts = _valid_states(vals) if vals else None
        if sts:
            out.append(_machine(rel, name, sts, _js_transitions(text, sts)))
    return out


def _override_machine(item):
    sts = [s for s in item.get("states") or [] if isinstance(s, str)][:12]
    name = _text(item.get("name") or str(item.get("id", "")))
    if not sts or not name:
        return None
    ident = item.get("id") if isinstance(item.get("id"), str) and item["id"] else "s:%s" % name
    if not ident.startswith("s:"):
        ident = "s:" + ident
    trans = []
    for t in item.get("transitions") or []:
        if isinstance(t, dict) and t.get("from") in sts and t.get("to") in sts:
            trans.append({"from": t["from"], "to": t["to"], "label": _text(t.get("label")),
                          "guessed": bool(t.get("guessed"))})
    if not trans:
        trans = [{"from": a, "to": b, "label": "", "guessed": True} for a, b in zip(sts, sts[1:])]
    initial = item.get("initial") if item.get("initial") in sts else sts[0]
    return {"id": ident, "name": name, "file": _text(item.get("file"), 200), "states": sts,
            "transitions": trans, "initial": initial}


def states(root, files, mapped=None):
    root = os.path.realpath(root)
    items = []
    for rel in _paths(files):
        ext = _ext(rel)
        if ext != "py" and ext not in JS_EXTS:
            continue
        text = _read(root, rel)
        if text is None or not re.search(r"STATUS|STATE", text):
            continue
        items.extend(_py_machines(rel, text) if ext == "py" else _js_machines(rel, text))
    for item in _overrides(root, "machines"):
        ov = _override_machine(item)
        if not ov:
            continue
        for i, old in enumerate(items):
            if old["id"] == ov["id"]:
                items[i] = ov
                break
        else:
            items.append(ov)
    return {"items": items[:MAX_MACHINES]}
