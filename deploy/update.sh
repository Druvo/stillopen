#!/usr/bin/env bash
# Update a StillOpen install to the latest code: git pull, rebuild/restart (Docker) or migrate (Python install).
#   deploy/update.sh              Docker Compose install (docker-compose.selfhost.yml), the default when docker is found
#   deploy/update.sh --source     Python install: pip install, migrate, build the app; you restart the server yourself
#   deploy/update.sh --dry-run    only print what would be done
#   deploy/update.sh --yes        do not ask first
# Refuses to run when you have uncommitted changes. Back up first: docs/SELF-HOSTING.md#backups
set -euo pipefail

mode=auto
dry=0
yes=0
for arg in "$@"; do
  case "$arg" in
    --source) mode=source ;;
    --docker) mode=docker ;;
    --dry-run) dry=1 ;;
    --yes | -y) yes=1 ;;
    -h | --help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
compose_file=docker-compose.selfhost.yml

if [ -n "$(git status --porcelain)" ]; then
  echo "You have uncommitted changes. Commit or stash them first, then run this again:" >&2
  git status --short >&2
  exit 1
fi

if [ "$mode" = auto ]; then
  if command -v docker >/dev/null 2>&1 && [ -f "$compose_file" ]; then mode=docker; else mode=source; fi
fi

if [ "$mode" = docker ]; then
  steps=("git pull --ff-only" "docker compose -f $compose_file up -d --build   # migrations run on start")
else
  steps=("git pull --ff-only" "python -m pip install -r requirements.txt" "python manage.py migrate --noinput" "(cd frontend && pnpm install --frozen-lockfile && pnpm build)" "then restart the server (systemd: sudo systemctl restart stillopen)")
fi

echo "StillOpen update ($mode install). This will run, in $(pwd):"
printf '  - %s\n' "${steps[@]}"
echo "Read CHANGELOG.md first, and take a backup (docs/SELF-HOSTING.md)."
if [ "$dry" = 1 ]; then echo "Dry run: nothing was changed."; exit 0; fi
if [ "$yes" != 1 ]; then
  read -r -p "Go ahead? [y/N] " answer
  case "$answer" in y | Y | yes) ;; *) echo "Cancelled."; exit 1 ;; esac
fi

git pull --ff-only
if [ "$mode" = docker ]; then
  docker compose -f "$compose_file" up -d --build
else
  python -m pip install -r requirements.txt
  python manage.py migrate --noinput
  (cd frontend && pnpm install --frozen-lockfile && pnpm build)
  echo "Done. Restart the server now."
fi
echo "Updated to $(git rev-parse --short HEAD)."
