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
| `/srv/appdata/bok/dropzone` | **Not created here.** The `Bokforing` SMB share, owned by the hubbabubba repo — see "Folder intake" below. |

## One-time setup (admin / `rsw` shell)

`e9wikner` cannot write under `/srv/appdata` (it only has traverse access), so
the stack directory and the secrets file are created once by an admin:

```bash
sudo mkdir -p /srv/appdata/bok/data
sudo chown e9wikner:e9wikner /srv/appdata/bok /srv/appdata/bok/data
sudo -u e9wikner install -m 600 /dev/null /srv/appdata/bok/bok.env
```

**Not `chown -R`.** `/srv/appdata/bok/dropzone` is an SMB share owned by the
file server (`rsw:rsw`, `2770`, plus a POSIX ACL granting `e9wikner`). Taking
ownership of it would be reverted by hubbabubba's daily permission check the
next morning, and the churn would show up as drift in the meantime.

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
5. Create any missing folders of the dropzone contract (below).
6. Curl `/health` on `:8000` and `:3000`, check the DB file ownership, and
   print the dropzone scanner's status.

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

## Folder intake (the `Bokforing` SMB share)

Files dropped into `/srv/appdata/bok/dropzone` are picked up by a scanner
thread in `bok-api` every 60 seconds, booked, and moved into `_Inläst/`. That
directory is exported over SMB, so the batch path is: mount the share in
Finder or Explorer, drag in forty receipts, walk away.

```
smb://hubbabubba/Bokforing        (macOS)
\\hubbabubba\Bokforing            (Windows)
```

The share is hidden from the server's share list (`browseable: false`), so
connect to it by exact name.

### The split with hubbabubba

The share is **not** created by this repo. It is declared in
`e9wikner/hubbabubba` — `file_shares` in `ansible/inventory/group_vars/all.yml`,
documented in `docs/samba.md` §3 "Application shares" — and applied with
`python scripts/install.py --tags samba`. That is the same boundary every stack
on that host uses (`docs/podman.md` §4): the host repo prepares, the project
deploys. `deploy.sh` refuses to run if the directory is missing or unwritable,
and names what to fix.

Two things must hold on that side, or nothing here works:

- **The directory exists**, at `/srv/appdata/bok/dropzone`. Deliberately not
  under `/srv/storage`: that pool is three spinning disks that hubbabubba puts
  into standby after 30 minutes, and a 60-second scan there would keep waking
  them. `/srv/appdata` is NVMe, and is already snapshotted and backed up.
- **A POSIX ACL grants `e9wikner`** (`host_acl` in the share declaration).
  `bok-api` runs rootless with `UserNS=keep-id`, so the container's root *is*
  that account on the host. Without the grant the scanner cannot move a file —
  and a full `Kvitton/` looks identical whether the scanner is stuck or nobody
  has dropped anything.

### The folder contract

`deploy.sh` creates these; the names are the classification:

```
Kvitton/                        kvitto
Leverantörsfakturor/            leverantörsfaktura
Kundfakturor/                   kundfaktura
Utlägg/                         utlägg
Övrigt/                         annat
Kontoutdrag/1930 Företagskonto/ kontoutdrag för konto 1930
SIE4-import/                    hel årsexport, bokförs direkt
_Inläst/2026-09/                ← inlästa filer flyttas hit
_Problem/                       ← avvisade filer, med .txt som förklarar
```

Names match case- and NFC/NFD-insensitively, so a folder created on a Mac
works. More statement folders need no code or config change — `mkdir
"Kontoutdrag/1630 Skattekonto"`, as long as account 1630 is in the chart of
accounts. A file in the root or an unknown folder is read without a type and
classified by the agent; a `.txt` is always sidecar metadata, never a document.

Files are never deleted, only moved. A file still being written is left alone
until it has been quiet for `DROPZONE_QUIET_SECONDS` (30 here, up from the
10-second default: SMB writes straight to the final filename, so that timer is
the only guard against reading a half-copied PDF).

### Checking it is alive

```bash
curl -fsS -H "Authorization: Bearer $BOKFOERING_API_KEY" \
  http://hubbabubba:8000/api/v1/intake/dropzone/status
```

Reports when the scan last ran, how many files are waiting, how many are in
`_Problem/`, and any `Kontoutdrag/` folder whose account code is unknown. The
same information is on the intake page in the web UI, which warns when the
scanner has stopped. `deploy.sh` prints it at the end of every deploy.

If the share is fine but nothing is picked up:

```bash
getfacl -p /srv/appdata/bok/dropzone      # expect user:e9wikner:rwx
systemctl --user status bok-api.service
journalctl --user -u bok-api.service | grep -i dropzone
```

## Rotate a secret

Edit `/srv/appdata/bok/bok.env` and `systemctl --user restart bok-api.service`.

## Config knobs

The quadlets hardcode ports `8000` (API) and `3000` (frontend), the `admin`
username, and the dropzone settings (`DROPZONE_ENABLED`, `DROPZONE_DIR`,
`DROPZONE_QUIET_SECONDS`). Removing the `DROPZONE_ENABLED` line turns folder
intake off and makes the share preflight moot; the web upload stays either way. Change them by editing the `.container` files here and
re-running `deploy.sh`. There is intentionally no TLS / reverse proxy layer —
that matches every other service on hubbabubba.
