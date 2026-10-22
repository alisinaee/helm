# Helm on the mjp-labs Linux server (helm.mjplabs.ir)

Helm runs as a systemd user service and is reached from anywhere through Nginx Proxy Manager (NPM) with an
Authelia login in front.

```
browser --https--> helm.mjplabs.ir (Cloudflare DNS, A 84.241.9.114, not proxied)
        --> router :443 --> NPM container (wildcard cert *.mjplabs.ir)
        --> auth_request to Authelia (one_factor, session cookie on mjplabs.ir)
        --> http://192.168.31.50:8780  (bin/roadmap serve, systemd --user helm.service)
```

## Pieces

- `helm.service`: copy to `~/.config/systemd/user/`, then `systemctl --user daemon-reload && systemctl --user enable --now helm`.
  Two environment variables make the server work behind the proxy:
  - `ROADMAP_BIND_HOST=192.168.31.50`: bind the main listener on the LAN address so the NPM container can reach it
    (default 127.0.0.1). The phone listener stays on loopback (`--no-phone` here).
  - `ROADMAP_PUBLIC_HOST=helm.mjplabs.ir`: the Host check and the Origin/CSRF write check also accept this name
    (`https://helm.mjplabs.ir`). Any other Host still gets 421.
- `npm-helm.conf`: the server block appended to NPM's `/data/nginx/custom/http.conf` (hand-written, not in the NPM
  UI, like studio.mjplabs.ir). Reload with `docker exec npm nginx -t && docker exec npm nginx -s reload`.
- Firewall (ufw): the NPM container reaches the host from the docker range, so 8780 must be open to it (else
  NPM answers 504 after the Authelia login):
  `sudo ufw allow from 172.16.0.0/12 to any port 8780 proto tcp comment 'Helm from docker (NPM)'`
- Authelia: `helm.mjplabs.ir` is in the `one_factor` domain list of `/srv/docker/authelia/config/configuration.yml`
  (default policy is deny). Restart with `docker restart authelia` after changes.

## Operate

```
systemctl --user status helm
journalctl --user -u helm -f
systemctl --user restart helm      # load new code after git pull
```

State lives in the default places (`~/.config/roadmap-board`, `~/.local/state/...`); the project registered is this
checkout (`bin/roadmap project add .`).

## Several Claude accounts on this server (Tokens > Account)

Each login lives in its own config folder (`~/.claude-<name>`, the same layout `CLAUDE_CONFIG_DIR=~/.claude-<name>
claude auth login` makes). Plain `claude` uses `~/.claude/.credentials.json` + `~/.claude.json`.

- **+ Log in another account**: give it a name. Helm runs `claude auth login` for `~/.claude-<name>` on the server,
  shows the sign-in link; sign in with the account you want, copy the code the page shows and paste it back. The
  account is added and read live from then on.
- **Switch**: moves that stored login into plain `claude` (marked **In use**), no new login. The login that was in
  use is first saved back to its own folder (a new `~/.claude-<name>` is made and added when it had none), with the
  freshest token pair. New Claude Code sessions use the new login; sessions already open keep theirs.
- **Weekly / 5 hour** columns: every connected account is read every sync, not only the starred one. The board's
  own usage (top bar, stops) follows the **Active** account, which is the in-use login by default.
- **Log in** (row action) appears when a stored login expired or is signed out; it re-logs that folder.

CLI: `bin/roadmap usage account list`, `bin/roadmap service status|restart|logs` (systemd --user on Linux).

## /helm and hooks

- Hooks: `bin/roadmap hooks install helm` wrote `.claude/settings.local.json` (git-ignored). Every Claude Code chat
  opened in this folder now reports to Helm: presence, the person's prompts into the Head ledger, Agent calls as
  jobs, and the usage-stop gate.
- `/helm` (not `/head`: that name belongs to the head mod in home-server-head): the skill is
  `.claude/skills/helm/SKILL.md`, loaded in chats opened in this folder; for other folders install it with
  `mkdir -p ~/.claude/skills/helm && cp .claude/skills/helm/SKILL.md ~/.claude/skills/helm/`.
