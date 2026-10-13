"""API v1 routes: schema checks for every route, ETag and 304, the deprecated /data.json alias, method checks and
the one write route, with the usage sync replaced by a fake."""

import json
import os

from roadmap.store import config as config_store
from tests.api.support import PROJECT_ID, ServerCase, FakeSync


class ReadRoutes(ServerCase):
    def test_health(self):
        res = self.request("GET", "/api/v1/health")
        self.assert_schema(res, "health")
        self.assertIs(res.json()["ok"], True)

    def test_meta(self):
        res = self.request("GET", "/api/v1/meta")
        self.assert_schema(res, "meta")
        self.assertEqual(res.json()["api_version"], "v1")

    def test_projects_list(self):
        res = self.request("GET", "/api/v1/projects")
        self.assert_schema(res, "projects")
        row = res.json()["projects"][0]
        self.assertEqual(row["id"], PROJECT_ID)
        self.assertIs(row["stale"], False)
        self.assertGreater(row["tasks_left"], 0)

    def test_snapshot(self):
        res = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID)
        self.assert_schema(res, "snapshot")
        self.assertEqual(res.json()["project"], {"id": PROJECT_ID, "title": "split-net"})

    def test_usage_without_any_sync(self):
        res = self.request("GET", "/api/v1/usage")
        self.assert_schema(res, "usage")
        self.assertIs(res.json()["stale"], True)
        self.assertEqual(self.sync.calls, 0)

    def test_unknown_project_is_404_envelope(self):
        res = self.request("GET", "/api/v1/projects/nosuch/snapshot")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "not_found")
        self.assertEqual(validate_error(res), [])

    def test_bad_project_id_shape_is_404(self):
        res = self.request("GET", "/api/v1/projects/Split_Net/snapshot")
        self.assertEqual(res.status, 404)

    def test_missing_data_file_gives_errors_not_500(self):
        os.remove(os.path.join(self.project_root, "docs", "tasks.json"))
        res = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID)
        self.assert_schema(res, "snapshot")
        self.assertIn("tasks.json", [e["file"] for e in res.json()["errors"]])
        rows = self.request("GET", "/api/v1/projects").json()["projects"]
        self.assertIs(rows[0]["stale"], True)
        self.assertGreaterEqual(rows[0]["errors_count"], 1)


class Etag(ServerCase):
    def test_304_on_matching_etag(self):
        # a running job's duration moves with the clock, so the project here has no jobs.json
        os.remove(os.path.join(self.project_root, "docs", "jobs.json"))
        first = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID)
        etag = first.header("ETag")
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))
        again = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID, headers={"If-None-Match": etag})
        self.assertEqual(again.status, 304)
        self.assertEqual(again.body, b"")
        self.assertEqual(again.header("ETag"), etag)
        weak = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID, headers={"If-None-Match": "W/" + etag})
        self.assertEqual(weak.status, 304)

    def test_etag_changes_when_the_data_changes(self):
        path = os.path.join(self.project_root, "docs", "tasks.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        first = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID).header("ETag")
        data["updated"] = "2030-01-01"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        res = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID, headers={"If-None-Match": first})
        self.assertEqual(res.status, 200)
        self.assertNotEqual(res.header("ETag"), first)
        self.assertEqual(res.json()["tasks_updated"], "2030-01-01")


VOLATILE_KEYS = ("server_time", "elapsed_s")


def strip_volatile(value):
    """A copy with server_time and elapsed_s removed at every depth. Those two change between the two requests
    (elapsed_s is measured from the clock); nothing else is dropped."""
    if isinstance(value, dict):
        return {key: strip_volatile(item) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [strip_volatile(item) for item in value]
    return value


class DeprecatedAlias(ServerCase):
    def test_data_json_equals_first_project_snapshot(self):
        legacy = self.request("GET", "/data.json")
        self.assertEqual(legacy.status, 200)
        self.assertEqual(legacy.header("Deprecation"), "true")
        self.assertIn("/api/v1/projects/%s/snapshot" % PROJECT_ID, legacy.header("Link"))
        new = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID)
        a, b = strip_volatile(legacy.json()), strip_volatile(new.json())
        self.assertEqual(a, b)

    def test_data_json_without_projects_is_404(self):
        config_store.remove_project(PROJECT_ID)
        res = self.request("GET", "/data.json")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "not_found")


class WriteRoute(ServerCase):
    def test_sync_calls_the_injected_fake_exactly_once(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 200)
        self.assertEqual(self.sync.calls, 1)
        self.assert_schema(res, "usage")

    def test_sync_with_empty_body_is_fine(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"")
        self.assertEqual(res.status, 200)
        self.assertEqual(self.sync.calls, 1)

    def test_sync_failure_is_502_with_plain_reason(self):
        from roadmap.services.usage import UsageError
        self.httpd.app._sync = FakeSync(UsageError("keychain item not found, sign in to Claude Code first"))
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 502)
        self.assertEqual(res.json()["error"]["code"], "usage_unavailable")
        self.assertNotIn(self.token, res.body.decode("utf-8"))

    def test_read_routes_refuse_post_with_allow_header(self):
        for path in ("/api/v1/health", "/api/v1/meta", "/api/v1/projects", "/api/v1/usage",
                     "/api/v1/projects/%s/snapshot" % PROJECT_ID, "/data.json"):
            with self.subTest(path=path):
                res = self.request("POST", path, headers=self.write_headers(), body=b"{}")
                self.assertEqual(res.status, 405)
                self.assertEqual(res.header("Allow"), "GET")
                self.assertEqual(res.json()["error"]["code"], "method_not_allowed")

    def test_sync_route_refuses_get(self):
        res = self.request("GET", "/api/v1/usage/sync")
        self.assertEqual(res.status, 405)
        self.assertEqual(res.header("Allow"), "POST")
        self.assertEqual(self.sync.calls, 0)


def validate_error(res):
    from tests.api.support import load_schema, validate
    return validate(res.json(), load_schema("error"))
