#!/bin/sh
# Nightly backup for the Docker + PostgreSQL setup (docker-compose.selfhost.yml + docker-compose.postgres.yml).
#   deploy/backup-postgres.sh                 # writes ~/stillopen-backups/stillopen-<UTC time>.dump
# Settings (environment): BACKUP_DIR (default ~/stillopen-backups), BACKUP_KEEP_DAYS (default 14), DOCKER (default docker).
# Also keeps one copy of the app's secret key: stored API keys cannot be decrypted without it.
# A backup on the same machine does not protect you if the machine is lost: copy BACKUP_DIR somewhere else too (rclone, rsync, a NAS).
# Restore:  docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml exec -T db pg_restore -U stillopen -d stillopen --clean --if-exists < FILE.dump
set -eu
cd "$(dirname "$0")/.."
DOCKER="${DOCKER:-docker}"
DIR="${BACKUP_DIR:-$HOME/stillopen-backups}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
FILES="-f docker-compose.selfhost.yml -f docker-compose.postgres.yml"
umask 077
mkdir -p "$DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DIR/stillopen-$STAMP.dump"
$DOCKER compose $FILES exec -T db pg_dump -U stillopen -Fc stillopen > "$OUT.tmp"
# a dump that cannot be read back is not a backup
$DOCKER compose $FILES exec -T db pg_restore --list < "$OUT.tmp" > /dev/null
mv "$OUT.tmp" "$OUT"
if [ ! -s "$DIR/secret_key" ]; then
  $DOCKER compose $FILES exec -T stillopen sh -c 'cat /data/.secret_key 2>/dev/null || true' > "$DIR/secret_key" || true
fi
find "$DIR" -name 'stillopen-*.dump' -mtime +"$KEEP" -delete
echo "$(date -u +%FT%TZ) backup ok: $OUT ($(wc -c < "$OUT") bytes)"
