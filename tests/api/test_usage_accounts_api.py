"""R11.8: GET /api/v1/usage/accounts and POST /api/v1/usage/accounts/{id}/{action}. The GET is the Account tab's
masked rows. The POST needs the write guard (CSRF, same origin, JSON), maps each action to its usage_accounts call
with src="ui", and gives 404 for an unknown action or account. Browser, keychain and login calls are mocked."""

from unittest import mock

from tests.api.support import ServerCase

SAME = {"Sec-Fetch-Site": "same-origin"}
ROW = {"id": "acct-1", "connected": True}


class UsageAccountsRoutes(ServerCase):
    def post(self, account, action, headers=None):
        return self.request("POST", "/api/v1/usage/accounts/%s/%s" % (account, action),
                            headers=headers if headers is not None else self.write_headers())

    def test_get_lists_rows_with_full_email_on_the_main_listener(self):
        with mock.patch("roadmap.services.usage_accounts.list_status", return_value=[ROW]) as status:
            res = self.request("GET", "/api/v1/usage/accounts", headers=SAME)
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), [ROW])
        status.assert_called_once_with(full_email=True)

    def test_get_masks_the_email_on_the_phone_listener(self):
        from roadmap.http import routes

        class _PhoneishApp:
            cmd_source = "phone"

        with mock.patch("roadmap.services.usage_accounts.list_status", return_value=[ROW]) as status:
            routes.usage_accounts_get(_PhoneishApp(), None, None)
        status.assert_called_once_with(full_email=False)

    def test_post_needs_the_write_guard(self):
        with mock.patch("roadmap.services.usage_accounts.connect") as connect:
            no_token = self.post("acct-1", "connect", headers={"Sec-Fetch-Site": "same-origin",
                                                              "Content-Type": "application/json"})
            cross = self.post("acct-1", "connect", headers=self.write_headers(**{"Sec-Fetch-Site": "cross-site"}))
            text = self.post("acct-1", "connect", headers=dict(self.write_headers(), **{"Content-Type": "text/plain"}))
        self.assertEqual(no_token.status, 403)
        self.assertEqual(cross.status, 403)
        self.assertEqual(text.status, 415)
        connect.assert_not_called()

    def test_actions_map_to_usage_accounts_with_src_ui(self):
        cases = {"connect": "connect", "disconnect": "disconnect", "switch": "switch"}
        for action, func in cases.items():
            with mock.patch("roadmap.services.usage_accounts." + func, return_value=dict(ROW, action=action)) as fn:
                res = self.post("acct-1", action)
            self.assertEqual(res.status, 200, res.body[:200])
            self.assertEqual(res.json()["action"], action)
            fn.assert_called_once_with("acct-1", src="ui")

    def test_check_and_login(self):
        with mock.patch("roadmap.services.usage_accounts.check", return_value=ROW) as check:
            res = self.post("acct-1", "check")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), ROW)
        check.assert_called_once_with("acct-1")

        opened = {"opened": True, "command": "claude auth login"}
        with mock.patch("roadmap.services.claude_slots.supported", return_value=False), \
                mock.patch("roadmap.services.usage_accounts.open_login", return_value=opened) as login:
            res = self.post("acct-1", "login")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), opened)
        login.assert_called_once_with("acct-1", src="ui")

    def test_linux_login_and_use(self):
        started = {"key": "acct-1", "url": "https://claude.com/x", "folder": "~/.claude-acct-1"}
        with mock.patch("roadmap.services.claude_slots.supported", return_value=True), \
                mock.patch("roadmap.services.claude_slots.login_start", return_value=started) as start:
            res = self.post("acct-1", "login")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), started)
        start.assert_called_once_with("acct-1")
        with mock.patch("roadmap.services.claude_slots.use_in_claude", return_value=ROW) as use:
            res = self.post("acct-1", "use")
        self.assertEqual(res.status, 200)
        use.assert_called_once_with("acct-1", src="ui")

    def test_unknown_action_is_404(self):
        with mock.patch("roadmap.services.usage_accounts.connect") as connect:
            res = self.post("acct-1", "delete")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "not_found")
        connect.assert_not_called()

    def test_unknown_account_is_404(self):
        # check resolves the id before any browser or keychain work, so nothing else is mocked here.
        res = self.post("no-such-account", "check")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "not_found")

    def add(self, body, headers=None):
        import json
        return self.request("POST", "/api/v1/usage/accounts", body=json.dumps(body).encode(),
                            headers=headers if headers is not None else self.write_headers())

    def test_post_add_calls_usage_accounts_add(self):
        body = {"id": "work", "label": "Work", "source": "config-dir", "path": "~/.claude-work"}
        with mock.patch("roadmap.services.usage_accounts.add", return_value=ROW) as add:
            res = self.add(body)
        self.assertEqual(res.status, 200, res.body[:200])
        add.assert_called_once_with("work", label="Work", source="config-dir", path="~/.claude-work",
                                    keychain_service=None, src="ui")

    def test_post_add_rejects_a_non_object_body(self):
        with mock.patch("roadmap.services.usage_accounts.add") as add:
            res = self.add([1, 2])
        self.assertEqual(res.status, 400)
        add.assert_not_called()

    def test_post_remove_maps_to_remove(self):
        with mock.patch("roadmap.services.usage_accounts.remove", return_value=ROW) as rm:
            res = self.post("acct-1", "remove")
        self.assertEqual(res.status, 200, res.body[:200])
        rm.assert_called_once_with("acct-1", src="ui")

    def test_phone_listener_is_denied_add_and_remove(self):
        from roadmap.errors import RoadmapError
        from roadmap.http import routes

        class _PhoneishApp:
            cmd_source = "phone"

        for fn, m in ((routes.usage_accounts_add, None), (routes.usage_accounts_action, {})):
            with mock.patch("roadmap.services.usage_accounts.add") as add, \
                    mock.patch("roadmap.services.usage_accounts.remove") as rm:
                with self.assertRaises(RoadmapError) as ctx:
                    fn(_PhoneishApp(), None, None)
            self.assertEqual(ctx.exception.code, "forbidden")
            add.assert_not_called()
            rm.assert_not_called()
