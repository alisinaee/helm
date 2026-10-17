import json
import os
import shutil
import tempfile
import unittest

from roadmap.services import system_data


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.files = []

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text if isinstance(text, str) else json.dumps(text))
        self.files.append(rel)

    def er(self):
        return system_data.er(self.root, self.files, {})

    def states(self):
        return system_data.states(self.root, self.files, {})

    def ent(self, data, label):
        return next(e for e in data["entities"] if e["label"] == label)


class ErTests(Base):
    def test_sql_fk(self):
        self.put("db/schema.sql", """
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE orders (
              id INTEGER, user_id INTEGER REFERENCES users(id), total REAL,
              PRIMARY KEY (id));
            CREATE TABLE notes (id int, order_id int, FOREIGN KEY (order_id) REFERENCES orders(id));""")
        data = self.er()
        orders = self.ent(data, "orders")
        self.assertEqual(orders["source"], "sql")
        self.assertTrue(orders["id"].startswith("e:"))
        by = {a["name"]: a for a in orders["attrs"]}
        self.assertTrue(by["id"]["pk"])
        self.assertTrue(by["user_id"]["fk"])
        rels = {(r["from"], r["to"], r["implied"]) for r in data["relations"]}
        self.assertIn(("e:users", "e:orders", False), rels)
        self.assertIn(("e:orders", "e:notes", False), rels)

    def test_sql_in_python_string(self):
        self.put("app/db.py", 'SQL = "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT)"\n')
        self.assertEqual(self.ent(self.er(), "jobs")["source"], "sql")

    def test_schema_ref_and_allof(self):
        self.put("schemas/base.json", {"$schema": "x", "title": "Base",
                                       "properties": {"id": {"type": "string"}}})
        self.put("schemas/task.json", {"$schema": "x", "title": "Task",
                                       "allOf": [{"$ref": "base.json"}],
                                       "properties": {"owner": {"$ref": "person.json"},
                                                      "tags": {"type": "array", "items": {"type": "string"}}}})
        self.put("schemas/person.json", {"properties": {"name": {"type": "string"}}})
        data = self.er()
        task = self.ent(data, "Task")
        self.assertEqual(task["parent"], "e:Base")
        self.assertTrue(any(a["name"] == "tags" and a["many"] for a in task["attrs"]))
        self.assertIn({"from": "e:Task", "to": "e:person", "label": "owner", "card": "1-1", "implied": False},
                      data["relations"])

    def test_schema_defs(self):
        self.put("s.json", {"$schema": "x", "$defs": {"Item": {"properties": {"n": {"type": "integer"}}}}})
        self.assertEqual(self.ent(self.er(), "Item")["source"], "schema")

    def test_json_store_implied(self):
        self.put("docs/tasks.json", {"phases": [{"id": "p1", "name": "A"}],
                                     "tasks": [{"id": "t1", "phaseId": "p1", "title": "x", "tags": ["a"]}]})
        self.put("docs/log.jsonl", '{"id": 1, "taskId": "t1"}\n{"id": 2, "taskId": "t1"}\n')
        data = self.er()
        tasks = self.ent(data, "tasks")
        self.assertEqual(tasks["source"], "json")
        self.assertTrue(next(a for a in tasks["attrs"] if a["name"] == "tags")["many"])
        rels = {(r["from"], r["to"], r["label"], r["card"], r["implied"]) for r in data["relations"]}
        self.assertIn(("e:phases", "e:tasks", "phaseId", "1-n", True), rels)
        self.assertIn(("e:tasks", "e:log", "taskId", "1-n", True), rels)

    def test_implied_nn(self):
        self.put("a.json", {"tasks": [{"id": 1}], "people": [{"id": 1, "tasks": [1]}]})
        rels = self.er()["relations"]
        self.assertTrue(any(r["card"] == "n-n" and r["implied"] for r in rels))

    def test_package_lock_skipped(self):
        self.put("package-lock.json", {"packages": [{"a": 1}]})
        self.assertEqual(self.er()["entities"], [])

    def test_dataclass_inheritance(self):
        self.put("m.py", "from dataclasses import dataclass\n@dataclass\nclass A:\n    id: int\n    names: list\n"
                         "@dataclass(frozen=True)\nclass B(A):\n    a_id: int\nclass Plain:\n    x: int\n")
        data = self.er()
        self.assertEqual(self.ent(data, "B")["parent"], "e:A")
        self.assertTrue(self.ent(data, "A")["attrs"][1]["many"])
        self.assertEqual(len([e for e in data["entities"] if e["label"] == "Plain"]), 0)
        self.assertTrue(any(r["label"] == "a_id" and r["implied"] for r in data["relations"]))

    def test_dedupe_prefers_sql(self):
        self.put("a.sql", "CREATE TABLE tasks (id int);")
        self.put("tasks.json", [{"id": 1, "x": 2}])
        data = self.er()
        self.assertEqual([e["source"] for e in data["entities"] if e["label"] == "tasks"], ["sql"])

    def test_override(self):
        self.put("a.sql", "CREATE TABLE tasks (id int);")
        self.put("docs/system.json", {"entities": [
            {"id": "e:tasks", "label": "tasks", "attrs": ["id", {"name": "x", "type": "int"}]},
            {"id": "e:extra", "label": "extra", "attrs": []}]})
        data = self.er()
        self.assertEqual([a["name"] for a in self.ent(data, "tasks")["attrs"]], ["id", "x"])
        self.assertTrue(self.ent(data, "extra"))

    def test_caps(self):
        sql = "".join("CREATE TABLE t%d (%s);\n" % (i, ", ".join("c%d int" % j for j in range(40)))
                      for i in range(70))
        self.put("big.sql", sql)
        data = self.er()
        self.assertEqual(len(data["entities"]), 60)
        self.assertEqual(len(data["entities"][0]["attrs"]), 30)
        many = "".join("CREATE TABLE r%d (id int, %s);\n" % (i, ", ".join("c%d_id int" % j for j in range(5)))
                       for i in range(60))
        self.put("rel.sql", many)
        self.assertLessEqual(len(self.er()["relations"]), 150)

    def test_confinement(self):
        outside = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        with open(os.path.join(outside, "x.sql"), "w") as fh:
            fh.write("CREATE TABLE secret (id int);")
        os.symlink(os.path.join(outside, "x.sql"), os.path.join(self.root, "link.sql"))
        os.symlink(outside, os.path.join(self.root, "dir"))
        self.files += ["link.sql", "dir/x.sql", "../x.sql"]
        self.assertEqual(self.er()["entities"], [])

    def test_big_file_skipped(self):
        self.put("big.sql", "CREATE TABLE a (id int);" + " " * (300 * 1024))
        self.assertEqual(self.er()["entities"], [])


class StatesTests(Base):
    def test_py_real_transition(self):
        self.put("svc.py", 'STATUS = ("todo", "doing", "done")\n'
                           'def start(t):\n    if t["status"] == "todo":\n        t["status"] = "doing"\n'
                           'def finish(t):\n    if t["status"] == "doing":\n        t["status"] = "done"\n')
        item = self.states()["items"][0]
        self.assertEqual(item["id"], "s:svc.py:STATUS")
        self.assertEqual(item["initial"], "todo")
        self.assertEqual({(t["from"], t["to"], t["guessed"]) for t in item["transitions"]},
                         {("todo", "doing", False), ("doing", "done", False)})
        self.assertEqual(item["transitions"][0]["label"], "start")

    def test_py_guessed_chain(self):
        self.put("m.py", 'JOB_STATES = ["a", "b", "c"]\n')
        item = self.states()["items"][0]
        self.assertEqual([(t["from"], t["to"], t["guessed"]) for t in item["transitions"]],
                         [("a", "b", True), ("b", "c", True)])

    def test_py_ignores_bad(self):
        self.put("m.py", 'STATUS = ("only",)\nOTHER = ("a", "b")\nSTATES = ("a", 1)\n')
        self.assertEqual(self.states()["items"], [])

    def test_js_frozen(self):
        self.put("web/s.js", 'export const TASK_STATUS = Object.freeze(["open", "closed"]);\n'
                             'function close(t) { if (t.status === "open") { t.status = "closed"; } }\n')
        item = self.states()["items"][0]
        self.assertEqual(item["states"], ["open", "closed"])
        self.assertEqual([(t["from"], t["to"], t["guessed"]) for t in item["transitions"]],
                         [("open", "closed", False)])

    def test_js_plain_array(self):
        self.put("a.mjs", "const STATES = ['x', 'y'];\n")
        self.assertTrue(self.states()["items"][0]["transitions"][0]["guessed"])

    def test_override(self):
        self.put("m.py", 'STATUS = ("a", "b")\n')
        self.put("docs/system.json", {"machines": [
            {"id": "s:m.py:STATUS", "name": "STATUS", "states": ["a", "b", "c"],
             "transitions": [{"from": "a", "to": "c", "label": "skip"}]},
            {"id": "s:custom", "name": "custom", "states": ["p", "q"]}]})
        items = {i["id"]: i for i in self.states()["items"]}
        self.assertEqual(items["s:m.py:STATUS"]["states"], ["a", "b", "c"])
        self.assertFalse(items["s:m.py:STATUS"]["transitions"][0]["guessed"])
        self.assertIn("s:custom", items)

    def test_cap_and_confinement(self):
        for i in range(15):
            self.put("m%d.py" % i, 'STATUS = ("a", "b")\n')
        self.assertEqual(len(self.states()["items"]), 12)
        outside = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        with open(os.path.join(outside, "o.py"), "w") as fh:
            fh.write('OUT_STATUS = ("a", "b")\n')
        os.symlink(os.path.join(outside, "o.py"), os.path.join(self.root, "o.py"))
        self.files.append("o.py")
        self.assertFalse(any(i["file"] == "o.py" for i in system_data.states(self.root, self.files, {})["items"]))


if __name__ == "__main__":
    unittest.main()
