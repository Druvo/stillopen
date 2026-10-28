#!/bin/sh
# Container entrypoint: make sure there is a secret key, bring the database up to date, then run the command (gunicorn by default).
#
#   DJANGO_SECRET_KEY      set it yourself, or leave it empty and a key is generated once and kept in $STILLOPEN_DATA_DIR/.secret_key
#   STILLOPEN_SKIP_MIGRATE=1   do not run `migrate` on start (when something else does it)
set -e

DATA="${STILLOPEN_DATA_DIR:-/data}"

if [ -z "$DJANGO_SECRET_KEY" ]; then
  if [ ! -f "$DATA/.secret_key" ]; then
    mkdir -p "$DATA"
    (umask 077 && python -c "import secrets; print(secrets.token_urlsafe(64))" > "$DATA/.secret_key")
  fi
  DJANGO_SECRET_KEY="$(cat "$DATA/.secret_key")"
  export DJANGO_SECRET_KEY
fi

if [ "$STILLOPEN_SKIP_MIGRATE" != "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
