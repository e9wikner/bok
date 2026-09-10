#!/usr/bin/env bash
#
# Deploy Bok on the home server "hubbabubba" as two rootless Podman quadlets
# (bok-api, bok-frontend). Run this AS e9wikner, on the box. No sudo is needed
# after the one-time setup below.
#
#   ssh hubbabubba
#   ~/Development/bok/deploy/hubbabubba/deploy.sh
#
# ── One-time setup (run once, in an admin/rsw shell) ──────────────────────
#   sudo mkdir -p /srv/appdata/bok/data
#   sudo chown e9wikner:e9wikner /srv/appdata/bok /srv/appdata/bok/data
#   sudo -u e9wikner install -m 600 /dev/null /srv/appdata/bok/bok.env
#   # then edit /srv/appdata/bok/bok.env — see README.md in this directory
#
# NOT `chown -R`: /srv/appdata/bok/dropzone is an SMB share owned by the file
# server (rsw:rsw 2770, with a POSIX ACL granting e9wikner). Taking ownership of
# it would be undone by hubbabubba's daily permission check the next morning.
#
# Options:
#   --no-build     skip the image builds, just re-render quadlets and restart
#   --force-build  build even if the source did not change
#   --no-pull      deploy the checkout in $SRC as it stands, without git pull
#                  (for trying a commit before it is pushed; always rebuilds)
#
set -euo pipefail

APPDATA=/srv/appdata/bok
DROPZONE=$APPDATA/dropzone
ENV_FILE=$APPDATA/bok.env
SRC=$APPDATA/src
REPO=https://github.com/e9wikner/bok.git
QUADLET_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/containers/systemd
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

BUILD=auto
PULL=yes
for arg in "$@"; do
  case "$arg" in
    --no-build)    BUILD=no ;;
    --force-build) BUILD=force ;;
    --no-pull)     PULL=no ;;
    -h|--help)     sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

fail() { echo "error: $*" >&2; exit 1; }

[ "$(id -un)" = "e9wikner" ] || fail "run this as e9wikner, not $(id -un)"
command -v podman >/dev/null || fail "podman not found — run the hubbabubba 'podman' role first"

# ── preflight: one-time setup must have happened ─────────────────────────
if [ ! -d "$APPDATA" ] || [ ! -w "$APPDATA" ]; then
  cat >&2 <<EOF
$APPDATA is missing or not writable by e9wikner.

One-time setup, in an admin (rsw) shell:
  sudo mkdir -p $APPDATA/data
  sudo chown e9wikner:e9wikner $APPDATA $APPDATA/data
  sudo -u e9wikner install -m 600 /dev/null $ENV_FILE

then fill in $ENV_FILE (see $SCRIPT_DIR/README.md) and re-run this script.
EOF
  exit 1
fi

[ -f "$ENV_FILE" ] || fail "$ENV_FILE missing — see $SCRIPT_DIR/README.md"
if grep -qE '^(BOKFOERING_API_KEY|JWT_SECRET|AUTH_PASSWORD)=("")?$' "$ENV_FILE" ||
   grep -q 'CHANGE_ME' "$ENV_FILE"; then
  fail "$ENV_FILE has unset or placeholder values — fill in all three secrets"
fi
chmod 600 "$ENV_FILE"

mkdir -p "$APPDATA/data" "$QUADLET_DIR"

# ── preflight: the dropzone share must exist and be writable ─────────────
# bok-api.container sets DROPZONE_ENABLED=true, so a missing or unwritable
# dropzone is not a degraded deploy — it is a scanner logging
# `dropzone_dir_missing` every 60 seconds while receipts pile up in a folder
# nobody is reading. Fail here, naming the check, rather than start like that.
#
# The directory is the `Bokforing` SMB share, declared and owned by hubbabubba
# (file_shares in group_vars/all.yml; docs/samba.md §3 "Application shares").
# This repo never creates or chowns it — it only asserts the host preparation
# it depends on actually holds, the same contract homeass and telldus use.
if [ ! -d "$DROPZONE" ]; then
  cat >&2 <<EOF
error: $DROPZONE does not exist.

It is the 'Bokforing' SMB share, declared in the hubbabubba repo:
  ansible/inventory/group_vars/all.yml  ->  file_shares
Apply it on this host with:
  python scripts/install.py --tags samba

To deploy without folder intake instead, remove the DROPZONE_ENABLED line
from $SCRIPT_DIR/bok-api.container.
EOF
  exit 1
fi

if [ ! -w "$DROPZONE" ] || [ ! -x "$DROPZONE" ]; then
  cat >&2 <<EOF
error: $DROPZONE is not writable by $(id -un).

The share grants this account through a POSIX ACL, not ownership. Check it:
  getfacl -p $DROPZONE     # expect user:$(id -un):rwx and default:user:$(id -un):rwx

If it is missing, the grant is not declared (or has drifted). In the hubbabubba
repo the share needs:
  host_acl:
    - { etype: user, entity: "{{ dev_user }}", permissions: rwx }
then: sudo /usr/local/lib/hubbabubba/permissions.py --fix
EOF
  exit 1
fi

# The folder contract the scanner reads (services/dropzone.py). Creating them is
# this repo's job, not the file server's: the names ARE the classification.
# Folder names are matched case- and NFC/NFD-insensitively, so a folder created
# on a Mac works too. Add more account statement folders the same way —
# `Kontoutdrag/<account> <label>/`, no code or config change needed.
echo "==> ensuring the dropzone folder contract in $DROPZONE"
for folder in Kvitton Leverantörsfakturor Kundfakturor Utlägg Övrigt               "Kontoutdrag/1930 Företagskonto" SIE4-import; do
  mkdir -p "$DROPZONE/$folder"
done

# ── source ──────────────────────────────────────────────────────────────
changed=1
if [ "$PULL" = no ]; then
  [ -d "$SRC/.git" ] || fail "--no-pull needs an existing checkout at $SRC"
  echo "==> --no-pull: deploying $SRC as-is at $(git -C "$SRC" rev-parse --short HEAD)"
  git -C "$SRC" --no-pager log -1 --oneline
elif [ -d "$SRC/.git" ]; then
  echo "==> updating $SRC"
  before=$(git -C "$SRC" rev-parse HEAD)
  git -C "$SRC" pull --ff-only
  after=$(git -C "$SRC" rev-parse HEAD)
  [ "$before" = "$after" ] && changed=0 || true
else
  echo "==> cloning $REPO -> $SRC"
  git clone "$REPO" "$SRC"
fi

# ── build ───────────────────────────────────────────────────────────────
do_build=0
if [ "$BUILD" = force ]; then
  do_build=1
elif [ "$BUILD" = no ]; then
  do_build=0
elif [ "$changed" = 1 ]; then
  do_build=1
elif ! podman image exists bok-api:latest || ! podman image exists bok-frontend:latest; then
  do_build=1
fi

if [ "$do_build" = 1 ]; then
  for img in bok-api bok-frontend; do
    if podman image exists "$img:latest"; then
      podman tag "$img:latest" "$img:previous"
    fi
  done
  echo "==> building bok-api:latest"
  podman build -t bok-api:latest "$SRC"
  echo "==> building bok-frontend:latest"
  # BACKEND_URL is a build arg the frontend Dockerfile bakes into the Next.js
  # rewrites; under Network=host there is no `api` DNS name, so it must be
  # loopback. NEXT_PUBLIC_API_URL is left empty so the browser calls the same
  # origin and Next proxies /api + /health server-side.
  podman build -t bok-frontend:latest \
    --build-arg BACKEND_URL=http://127.0.0.1:8000 \
    "$SRC/frontend-v3"
else
  echo "==> source unchanged, skipping build (--force-build to override)"
fi

# ── quadlets ────────────────────────────────────────────────────────────
echo "==> installing quadlets into $QUADLET_DIR"
install -m 0644 "$SCRIPT_DIR/bok-api.container"      "$QUADLET_DIR/bok-api.container"
install -m 0644 "$SCRIPT_DIR/bok-frontend.container" "$QUADLET_DIR/bok-frontend.container"
systemctl --user daemon-reload

# ── (re)start ───────────────────────────────────────────────────────────
echo "==> restarting units"
systemctl --user restart bok-api.service
systemctl --user restart bok-frontend.service

# ── verify (best-effort; don't abort the script on a failed probe) ───────
set +e
echo "==> waiting for the API to answer"
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 1
done

printf 'api      '; curl -fsS  http://127.0.0.1:8000/health; echo
printf 'frontend '; curl -fsS  http://127.0.0.1:3000/health; echo
printf 'login    '; curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/login

db=$APPDATA/data/bokfoering.db
[ -f "$db" ] && printf 'db owner %s (want e9wikner:e9wikner)\n' "$(stat -c '%U:%G' "$db")"

# The classic folder-intake failure is a scanner that dies quietly: files pile
# up, everyone assumes they are queued, and nothing is booked. Print its status
# here so a deploy never ends without having looked.
api_key=$(sed -n 's/^BOKFOERING_API_KEY=//p' "$ENV_FILE" | head -1)
if [ -n "$api_key" ]; then
  printf 'dropzone '
  curl -fsS -H "Authorization: Bearer $api_key" \
    http://127.0.0.1:8000/api/v1/intake/dropzone/status || echo '(no answer)'
  echo
fi

echo
echo "done — UI at http://hubbabubba:3000, API at http://hubbabubba:8000"
