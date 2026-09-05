# Deploying Bok on hubbabubba

This is the deployment path for the home server **hubbabubba**. Bok runs as
two rootless Podman quadlets — `bok-api` and `bok-frontend` — under the
`e9wikner` account's `systemd --user` instance, LAN HTTP only, no reverse
proxy. Same model as the other stacks on that box (Home Assistant, MQTT,
Telldus); see `docs/podman.md` in the `hubbabubba` repo for the rationale.

It **replaces** the Docker Compose deployment on `q.stefanwikner.se`
(`../../DEPLOYMENT.md`), which is retired once this is confirmed working.

Everything here runs **as `e9wikner`, on the box, with no sudo** — after a
one-time setup that does need an admin shell.

## Files

| File | Purpose |
|---|---|
| `deploy.sh` | Run as `e9wikner` on hubbabubba. Pulls source, builds both images, installs the quadlets, restarts, health-checks. |
| `bok-api.container` | Quadlet for the API. Installed to `~/.config/containers/systemd/`. |
| `bok-frontend.container` | Quadlet for the frontend. |
| `/srv/appdata/bok/bok.env` | **Not in git.** The three secrets, `mode 600`, `e9wikner`-owned. |

## One-time setup (admin / `rsw` shell)

`e9wikner` cannot write under `/srv/appdata` (it only has traverse access), so
the stack directory and the secrets file are created once by an admin:

```bash
sudo mkdir -p /srv/appdata/bok/data
sudo chown -R e9wikner:e9wikner /srv/appdata/bok
sudo -u e9wikner install -m 600 /dev/null /srv/appdata/bok/bok.env
```

Then put the three secrets in `/srv/appdata/bok/bok.env` — **no quotes**, one
per line:

```
BOKFOERING_API_KEY=<openssl rand -hex 32>
JWT_SECRET=<openssl rand -hex 32>
AUTH_PASSWORD=<openssl rand -base64 24>
```

`AUTH_USERNAME` is `admin` (set in `bok-api.container`, not a secret). Save the
`AUTH_PASSWORD` in a password manager — it is the web-UI login.

`/srv/appdata` is on the snapshotted, backed-up `@docker` Btrfs subvolume, so
the SQLite database and `bok.env` are covered by the hubbabubba backup tiers
with no extra configuration.

## Deploy

```bash
ssh hubbabubba
~/Development/bok/deploy/hubbabubba/deploy.sh
```

What it does:

1. Clone/`git pull` the source into `/srv/appdata/bok/src`.
2. `podman build` `bok-api:latest` (repo root) and `bok-frontend:latest`
   (`frontend-v3/`) — only when the source changed, unless `--force-build`.
   The previous images are retagged `:previous` first.
3. Copy the two `.container` files into `~/.config/containers/systemd/` and
   `systemctl --user daemon-reload`.
4. `systemctl --user restart bok-api bok-frontend`.
5. Curl `/health` on `:8000` and `:3000` and check the DB file ownership.

`[Install] WantedBy=default.target` in the quadlets means both units come back
on reboot automatically — no `systemctl enable` needed (linger is already on
for `e9wikner`).

Flags: `--no-build` (quadlet + restart only), `--force-build` (rebuild even if
the source is unchanged).

## Verify

```bash
systemctl --user status bok-api.service bok-frontend.service
curl -fsS http://hubbabubba:8000/health        # {"status":"ok","commit":"<sha>"}
curl -fsS http://hubbabubba:3000/health        # same JSON, via the Next.js proxy
```

Then open `http://hubbabubba:3000/login` and log in with `admin` /
`AUTH_PASSWORD`.

## Update

Re-run `deploy.sh`. It fast-forwards the source and rebuilds only if there are
new commits.

## Rollback

```bash
podman tag bok-api:previous bok-api:latest
podman tag bok-frontend:previous bok-frontend:latest
systemctl --user restart bok-api.service bok-frontend.service
```

For a bad database (not a bad build), restore the `/srv/appdata` Btrfs
snapshot — see `docs/backup.md` in the `hubbabubba` repo.

## Rotate a secret

Edit `/srv/appdata/bok/bok.env` and `systemctl --user restart bok-api.service`.

## Config knobs

The quadlets hardcode ports `8000` (API) and `3000` (frontend) and the
`admin` username. Change them by editing the `.container` files here and
re-running `deploy.sh`. There is intentionally no TLS / reverse proxy layer —
that matches every other service on hubbabubba.
