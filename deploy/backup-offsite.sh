#!/bin/bash
# Copy the newest verified backup to somewhere that is NOT this machine, check the copy, and keep the last few there.
#   deploy/backup-offsite.sh                  # run it after deploy/backup-postgres.sh (see deploy/crontab.docker.example)
#   OFFSITE_DRY_RUN=1 deploy/backup-offsite.sh   # shows what it would do and copies nothing
#
# Settings come from environment variables, or from a file of VAR=value lines (never committed): $OFFSITE_ENV_FILE, default
# $HOME/.stillopen-offsite.env. A documented template is deploy/offsite.env.example. The important ones:
#   OFFSITE_METHOD   rclone (preferred) | rsync | scp                 default rclone
#   OFFSITE_REMOTE   rclone: "myremote:stillopen-backups"   rsync/scp: "user@host:/path/to/folder"
#   OFFSITE_KEEP     how many copies to keep at the remote            default 7
#   BACKUP_DIR       where backup-postgres.sh writes                  default ~/stillopen-backups
#   OFFSITE_INCLUDE_SECRET_KEY=1   also copy the app's secret key (needed to read stored API keys after a restore). Only do this
#                                  to a remote you encrypt (an rclone "crypt" remote) or fully trust.
#   OFFSITE_INCLUDE_MEDIA=1        also copy an archive of uploaded files (Docker setup; needs DOCKER and the compose files below)
#   OFFSITE_RCLONE   the rclone command if it is not on PATH       default rclone
#   OFFSITE_SSH_KEY  rsync/scp: path to a private key file (a path only, the key itself is never read or printed)
# Credentials live in rclone's own config or in your ssh key; this script never reads, prints or logs one.
# Exit status is non-zero if anything failed (no dump, the copy is missing or differs, a tool is absent), so cron can tell you.
set -eu
set +x
cd "$(dirname "$0")/.."

ENV_FILE="${OFFSITE_ENV_FILE:-$HOME/.stillopen-offsite.env}"
if [ -f "$ENV_FILE" ]; then
  # Only plain VAR=value lines are accepted (no commands run from the file).
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}   # a file saved on Windows has CRLF line ends
    case "$line" in
      ''|'#'*) continue ;;
      OFFSITE_[A-Z_]*=*|BACKUP_DIR=*|DOCKER=*|COMPOSE_FILES=*) key=${line%%=*}; val=${line#*=}; val=${val%\"}; val=${val#\"}
        # an environment variable that is already set wins over the file
        if [ -z "$(printenv "$key" 2>/dev/null || true)" ]; then export "$key=$val"; fi ;;
      *) echo "offsite: ignoring an unrecognised line in $ENV_FILE" >&2 ;;
    esac
  done < "$ENV_FILE"
fi

METHOD="${OFFSITE_METHOD:-rclone}"
REMOTE="${OFFSITE_REMOTE:-}"
KEEP="${OFFSITE_KEEP:-7}"
DIR="${BACKUP_DIR:-$HOME/stillopen-backups}"
DRY="${OFFSITE_DRY_RUN:-0}"
DOCKER="${DOCKER:-docker}"
RCLONE="${OFFSITE_RCLONE:-rclone}"   # the rclone command (a path works too)
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.selfhost.yml -f docker-compose.postgres.yml}"

log() { echo "$(date -u +%FT%TZ) offsite: $*"; }
fail() { echo "$(date -u +%FT%TZ) offsite: FAILED: $*" >&2; exit 1; }

case "$KEEP" in ''|*[!0-9]*) fail "OFFSITE_KEEP must be a whole number" ;; esac
[ "$KEEP" -ge 1 ] || fail "OFFSITE_KEEP must be at least 1"
case "$METHOD" in rclone|rsync|scp) ;; *) fail "OFFSITE_METHOD must be rclone, rsync or scp" ;; esac
[ -n "$REMOTE" ] || fail "OFFSITE_REMOTE is not set (see deploy/offsite.env.example)"
[ -d "$DIR" ] || fail "no backup folder at $DIR (run deploy/backup-postgres.sh first)"

# The newest dump that backup-postgres.sh finished (it only renames a dump into place after pg_restore --list read it back).
LATEST=$(ls -1t "$DIR"/stillopen-*.dump "$DIR"/stillopen-*.sqlite3 2>/dev/null | head -n 1 || true)
[ -n "$LATEST" ] && [ -s "$LATEST" ] || fail "no backup file found in $DIR"
NAME=$(basename "$LATEST")
SIZE=$(wc -c < "$LATEST" | tr -d ' ')

FILES=("$LATEST")
STAGE=""
cleanup() { [ -n "$STAGE" ] && rm -rf "$STAGE"; return 0; }
trap cleanup EXIT

if [ "${OFFSITE_INCLUDE_SECRET_KEY:-0}" = "1" ]; then
  [ -s "$DIR/secret_key" ] || fail "OFFSITE_INCLUDE_SECRET_KEY=1 but there is no $DIR/secret_key"
  FILES+=("$DIR/secret_key")
fi

if [ "${OFFSITE_INCLUDE_MEDIA:-0}" = "1" ] && [ "$DRY" != "1" ]; then
  umask 077
  STAGE=$(mktemp -d)
  MEDIA="$STAGE/stillopen-media-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
  # shellcheck disable=SC2086
  $DOCKER compose $COMPOSE_FILES exec -T stillopen sh -c 'cd /data && tar -czf - media 2>/dev/null' > "$MEDIA" || fail "could not archive the media folder"
  tar -tzf "$MEDIA" > /dev/null || fail "the media archive could not be read back"
  FILES+=("$MEDIA")
fi

if [ "$DRY" = "1" ]; then
  log "DRY RUN (method $METHOD, keep $KEEP): nothing is copied or deleted"
  for f in "${FILES[@]}"; do log "would copy $(basename "$f") ($(wc -c < "$f" | tr -d ' ') bytes) to $REMOTE"; done
  [ "${OFFSITE_INCLUDE_MEDIA:-0}" = "1" ] && log "would also archive and copy the media folder"
  log "would then check size and checksum at the remote and delete all but the newest $KEEP stillopen-* copies there"
  exit 0
fi

sha_of() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=yes)
[ -n "${OFFSITE_SSH_KEY:-}" ] && SSH_OPTS+=(-i "$OFFSITE_SSH_KEY")

if [ "$METHOD" = "rclone" ]; then
  command -v "$RCLONE" >/dev/null 2>&1 || fail "rclone is not installed (https://rclone.org/install/), or choose OFFSITE_METHOD=rsync"
  for f in "${FILES[@]}"; do
    "$RCLONE" copyto --quiet "$f" "$REMOTE/$(basename "$f")" || fail "rclone could not copy $(basename "$f")"
  done
  for f in "${FILES[@]}"; do
    b=$(basename "$f")
    # rclone check compares hashes where the remote has them and sizes where it does not; non-zero when they differ
    "$RCLONE" check --quiet --one-way --include "/$b" "$(dirname "$f")" "$REMOTE" >/dev/null 2>&1 || fail "the copy of $b at the remote does not match the original"
  done
  # keep the newest $KEEP copies of each kind
  for pattern in 'stillopen-*.dump' 'stillopen-*.sqlite3' 'stillopen-media-*.tar.gz'; do
    old=$("$RCLONE" lsf --files-only --include "$pattern" "$REMOTE" 2>/dev/null | sort -r | tail -n +"$((KEEP + 1))" || true)
    [ -n "$old" ] && while IFS= read -r gone; do "$RCLONE" deletefile --quiet "$REMOTE/$gone" || log "could not remove old copy $gone"; done <<< "$old"
  done
else
  case "$REMOTE" in *:*) ;; *) fail "OFFSITE_REMOTE must look like user@host:/path for $METHOD" ;; esac
  HOST=${REMOTE%%:*}
  RPATH=${REMOTE#*:}
  command -v ssh >/dev/null 2>&1 || fail "ssh is not installed"
  if [ "$METHOD" = "rsync" ]; then
    command -v rsync >/dev/null 2>&1 || fail "rsync is not installed, or choose OFFSITE_METHOD=scp"
    for f in "${FILES[@]}"; do rsync -a --checksum -e "ssh ${SSH_OPTS[*]}" "$f" "$REMOTE/" >/dev/null || fail "rsync could not copy $(basename "$f")"; done
  else
    command -v scp >/dev/null 2>&1 || fail "scp is not installed"
    for f in "${FILES[@]}"; do scp -q "${SSH_OPTS[@]}" "$f" "$REMOTE/" || fail "scp could not copy $(basename "$f")"; done
  fi
  for f in "${FILES[@]}"; do
    b=$(basename "$f")
    local_sum=$(sha_of "$f")
    remote_sum=$(ssh "${SSH_OPTS[@]}" "$HOST" "sha256sum '$RPATH/$b' 2>/dev/null | cut -d' ' -f1" || true)
    [ -n "$remote_sum" ] || fail "could not read $b back from the remote"
    [ "$local_sum" = "$remote_sum" ] || fail "the copy of $b at the remote does not match the original"
  done
  ssh "${SSH_OPTS[@]}" "$HOST" "cd '$RPATH' && for p in 'stillopen-*.dump' 'stillopen-*.sqlite3' 'stillopen-media-*.tar.gz'; do ls -1 \$p 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) | while read -r gone; do rm -f -- \"\$gone\"; done; done" || log "could not remove old copies"
fi

log "ok: $NAME ($SIZE bytes) copied to $REMOTE and verified; keeping the newest $KEEP"
