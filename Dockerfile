# The whole app in one image: Django + gunicorn + WhiteNoise, with the signed-in app (frontend/) built in.
#
#   docker build -t stillopen .
#   docker run -p 8000:8000 -v stillopen_data:/data stillopen
#
# Config is by environment variables (see docs/INSTALL.md and docs/SELF-HOSTING.md). Your data lives in /data: the SQLite database,
# uploads and the generated secret key. Set DATABASE_URL to use PostgreSQL instead.

# Stage 1: build the signed-in app (a static export). Node is only here; the final image has none.
FROM node:22-alpine AS frontend
WORKDIR /frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# Stage 2: the Python image that runs it.
FROM python:3.12-slim
LABEL org.opencontainers.image.title="StillOpen" \
      org.opencontainers.image.description="A job-search tracker you host yourself." \
      org.opencontainers.image.source="https://github.com/Druvo/stillopen" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 STILLOPEN_DB=/data/db.sqlite3 STILLOPEN_MEDIA=/data/media STILLOPEN_DATA_DIR=/data
WORKDIR /app
COPY requirements-hosting.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-hosting.txt
COPY . .
COPY --from=frontend /frontend/out /app/frontend/out
RUN chmod +x /app/deploy/docker-entrypoint.sh \
 && DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput
# Run as an ordinary user, not root. /data is where the database, uploads and secret key live: mount a volume there.
# (A bind-mounted host folder must be writable by uid 10001.)
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app:app /app /data
USER app
VOLUME /data
EXPOSE 8000
# 127.0.0.1 is always an allowed host (see settings.py), whatever DJANGO_ALLOWED_HOSTS says.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/robots.txt', timeout=5)"
ENTRYPOINT ["sh", "/app/deploy/docker-entrypoint.sh"]
# One worker with threads: the per-person rate limits live in process memory, so all requests must share one process.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "16", "--timeout", "180"]
