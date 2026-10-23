"""R10.32: measured tokens per job from subagent transcripts: hook capture, backfill, weighted units."""

import json
import os

from roadmap.core.parsers import parse_jobs, weighted_units
from roadmap.services import jobs, jobtokens
from tests.unit.test_hooks import HookTestCase
from tests.unit.test_jobs_support import run_cli


def line(mid, model, i, o, cr, cw, ts="2026-10-16T10:00:00Z"):
    usage = {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"id": mid, "model": model, "usage": usage}}) + "\n"


def write_transcript(path, lines, meta=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "timestamp": "2026-10-16T09:59:00Z"}) + "\n")
        fh.write("not json\n")
        fh.writelines(lines)
    if meta:
        with open(path[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh)


class UsageTests(HookTestCase):
    def test_read_usage_dedupes_repeated_message_and_skips_junk(self):
        path = os.path.join(self.tmp, "a.jsonl")
        write_transcript(path, [line("m1", "claude-sonnet-5-5", 2, 10, 100, 50), line("m1", "claude-sonnet-5-5", 2, 30,
            100, 50),
                                line("m2", "claude-sonnet-5-5", 1, 5, 200, 0)])
        self.assertEqual(jobtokens.read_usage(path),
                         {"in": 3, "out": 35, "cacheRead": 300, "cacheWrite": 50, "model": "sonnet"})

    def test_read_usage_missing_or_empty_is_none(self):
        self.assertIsNone(jobtokens.read_usage(os.path.join(self.tmp, "nope.jsonl")))

    def test_weighted_units(self):
        t = {"in": 10, "out": 2, "cacheRead": 100, "cacheWrite": 4, "model": "opus"}
        self.assertEqual(weighted_units(t), 5 * (10 + 10 + 5 + 10))
        self.assertEqual(weighted_units(dict(t, model="haiku")), 35)
        self.assertEqual(weighted_units(dict(t, model="sonnet")), 105)

    def test_parse_jobs_exposes_tokens_and_units(self):
        text = json.dumps({"jobs": [{"id": "j1", "title": "t", "model": "haiku", "status": "done",
                                      "started": "2026-10-16T10:00:00+00:00",
                                      "tokens": {"in": 1, "out": 1, "cacheRead": 0, "cacheWrite": 0,
                                          "model": "haiku"}}]})
        rows, _ = parse_jobs(text, __import__("datetime").datetime.now().astimezone())
        self.assertEqual(rows[0]["units"], 6)
        self.assertEqual(rows[0]["tokens"]["out"], 1)

    def test_subagent_stop_stores_tokens_on_the_job(self):
        self.agent_start()
        session = os.path.join(self.tmp, "sess")
        write_transcript(os.path.join(session, "subagents", "agent-a1b2c3d4e5.jsonl"),
                         [line("m1", "claude-haiku-5", 4, 8, 16, 32)])
        self.fire(hook_event_name="SubagentStop", agent_id="a1b2c3d4e5", transcript_path=session + ".jsonl")
        job = self.read_jobs()[0]
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["tokens"], {"in": 4, "out": 8, "cacheRead": 16, "cacheWrite": 32, "model": "haiku"})

    def test_subagent_stop_without_transcript_is_fail_open(self):
        self.agent_start()
        self.fire(hook_event_name="SubagentStop", agent_id="a1b2c3d4e5", transcript_path="/nonexistent/s.jsonl")
        job = self.read_jobs()[0]
        self.assertEqual(job["status"], "done")
        self.assertNotIn("tokens", job)

    def test_backfill_matches_by_description_and_cli(self):
        self.agent_start(description="Parser fix P0.8", agent_id="aaaaaaaaaa")
        self.fire(hook_event_name="SubagentStop", agent_id="aaaaaaaaaa")
        root = os.path.join(self.tmp, "claude")
        write_transcript(os.path.join(root, "s1", "subagents", "agent-aaaaaaaaaa.jsonl"),
                         [line("m1", "claude-sonnet-5-5", 1, 2, 3, 4)],
                         {"description": "Parser fix P0.8", "model": "sonnet"})
        write_transcript(os.path.join(root, "s1", "subagents", "agent-bbbbbbbbbb.jsonl"),
                         [line("m1", "claude-sonnet-5-5", 9, 9, 9, 9)], {"description": "Other work",
                             "model": "sonnet"})
        data_dir = jobs.data_dir_of(jobs.resolve_project("demo"))
        dry = jobtokens.backfill(data_dir, root, dry_run=True)
        self.assertEqual(dry["matched"], 1)
        self.assertNotIn("tokens", self.read_jobs()[0])
        code, out, _ = run_cli(["tokens", "backfill", "--root", root, "--project", "demo", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["matched"], 1)
        self.assertEqual(self.read_jobs()[0]["tokens"]["cacheWrite"], 4)
        self.assertEqual(jobtokens.backfill(data_dir, root)["matched"], 0)  # already filled
