# Stage 1: build the new app (a static export). Node is only here; the final image has none.
FROM node:22-alpine AS frontend
WORKDIR /frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-hosting.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-hosting.txt
COPY . .
COPY --from=frontend /frontend/out /app/frontend/out
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput
# Run as an ordinary user, not root. /data is where the self-host compose file keeps the database, uploads and secret key.
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app:app /app /data
USER app
EXPOSE 8000
# One worker with threads: the per-person rate limits live in process memory, so all requests must share one process.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 16 --timeout 180"]
