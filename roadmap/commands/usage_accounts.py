"""`helm usage account ...` (R11.8, docs/USAGE-ACCOUNTS.md): list, check, connect, disconnect, switch, add, remove
and login. Registered by commands/usage.py. Nothing here prints a token; e-mails are shown masked."""

from roadmap.services import usage_accounts as accounts


def register(actions, common):
    """Add `usage account ACTION` under the usage group."""
    group = actions.add_parser("account", parents=[common], help="which Claude login the usage sync reads")
    sub = group.add_subparsers(dest="account_action", metavar="ACTION", required=True)
    sub.add_parser("list", parents=[common], help="list the usage accounts").set_defaults(handler=handle_list)
    check = sub.add_parser("check", parents=[common], help="read who is logged in (claude auth status)")
    check.add_argument("id", nargs="?", default=None)
    check.set_defaults(handler=handle_check)
    for name, text, handler in (
            ("connect", "let Helm read this login again", handle_connect),
            ("disconnect", "Helm stops reading this login (Claude Code stays signed in)", handle_disconnect),
            ("switch", "make this account the one the sync reads", handle_switch),
            ("remove", "forget this account in Helm (Claude Code is not touched)", handle_remove)):
        cmd = sub.add_parser(name, parents=[common], help=text)
        cmd.add_argument("id")
        cmd.set_defaults(handler=handler)
    add = sub.add_parser("add", parents=[common], help="add another Claude login place")
    add.add_argument("id")
    add.add_argument("--label", default=None)
    where = add.add_mutually_exclusive_group(required=True)
    where.add_argument("--config-dir", default=None, help="a CLAUDE_CONFIG_DIR folder (a second Claude account)")
    where.add_argument("--credentials-file", default=None, help="a .credentials.json file")
    where.add_argument("--keychain", action="store_true", help="the default keychain login")
    add.add_argument("--keychain-service", default=None, help="override the keychain item name")
    add.set_defaults(handler=handle_add)
    login = sub.add_parser("login", parents=[common], help="print (and on macOS, --open in Terminal) the login command")
    login.add_argument("id", nargs="?", default=None)
    login.add_argument("--open", action="store_true", help="open a Terminal window running it")
    login.set_defaults(handler=handle_login)


def _json(args):
    return getattr(args, "json", False)


def _pct(value):
    return "-" if value is None else "%s%%" % value


def _line(row):
    ident = row["identity"]
    who = ident.get("emailMasked") or "-"
    reading = row["reading"]
    return "%s %-12s %-14s %-24s %-6s %-12s week %-5s 5h %-5s %s" % (
        "*" if row["active"] else " ", row["id"], row["label"][:14], who, ident.get("plan") or "-", row["status"],
        _pct(reading.get("weeklyPercent")), _pct(reading.get("fiveHourPercent")), row["path"] or row["source"])


def _print_list(args, result):
    if not _json(args):
        for row in result["accounts"]:
            print(_line(row))
        print(result["note"])
    return result


def _local(result):
    """The CLI shows masked e-mails only, like any log a terminal may keep."""
    for row in result.get("accounts", [result] if "identity" in result else []):
        row["identity"].pop("email", None)
    return result


def handle_list(args):
    return _print_list(args, accounts.list_status(full_email=False))


def handle_check(args):
    row = _local(accounts.check(args.id))
    if not _json(args):
        print(_line(row))
    return row


def handle_connect(args):
    return _print_list(args, _local(accounts.connect(args.id, src="cli", data_dir=_data_dir())))


def handle_disconnect(args):
    return _print_list(args, _local(accounts.disconnect(args.id, src="cli", data_dir=_data_dir())))


def handle_switch(args):
    return _print_list(args, _local(accounts.switch(args.id, src="cli", data_dir=_data_dir())))


def handle_remove(args):
    return _print_list(args, _local(accounts.remove(args.id, src="cli", data_dir=_data_dir())))


def handle_add(args):
    if args.config_dir:
        source, path = "config-dir", args.config_dir
    elif args.credentials_file:
        source, path = "credentials-file", args.credentials_file
    else:
        source, path = "keychain", None
    result = accounts.add(args.id, label=args.label, source=source, path=path, keychain_service=args.keychain_service,
                          src="cli", data_dir=_data_dir())
    return _print_list(args, _local(result))


def handle_login(args):
    if args.open:
        result = accounts.open_login(args.id, src="cli", data_dir=_data_dir())
    else:
        cfg = accounts.config_store.load()
        account = accounts._find(cfg, args.id or accounts.active_id(cfg))
        result = {"opened": False, "command": accounts.login_command(accounts.config_dir_of(account))}
    if not _json(args):
        print(result["command"])
        print("then: helm usage account check" + (" " + args.id if args.id else ""))
    return result


def _data_dir():
    """The first registered project's data folder for the activity line, or None."""
    try:
        from roadmap.services import tasks
        return tasks.resolve(None)[1]
    except Exception:
        return None
