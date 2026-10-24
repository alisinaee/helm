"""The work rows carry owner, outcome and tasks."""
import json
import unittest

from roadmap.core import snapshot


def _task(tid, state, model="sonnet"):
    return {"id": tid, "state": state, "model": model}


class WorkFieldsTest(unittest.TestCase):
    def test_owner_outcome_tasks(self):
        doc = {"items": [{"id": "W1", "title": "a", "kind": "task", "prio": 1, "outcome": "ships", "owner": "you"},
                         {"id": "W2", "title": "b", "kind": "task", "prio": 2, "owner": ""},
                         {"id": "W3", "title": "c", "kind": "task", "prio": 2}],
               "links": {"T1": "W2", "T2": "W2", "T3": "W2"}}
        tasks = [_task("T1", "done", "haiku"), _task("T2", "running"), _task("T3", "todo")]
        jobs = [{"id": "J1", "task": "T2"}, {"id": "J2", "task": "T2"}]
        rows = {r["id"]: r for r in snapshot._work_view(json.dumps(doc), tasks, [], jobs)}
        self.assertEqual((rows["W1"]["owner"], rows["W1"]["outcome"], rows["W1"]["tasks"]), ("you", "ships", []))
        self.assertEqual((rows["W2"]["owner"], rows["W2"]["outcome"]), ("head", None))
        self.assertEqual(rows["W3"]["owner"], None)
        self.assertEqual([t["id"] for t in rows["W2"]["tasks"]], ["T2", "T3", "T1"])
        self.assertEqual(rows["W2"]["tasks"][0], {"id": "T2", "state": "running", "model": "sonnet", "job": "J2"})

    def test_task_cap(self):
        links = {"T%d" % i: "W1" for i in range(30)}
        doc = {"items": [{"id": "W1", "title": "a", "kind": "task"}], "links": links}
        rows = snapshot._work_view(json.dumps(doc), [_task(t, "todo") for t in links], [])
        self.assertEqual(len(rows[0]["tasks"]), 20)


if __name__ == "__main__":
    unittest.main()
