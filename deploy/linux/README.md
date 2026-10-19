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
