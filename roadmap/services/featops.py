"""Feature ops (WP52): the registry entries for the planner's features, run through commands.run like the other ops.

feature.add, feature.set, feature.link, feature.unlink, feature.accept and feature.rm are public. feature.restore is
internal: undo uses it to put back a removed feature. Each op returns (data, summary, inverse), so commands.run logs
one activity line and stores the inverse in undo.jsonl.

feature.accept is for the person only. It is refused when the source is agent, when the shell has CLAUDECODE set
(agentguard.is_agent), or when the source is phone; the refusal names "ask the person" as the next step.
cmdops imports this module, so the ops are registered whenever the registry loads.
"""

from roadmap.core import planfmt
from roadmap.core.parsers import FEAT_ID_RE
from roadmap.errors import EXIT_CONFLICT, RoadmapError
from roadmap.services import agentguard, commands, features, records

PRIOS = (1, 2, 3)
ACC_MAX = 160
TITLE_MAX = 80
LINK_MAX = 3
NEXT_LIST = "roadmap feature list"


# ---------------------------------------------------------------- argument checks

def _feat_id(a, key="id"):
    value = commands._text(a.get(key))
    if not FEAT_ID_RE.match(value):
        raise commands._usage("feature id '" + value + "' must look like F3 (allowed: F1 to F99)", NEXT_LIST)
    return value


def _opt_phase(a, key="phase"):
    value = commands._text(a.get(key))
    if value == "":
        return None
    if not planfmt.PHASE_ID_RE.match(value):
        raise commands._usage("phase '" + value + "' must be a phase id or empty (allowed: letters and digits)",
                              "roadmap task list")
    return value


def _opt_parent(a, key="parent"):
    value = commands._text(a.get(key))
    if value == "":
        return None
    if not FEAT_ID_RE.match(value):
        raise commands._usage("parent '" + value + "' must look like F3 or be empty (allowed: feature id)", NEXT_LIST)
    return value


def _prio(value):
    if isinstance(value, bool) or value not in PRIOS:
        raise commands._usage("prio must be 1, 2 or 3", NEXT_LIST)
    return value


def _acc(a):
    text = " ".join(commands._text(a.get("acc")).split())
    if len(text) > ACC_MAX:
        raise commands._usage("acc is " + str(len(text)) + " characters; the limit is " + str(ACC_MAX), NEXT_LIST)
    return text


def _title(a):
    return records.text_field(a.get("title"), "title", TITLE_MAX)


def _check_add(a):
    return {"title": _title(a), "acc": _acc(a), "prio": _prio(a.get("prio", 2)),
            "phase": _opt_phase(a), "parent": _opt_parent(a)}


def _h_add(data_dir, a, now):
    row = features.add(data_dir, a["title"], a["acc"], a["prio"], a["phase"], a["parent"])
    inverse = {"op": "feature.rm", "args": {"id": row["id"]}}
    return row, row["id"] + " added: " + row["title"], inverse


def _check_set(a):
    changes = {}
    if "title" in a:
        changes["title"] = _title(a)
    if "acc" in a:
        changes["acc"] = _acc(a)
    if "prio" in a:
        changes["prio"] = _prio(a["prio"])
    if "phase" in a:
        changes["phase"] = _opt_phase(a)
    if "parent" in a:
        changes["parent"] = _opt_parent(a)
    if "hold" in a:
        changes["hold"] = commands._opt_bool(a, "hold", False)
    if not changes:
        raise commands._usage("feature set needs at least one of title, acc, prio, phase, parent, hold", NEXT_LIST)
    return {"id": _feat_id(a), "changes": changes}


def _h_set(data_dir, a, now):
    prior = features.set_fields(data_dir, a["id"], a["changes"])
    summary = a["id"] + " set " + ", ".join(sorted(a["changes"]))
    return {"id": a["id"], "changed": sorted(a["changes"])}, summary, {"op": "feature.set",
                                                                        "args": dict(prior, id=a["id"])}


def _feat_list(a, key="feats"):
    value = a.get(key)
    if not isinstance(value, (list, tuple)) or not value or len(value) > LINK_MAX:
        raise commands._usage(key + " must be a list of 1 to " + str(LINK_MAX) + " feature ids", NEXT_LIST)
    out = []
    for item in value:
        text = "" if item is None else str(item).strip()
        if not FEAT_ID_RE.match(text):
            raise commands._usage("feature id '" + text + "' must look like F3", NEXT_LIST)
        if text not in out:
            out.append(text)
    return out


def _check_link(a):
    return {"task": commands._id(a, "task", "task id"), "feats": _feat_list(a)}


def _h_link(data_dir, a, now):
    result = features.link(data_dir, a["task"], a["feats"])
    inverse = {"op": "feature.unlink", "args": {"task": a["task"], "feats": result["added"]}} if result["added"] \
        else None
    return result, "link " + " ".join(a["feats"]) + " to " + a["task"], inverse


def _check_unlink(a):
    return {"task": commands._id(a, "task", "task id"), "feats": _feat_list(a)}


def _h_unlink(data_dir, a, now):
    result = features.unlink(data_dir, a["task"], a["feats"])
    inverse = {"op": "feature.link", "args": {"task": a["task"], "feats": result["removed"]}} if result["removed"] \
        else None
    return result, "unlink " + " ".join(a["feats"]) + " from " + a["task"], inverse


def _check_accept(a):
    on = commands._opt_bool(a, "on", True)
    confirm = commands._opt_bool(a, "confirm", False)
    return {"id": _feat_id(a), "on": True if on is None else on, "confirm": confirm is True,
            "date": features.check_date(a.get("date"))}


def _refuse_accept():
    """Acceptance is the person's. Agents (CLAUDECODE or source agent) and the phone are refused."""
    source = commands.current_source()
    if source == "phone" or agentguard.is_agent(source):
        raise RoadmapError("agent_refused", "feature accept is for the person; an agent or the phone cannot accept a "
                           "feature", EXIT_CONFLICT, next="ask the person")


def _h_accept(data_dir, a, now):
    _refuse_accept()
    result, prior = features.accept(data_dir, a["id"], a["on"], date=a["date"], confirm=a["confirm"], now=now)
    if a["on"]:
        summary = a["id"] + " accepted " + str(result["accepted"])
    else:
        summary = a["id"] + " acceptance cleared"
    inverse = {"op": "feature.accept", "args": {"id": a["id"], "on": prior is not None, "date": prior,
                                                "confirm": True}}
    return result, summary, inverse


def _check_id(a):
    return {"id": _feat_id(a)}


def _h_rm(data_dir, a, now):
    removed = features.remove(data_dir, a["id"])
    return {"id": a["id"], "removed": True}, a["id"] + " removed", {"op": "feature.restore",
                                                                    "args": {"feature": removed}}


def _check_restore(a):
    feature = a.get("feature")
    if not isinstance(feature, dict) or not FEAT_ID_RE.match(str(feature.get("id", ""))):
        raise commands._usage("feature restore needs a feature record")
    return {"feature": feature}


def _h_restore(data_dir, a, now):
    features.restore(data_dir, a["feature"])
    return {"id": a["feature"]["id"], "restored": True}, a["feature"]["id"] + " restored", None


# ---------------------------------------------------------------- registration

def _register(name, check, handler, public=True):
    commands.OPS[name] = commands._Op(check, handler, public=public)


_register("feature.add", _check_add, _h_add)
_register("feature.set", _check_set, _h_set)
_register("feature.link", _check_link, _h_link)
_register("feature.unlink", _check_unlink, _h_unlink)
_register("feature.accept", _check_accept, _h_accept)
_register("feature.rm", _check_id, _h_rm)
_register("feature.restore", _check_restore, _h_restore, public=False)
