"""services/claude_slots: several Claude logins on Linux, switched with no new login, and the web login."""

import json
import os
import stat
import sys
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import claude_slots, usage, usage_accounts
from tests.unit.test_store_support import HomeCase


def write(path, data, mode=0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.chmod(path, mode)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def login(folder_creds, folder_state, uuid, email, token, extra=None):
    creds = {"claudeAiOauth": {"accessToken": token, "refreshToken": "r-" + token, "expiresAt": 9999999999999,
                               "subscriptionType": "max"}}
    creds.update(extra or {})
    write(folder_creds, creds)
    write(folder_state, {"oauthAccount": {"accountUuid": uuid, "emailAddress": email, "organizationName": "Org"},
                         "projects": {"keep": 1}})


class SlotsCase(HomeCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(sys, "platform", "linux")
        patcher.start()
        self.addCleanup(patcher.stop)
        claude_slots._owners.clear()
        self.addCleanup(claude_slots._owners.clear)
        self.home = os.environ["HOME"]
        os.makedirs(self.home)
        login(os.path.join(self.home, ".claude", ".credentials.json"), os.path.join(self.home, ".claude.json"),
              "uuid-a", "alice@example.com", "tok-a", extra={"mcpOAuth": {"x": 1}})
        self.work = os.path.join(self.home, ".claude-work")
        login(os.path.join(self.work, ".credentials.json"), os.path.join(self.work, ".claude.json"),
              "uuid-b", "bob@example.com", "tok-b")
        usage_accounts.add("work", label="Work", source="config-dir", path=self.work)

    def live_creds(self):
        return read(os.path.join(self.home, ".claude", ".credentials.json"))


class UseInClaudeTest(SlotsCase):
    def test_switch_swaps_login_and_saves_the_old_one(self):
        claude_slots.use_in_claude("work")
        live = self.live_creds()
        self.assertEqual(live["claudeAiOauth"]["accessToken"], "tok-b")
        self.assertEqual(live["mcpOAuth"], {"x": 1})  # other keys stay
        state = read(os.path.join(self.home, ".claude.json"))
        self.assertEqual(state["oauthAccount"]["accountUuid"], "uuid-b")
        self.assertEqual(state["projects"], {"keep": 1})
        mode = stat.S_IMODE(os.stat(os.path.join(self.home, ".claude", ".credentials.json")).st_mode)
        self.assertEqual(mode, 0o600)
        # the old live login was saved to a new folder and added as an account
        saved = os.path.join(self.home, ".claude-alice")
        self.assertEqual(read(os.path.join(saved, ".credentials.json"))["claudeAiOauth"]["accessToken"], "tok-a")
        self.assertEqual(read(os.path.join(saved, ".claude.json"))["oauthAccount"]["accountUuid"], "uuid-a")
        ids = [a["id"] for a in usage_accounts.accounts()]
        self.assertIn("alice", ids)

    def test_switch_back_writes_the_fresh_pair_back(self):
        claude_slots.use_in_claude("work")
        # Claude Code refreshed the live token meanwhile
        path = os.path.join(self.home, ".claude", ".credentials.json")
        live = self.live_creds()
        live["claudeAiOauth"]["accessToken"] = "tok-b2"
        write(path, live)
        claude_slots.use_in_claude("alice")
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")
        self.assertEqual(read(os.path.join(self.work, ".credentials.json"))["claudeAiOauth"]["accessToken"], "tok-b2")
        self.assertEqual(len([a for a in usage_accounts.accounts() if a["id"].startswith("alice")]), 1)

    def test_rows_show_who_is_in_claude(self):
        rows = {r["id"]: r for r in usage_accounts.list_status()["accounts"]}
        self.assertTrue(rows["default"]["inClaude"])
        self.assertFalse(rows["work"]["inClaude"])
        self.assertTrue(rows["work"]["canUse"])
        self.assertEqual(rows["work"]["identity"]["emailMasked"], usage_accounts.mask_email("bob@example.com"))
        claude_slots.use_in_claude("work")
        rows = {r["id"]: r for r in usage_accounts.list_status()["accounts"]}
        self.assertTrue(rows["work"]["inClaude"])
        self.assertFalse(rows["work"]["canUse"])
        self.assertTrue(usage_accounts.list_status()["switchable"])

    def test_not_logged_in_folder_is_refused(self):
        empty = os.path.join(self.home, ".claude-empty")
        os.makedirs(empty)
        usage_accounts.add("empty", source="config-dir", path=empty)
        with self.assertRaises(RoadmapError):
            claude_slots.use_in_claude("empty")
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")

    def test_default_account_is_refused(self):
        with self.assertRaises(RoadmapError):
            claude_slots.use_in_claude("default")

    def test_macos_is_refused(self):
        with mock.patch.object(sys, "platform", "darwin"):
            with self.assertRaises(RoadmapError):
                claude_slots.use_in_claude("work")
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")


class ReadAllTest(SlotsCase):
    def test_sync_others_reads_each_connected_account(self):
        seen = []

        def fetch(token):
            seen.append(token)
            return {"five_hour": {"utilization": 10, "resets_at": None}, "seven_day": {"utilization": 20,
                                                                                         "resets_at": None}}
        out = usage.sync_others(fetch=fetch)
        self.assertEqual(out, {"work": "ok"})
        self.assertEqual(seen, ["tok-b"])
        row = {r["id"]: r for r in usage_accounts.list_status()["accounts"]}["work"]
        self.assertEqual(row["status"], "ok")
        self.assertTrue(row["live"])

    def test_account_in_claude_is_read_from_the_live_login(self):
        claude_slots.use_in_claude("work")
        live = self.live_creds()
        live["claudeAiOauth"]["accessToken"] = "tok-b-fresh"
        write(os.path.join(self.home, ".claude", ".credentials.json"), live)
        seen = []
        # the board follows the default login, which is "work" now: sync_once files its reading on "work" too,
        # and sync_others does not fetch it a second time
        payload = {"five_hour": {"utilization": 5, "resets_at": None}, "seven_day": {"utilization": 33,
                                                                                     "resets_at": None}}
        usage.sync_once(fetch=lambda t: seen.append(t) or payload)
        self.assertEqual(seen, ["tok-b-fresh"])
        self.assertEqual(usage_accounts.last_reading("work")["weeklyPercent"], 33)
        seen.clear()
        usage.sync_others(fetch=lambda t: seen.append(t) or payload)
        self.assertNotIn("tok-b-fresh", seen)
        self.assertNotIn("tok-b", seen)
        # with the board on another account, the in-use login is read from ~/.claude (its freshest copy)
        usage_accounts.switch("alice")
        seen.clear()
        usage.sync_others(fetch=lambda t: seen.append(t) or {})
        self.assertIn("tok-b-fresh", seen)
        self.assertNotIn("tok-b", seen)

    def test_in_use_account_is_listed_once(self):
        usage_accounts.note_reading("work", {"weeklyPercent": 12})
        usage_accounts.note_reading("default", {"weeklyPercent": 41})  # alice's numbers, before the switch
        claude_slots.use_in_claude("work")
        rows = usage_accounts.list_status()["accounts"]
        self.assertNotIn("default", [r["id"] for r in rows])
        work = {r["id"]: r for r in rows}["work"]
        self.assertTrue(work["inClaude"])
        self.assertTrue(work["active"])
        self.assertEqual(work["reading"]["weeklyPercent"], 12)  # its own numbers, never the previous login's


class StoredRefreshTest(SlotsCase):
    def test_stored_login_is_refreshed_when_expired(self):
        path = os.path.join(self.work, ".credentials.json")
        creds = read(path)
        creds["claudeAiOauth"]["expiresAt"] = 1000  # long expired
        write(path, creds)
        posted = []

        def post(url, body):
            posted.append(body["refresh_token"])
            return {"access_token": "tok-b-new", "refresh_token": "r-new", "expires_in": 3600}
        from roadmap.services import usage_sources
        seen = []
        payload = {"five_hour": {"utilization": 1, "resets_at": None}, "seven_day": {"utilization": 2, "resets_at": None}}
        with mock.patch.object(usage_sources, "_post_json", post):
            out = usage.sync_others(fetch=lambda t: seen.append(t) or payload)
        self.assertEqual(out, {"work": "ok"})
        self.assertEqual(posted, ["r-tok-b"])
        self.assertEqual(seen, ["tok-b-new"])
        self.assertEqual(read(path)["claudeAiOauth"]["refreshToken"], "r-new")
        # the login in use is never refreshed by Helm
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")


class MismatchTest(SlotsCase):
    def owners(self, table):
        patcher = mock.patch.object(claude_slots, "FETCH_PROFILE", lambda token: table.get(token))
        patcher.start()
        self.addCleanup(patcher.stop)
        claude_slots._owners.clear()

    def test_switch_refuses_a_folder_holding_another_accounts_token(self):
        self.owners({"tok-b": {"accountUuid": "uuid-a", "emailAddress": "alice@example.com"}})
        with self.assertRaises(RoadmapError):
            claude_slots.use_in_claude("work")
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")

    def test_live_token_is_saved_under_its_real_owner(self):
        # ~/.claude.json says alice, but the live token is bob's (work)
        self.owners({"tok-a": {"accountUuid": "uuid-b", "emailAddress": "bob@example.com"}})
        claude_slots.save_live()
        self.assertEqual(read(os.path.join(self.work, ".credentials.json"))["claudeAiOauth"]["accessToken"], "tok-a")
        self.assertEqual(read(os.path.join(self.work, ".claude.json"))["oauthAccount"]["accountUuid"], "uuid-b")
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-alice")))

    def test_sync_marks_a_mixed_up_folder(self):
        self.owners({"tok-b": {"accountUuid": "uuid-a"}})
        payload = {"five_hour": {"utilization": 1, "resets_at": None}, "seven_day": {"utilization": 2, "resets_at": None}}
        out = usage.sync_others(fetch=lambda t: payload)
        self.assertEqual(out, {"work": "mismatch"})
        row = {r["id"]: r for r in usage_accounts.list_status()["accounts"]}["work"]
        self.assertEqual(row["status"], "wrong_login")

    def test_login_restores_the_live_file_if_it_changed(self):
        path = os.path.join(self.home, ".claude", ".credentials.json")
        entry = {"liveBefore": open(path, "rb").read()}
        write(path, {"claudeAiOauth": {"accessToken": "intruder"}})
        claude_slots._keep_live(entry)
        self.assertEqual(self.live_creds()["claudeAiOauth"]["accessToken"], "tok-a")


class WebLoginTest(SlotsCase):
    def test_find_url_strips_terminal_codes(self):
        text = ("If the browser didn't open, visit: \x1b]8;;https://claude.com/cai/oauth/authorize?code=true&x=1"
                "\x07https://claude.com/cai/oauth/authorize?code=true&x=1\x1b]8;;\x07\nPaste code here >")
        self.assertEqual(claude_slots.find_url(text), "https://claude.com/cai/oauth/authorize?code=true&x=1")
        self.assertIsNone(claude_slots.find_url("https://evil.example.com/a"))

    def test_login_flow_with_fake_terminal(self):
        rfd, wfd = os.pipe()
        os.write(wfd, b"visit: https://claude.com/cai/oauth/authorize?code=true\n")
        calls = {}

        def spawn(argv, env):
            calls["argv"], calls["env"] = argv, env
            return 4242, rfd

        with mock.patch.object(usage_accounts, "claude_binary", return_value="/bin/claude"):
            started = claude_slots.login_start(label="Team B", spawn=spawn)
        self.assertEqual(started["key"], "team-b")
        self.assertTrue(started["url"].startswith("https://claude.com/"))
        self.assertEqual(calls["argv"], ["/bin/claude", "auth", "login"])
        self.assertEqual(calls["env"]["CLAUDE_CONFIG_DIR"], os.path.join(self.home, ".claude-team-b"))
        with self.assertRaises(RoadmapError):
            claude_slots.login_code("team-b", "x y")
        # finish: the fake login wrote its files and exited 0
        folder = os.path.join(self.home, ".claude-team-b")
        login(os.path.join(folder, ".credentials.json"), os.path.join(folder, ".claude.json"), "uuid-c",
              "carol@example.com", "tok-c")
        entry = claude_slots._logins["team-b"]
        entry["fd"] = wfd
        with mock.patch.object(claude_slots, "_exited", return_value=0), \
                mock.patch.object(claude_slots, "_read_some", return_value=b""):
            result = claude_slots.login_code("team-b", "abcdef123456#state")
        self.assertEqual(result["loggedIn"], "team-b")
        self.assertIn("team-b", [a["id"] for a in usage_accounts.accounts()])
        os.close(rfd)

    def test_code_for_unknown_login(self):
        with self.assertRaises(RoadmapError):
            claude_slots.login_code("nope", "abcdefghij")


class MacFullEmailTest(SlotsCase):
    def test_full_email_comes_from_files_on_mac_and_active_marks_one_row(self):
        with mock.patch.object(sys, "platform", "darwin"):
            rows = {r["id"]: r for r in usage_accounts.list_status(full_email=True)["accounts"]}
            masked = usage_accounts.list_status(full_email=False)["accounts"]
        main = [r for r in rows.values() if r["source"] != "config-dir"][0]
        self.assertEqual(main["identity"]["email"], "alice@example.com")
        self.assertEqual(rows["work"]["identity"]["email"], "bob@example.com")
        self.assertEqual([r["active"] for r in rows.values()].count(True), 1)
        self.assertTrue(all(r["identity"].get("email") is None for r in masked))
