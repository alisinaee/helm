"""Tests for A1: the system map service. A fixture repo is built in a temp folder (git argv lists only).

Covers: the baseline from the tree, a valid docs/system.json, a broken one (baseline plus a warning, never a crash),
a partly broken one (merged, bad entries dropped), path confinement (symlinks refused), the HEAD-sha cache, a folder
outside git, the file cap, the glob rules and the assignment helper.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from roadmap.errors import RoadmapError
from roadmap.services import system


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env={"PATH": os.environ.get("PATH", ""), "HOME": cwd, "GIT_CONFIG_NOSYSTEM": "1"})


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class SystemFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sysmap-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "proj")
        os.makedirs(self.root)
        system._CACHE.clear()
        self.addCleanup(system._CACHE.clear)
        _write(self.root, "roadmap/services/jobs.py", "x = 1\n")
        _write(self.root, "roadmap/services/hooks.py", "x = 2\n")
        _write(self.root, "roadmap/commands/cmd.py", "x = 3\n")
        _write(self.root, "roadmap/commands/extra.py", "x = 5\n")
        _write(self.root, "roadmap/services/extra.py", "x = 6\n")
        for name in ("a", "b", "c", "d"):
            _write(self.root, "roadmap/services/more_%s.py" % name, "x = 7\n")
        _write(self.root, "web/js/b.js", "2;\n")
        _write(self.root, "roadmap/__main__.py", "x = 4\n")
        _write(self.root, "web/js/app.js", "1;\n")
        _write(self.root, "web/index.html", "<html></html>\n")
        _write(self.root, "bin/tool.sh", "echo\n")
        _write(self.root, "docs/NOTES.md", "# notes\n")
        _write(self.root, "tests/unit/test_x.py", "pass\n")
        _write(self.root, "README.md", "hi\n")
        _write(self.root, "Makefile", "check:\n")
        _write(self.root, "package.json", json.dumps({"bin": {"rm": "bin/tool.sh"}}))

    def git_repo(self):
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")
        _git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "init")

    def system_json(self, data):
        text = data if isinstance(data, str) else json.dumps(data)
        _write(self.root, "docs/system.json", text)

    def comps(self, result):
        return {c["id"]: c for c in result["components"]}


class BaselineTests(SystemFixture):
    def test_baseline_from_git_tree(self):
        self.git_repo()
        out = system.load(self.root)
        self.assertEqual(out["source"], "baseline")
        self.assertEqual(out["warnings"], [])
        self.assertIsNotNone(out["sha"])
        comps = self.comps(out)
        # roadmap holds most files and has two packages: it is split into its packages
        self.assertEqual(comps["roadmap-services"]["fileCount"], 7)
        self.assertEqual(comps["roadmap-commands"]["fileCount"], 2)
        self.assertEqual(comps["roadmap-services"]["language"], "Python")
        self.assertEqual(comps["roadmap"]["files"], ["roadmap/*"])
        self.assertEqual(comps["roadmap"]["fileCount"], 1)
        self.assertEqual(comps["web"]["fileCount"], 3)
        self.assertEqual(comps["web"]["language"], "JavaScript")
        self.assertEqual(comps["web"]["layer"], "code")
        self.assertEqual(comps["docs"]["layer"], "docs")
        self.assertEqual(comps["docs"]["kind"], "store")
        self.assertEqual(comps["tests"]["layer"], "tests")
        self.assertEqual(comps["bin"]["kind"], "tool")
        self.assertEqual(comps["bin"]["layer"], "cli")
        self.assertEqual(comps["root-files"]["fileCount"], 3)

    def test_entry_points_from_names_and_package_bin(self):
        self.git_repo()
        comps = self.comps(system.load(self.root))
        self.assertEqual(comps["roadmap"]["entry"], "roadmap/__main__.py")
        self.assertEqual(comps["web"]["entry"], "web/index.html")
        self.assertIn("bin/tool.sh", comps["bin"]["entries"])
        self.assertIn("Makefile", comps["root-files"]["entries"])
        self.assertIn("package.json", comps["root-files"]["entries"])

    def test_package_json_bin_is_validated_against_files(self):
        self.git_repo()
        _write(self.root, "package.json", json.dumps({"bin": {"rm": "../../etc/passwd", "ok": "bin/tool.sh"}}))
        comps = self.comps(system.load(self.root, use_cache=False))
        self.assertIn("bin/tool.sh", comps["bin"]["entries"])
        self.assertNotIn("../../etc/passwd", str(comps))

    def test_not_a_repo_still_gets_a_walk_baseline(self):
        out = system.load(self.root)
        self.assertIsNone(out["sha"])
        self.assertEqual(out["source"], "baseline")
        self.assertIn("web", self.comps(out))

    def test_relative_or_missing_path_is_refused(self):
        with self.assertRaises(RoadmapError):
            system.load("relative/path")
        with self.assertRaises(RoadmapError):
            system.load(os.path.join(self.tmp, "nope"))

    def test_card_cap_merges_the_smallest(self):
        for i in range(30):
            _write(self.root, "pkg%02d/mod.py" % i, "x = %d\n" % i)
        out = system.load(self.root)
        self.assertLessEqual(len(out["components"]), system.MAX_CARDS)
        self.assertIn("misc", self.comps(out))


class DeclaredTests(SystemFixture):
    GOOD = {
        "version": 1,
        "layers": ["ui", "service", "data"],
        "components": [
            {"id": "web-ui", "name": "Web UI", "layer": "ui", "kind": "module", "files": ["web/**"],
             "entry": "web/index.html", "notes": "SPA"},
            {"id": "api", "name": "API", "layer": "service", "files": ["roadmap/services/**"], "owner": "head"},
            {"id": "store", "name": "Store", "layer": "data", "kind": "store", "files": ["docs/**"]},
        ],
        "edges": [{"from": "web-ui", "to": "api", "label": "GET snapshot", "kind": "call"}],
    }

    def test_valid_file_used_and_unmatched_files_get_other(self):
        self.git_repo()
        self.system_json(self.GOOD)
        out = system.load(self.root)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(out["source"], "merged")  # unmatched files fall into auto other components
        comps = self.comps(out)
        self.assertEqual(comps["web-ui"]["fileCount"], 3)
        self.assertEqual(comps["api"]["fileCount"], 7)
        self.assertEqual(comps["api"]["owner"], "head")
        self.assertEqual(comps["web-ui"]["entry"], "web/index.html")
        self.assertIn("other-roadmap", comps)
        self.assertIn("other-root", comps)
        self.assertEqual(out["edges"], [{"from": "web-ui", "to": "api", "label": "GET snapshot", "kind": "call"}])
        self.assertIn("other", out["layers"])

    def test_fully_matched_file_is_source_file(self):
        self.git_repo()
        data = dict(self.GOOD)
        data["components"] = self.GOOD["components"] + [
            {"id": "rest", "name": "Rest", "layer": "data", "files": ["**"]}]
        self.system_json(data)
        out = system.load(self.root)
        self.assertEqual(out["source"], "file")
        self.assertEqual(out["warnings"], [])

    def test_broken_json_gives_baseline_and_warning(self):
        self.git_repo()
        self.system_json("{not json")
        out = system.load(self.root)
        self.assertEqual(out["source"], "baseline")
        self.assertEqual(len(out["warnings"]), 1)
        self.assertTrue(out["warnings"][0].startswith("system.json:"))
        self.assertIn("web", self.comps(out))

    def test_wrong_version_and_bad_shape_give_baseline(self):
        self.git_repo()
        for bad in ({"version": 2, "components": []}, [1, 2], {"version": 1, "components": "x"},
                    {"version": 1, "layers": "ui"}):
            self.system_json(bad)
            out = system.load(self.root, use_cache=False)
            self.assertEqual(out["source"], "baseline", bad)
            self.assertTrue(out["warnings"][0].startswith("system.json:"), bad)

    def test_bad_entries_are_dropped_and_rest_kept(self):
        self.git_repo()
        data = json.loads(json.dumps(self.GOOD))
        data["components"].append({"id": "Bad Id", "name": "x", "layer": "ui"})
        data["components"].append({"id": "api", "name": "dup", "layer": "service"})
        data["components"].append({"id": "lost", "name": "x", "layer": "nowhere"})
        data["components"][0]["files"] = ["web/**", "../../etc/passwd", "/abs/**"]
        data["components"][0]["entry"] = "../escape.html"
        data["edges"].append({"from": "web-ui", "to": "ghost"})
        data["edges"].append({"from": ["x"], "to": "api"})
        self.system_json(data)
        out = system.load(self.root)
        self.assertEqual(out["source"], "merged")
        ids = self.comps(out).keys()
        self.assertIn("web-ui", ids)
        self.assertIn("api", ids)
        self.assertNotIn("lost", ids)
        self.assertEqual(len(out["edges"]), 1)
        self.assertEqual(self.comps(out)["web-ui"]["files"], ["web/**"])
        self.assertEqual(self.comps(out)["web-ui"]["entry"], "web/index.html")
        self.assertGreaterEqual(len(out["warnings"]), 7)
        self.assertNotIn("../escape.html", str(out["components"]))

    def test_symlinked_system_json_is_refused_and_not_read(self):
        self.git_repo()
        outside = os.path.join(self.tmp, "outside.json")
        with open(outside, "w", encoding="utf-8") as fh:
            json.dump(self.GOOD, fh)
        os.makedirs(os.path.join(self.root, "docs"), exist_ok=True)
        os.symlink(outside, os.path.join(self.root, "docs", "system.json"))
        out = system.load(self.root)
        self.assertEqual(out["source"], "baseline")
        self.assertIn("refused", out["warnings"][0])
        self.assertNotIn("GET snapshot", str(out))

    def test_symlinked_docs_folder_is_refused(self):
        self.git_repo()
        other = os.path.join(self.tmp, "elsewhere")
        os.makedirs(other)
        with open(os.path.join(other, "system.json"), "w", encoding="utf-8") as fh:
            json.dump(self.GOOD, fh)
        shutil.rmtree(os.path.join(self.root, "docs"))
        os.symlink(other, os.path.join(self.root, "docs"))
        out = system.load(self.root)
        self.assertEqual(out["source"], "baseline")
        self.assertIn("refused", out["warnings"][0])

    def test_oversized_file_is_refused(self):
        self.git_repo()
        self.system_json("{" + " " * (system.MAX_FILE_BYTES + 10) + "}")
        out = system.load(self.root)
        self.assertEqual(out["source"], "baseline")
        self.assertIn("larger", out["warnings"][0])


class CacheTests(SystemFixture):
    def test_cache_keyed_by_head_sha(self):
        self.git_repo()
        first = system.load(self.root)
        self.assertEqual(len(system._CACHE), 1)
        second = system.load(self.root)
        self.assertEqual(first["components"], second["components"])
        self.assertEqual(len(system._CACHE), 1)
        _write(self.root, "newpkg/a.py", "x = 1\n")
        _git(self.root, "add", "-A")
        _git(self.root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "second")
        third = system.load(self.root)
        self.assertNotEqual(first["sha"], third["sha"])
        self.assertIn("newpkg", self.comps(third))
        self.assertEqual(len(system._CACHE), 2)

    def test_use_cache_false_does_not_store(self):
        self.git_repo()
        system.load(self.root, use_cache=False)
        self.assertEqual(len(system._CACHE), 0)

    def test_system_json_is_read_every_call(self):
        self.git_repo()
        system.load(self.root)
        self.system_json(DeclaredTests.GOOD)
        self.assertEqual(system.load(self.root)["source"], "merged")


class CapTests(SystemFixture):
    def test_file_cap_marks_truncated(self):
        old = system.MAX_FILES
        system.MAX_FILES = 3
        self.addCleanup(setattr, system, "MAX_FILES", old)
        out = system.load(self.root)
        self.assertTrue(out["truncated"])
        self.assertEqual(out["fileCount"], 3)
        self.assertIn("capped", " ".join(out["warnings"]))


class HelperTests(unittest.TestCase):
    def test_glob_rules(self):
        rx = system._glob_re
        self.assertTrue(rx("web/**").match("web/js/app.js"))
        self.assertFalse(rx("web/**").match("web"))
        self.assertFalse(rx("web/*").match("web/js/app.js"))
        self.assertTrue(rx("web/*").match("web/app.js"))
        self.assertTrue(rx("a/**/b.py").match("a/b.py"))
        self.assertTrue(rx("a/**/b.py").match("a/x/y/b.py"))
        self.assertTrue(rx("**").match("anything/at/all"))
        self.assertTrue(rx("*").match("README.md"))
        self.assertFalse(rx("*").match("a/README.md"))

    def test_valid_glob_refuses_escape_and_control(self):
        self.assertTrue(system.valid_glob("web/**"))
        for bad in ("", "../x", "/abs", "a/../b", "x\0y", "a\\b", "a//b", None, 5):
            self.assertFalse(system.valid_glob(bad), bad)

    def test_assign_first_match_wins(self):
        comps = [{"id": "a", "files": ["src/**"]}, {"id": "b", "files": ["**"]}]
        out, unmatched = system.assign_files(["src/x.py", "README.md"], comps)
        self.assertEqual(out["a"], ["src/x.py"])
        self.assertEqual(out["b"], ["README.md"])
        self.assertEqual(unmatched, [])


if __name__ == "__main__":
    unittest.main()
