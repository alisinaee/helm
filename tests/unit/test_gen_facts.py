"""tools/gen_facts.py: FACTS.md names every top-level command, is deterministic apart from the date line, and stays under
the size cap. The generator runs with a temporary ROADMAP_HOME and never touches the real state."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(REPO, "tools", "gen_facts.py")
SHIM = os.path.join(REPO, "bin", "roadmap")
MAX_BYTES = 60 * 1024


def _env(home):
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    env["ROADMAP_HOME"] = home
    return env


def _generate(home, out):
    proc = subprocess.run([sys.executable, TOOL, "--out", out], cwd=REPO, env=_env(home),
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)
    with open(out, encoding="utf-8") as fh:
        return fh.read()


def _top_level_commands(home):
    proc = subprocess.run([SHIM, "--help"], cwd=REPO, env=_env(home), capture_output=True, text=True, timeout=60)
    names, in_section = [], False
    for line in proc.stdout.splitlines():
        if line.startswith("positional arguments:"):
            in_section = True
        elif in_section and line.startswith("options:"):
            break
        else:
            match = re.match(r"^    (\S+)\s{2,}\S", line)
            if in_section and match:
                names.append(match.group(1))
    return names


class GenFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rb-genfacts-")
        cls.home = os.path.join(cls.tmp, "home")
        cls.first = _generate(cls.home, os.path.join(cls.tmp, "a.md"))
        cls.second = _generate(cls.home, os.path.join(cls.tmp, "b.md"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_top_level_command_has_a_help_section(self):
        names = _top_level_commands(self.home)
        self.assertTrue(names, "bin/roadmap --help listed no commands")
        for name in names:
            self.assertIn(f"### roadmap {name}\n", self.first, name)

    def test_deterministic_apart_from_date_line(self):
        def strip_date(text):
            return [line for line in text.splitlines() if not line.startswith("Generated ")]
        self.assertEqual(strip_date(self.first), strip_date(self.second))

    def test_size_cap(self):
        self.assertLessEqual(len(self.first.encode("utf-8")), MAX_BYTES)

    def test_sections_present(self):
        for heading in ("## 2. HTTP routes", "## 3. /cmd ops", "## 4. Size and cap constants", "## 5. Module tree",
                        "## 6. Data files", "## 7. Last 30 commit subjects", "## 8. UI rules"):
            self.assertIn(heading, self.first)
        self.assertIn("`/api/v1/cmd`", self.first)


if __name__ == "__main__":
    unittest.main()
