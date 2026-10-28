# Install StillOpen

Pick the way that fits you. All of them run the same app. For email, HTTPS, social sign-in, backups and updates read
[SELF-HOSTING.md](SELF-HOSTING.md); running it for many people is in [HOSTING.md](HOSTING.md).

| You have | Use |
| --- | --- |
| Docker and want the shortest path | [Docker Compose](#1-docker-compose-from-a-clone) |
| Docker and a published image | [Plain Docker](#2-plain-docker) |
| Python and Node, no Docker | [From source](#3-from-source-python-and-node) |
| An Ubuntu server, no Docker | [Ubuntu service](#4-ubuntu-server-as-a-service) |
| CapRover, Coolify or Dokploy | [Platform notes](#5-caprover-coolify-dokploy) |

Whatever you pick, **create an admin account** once it runs (`createsuperuser`, below) and sign in at `/admin/` to set the site up.

## What the container does

The `Dockerfile` builds the signed-in app with Node in a first stage, then runs Django under gunicorn (one worker, 16 threads, because
per-person rate limits live in process memory) with WhiteNoise serving the static files. The final image has no Node. It runs as a
non-root user (uid 10001) and listens on port 8000. On start, `deploy/docker-entrypoint.sh`:

- generates a secret key into `/data/.secret_key` if you did not set `DJANGO_SECRET_KEY`, so you stay signed in across restarts;
- runs `python manage.py migrate` (set `STILLOPEN_SKIP_MIGRATE=1` to skip it);
- starts gunicorn.

`/data` is the one folder to keep and back up: the SQLite database (`db.sqlite3`), uploads (`media/`) and the secret key. Set `DATABASE_URL`
(`postgres://user:password@host:5432/name`) to use PostgreSQL instead. The container has a health check (`/robots.txt` on 127.0.0.1).

Settings are environment variables. The ones you will most likely need:

| Variable | Meaning |
| --- | --- |
| `DJANGO_SECRET_KEY` | Optional. Leave unset to have one generated and kept in `/data`. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names you serve (`jobs.example.com`). Default is localhost only. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Your public address with scheme (`https://jobs.example.com`) when behind a proxy. |
| `DJANGO_HTTPS` | `1` once HTTPS is in front (secure cookies). |
| `DJANGO_BEHIND_PROXY` | `1` when a reverse proxy terminates TLS. Also set `ALLAUTH_TRUSTED_PROXY_COUNT=1` so rate limits see real visitor addresses. |
| `DATABASE_URL` | PostgreSQL instead of SQLite. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Outgoing email (or set it in the admin). |

The full list is in `.env.example` and `config/settings.py`.

## 1. Docker Compose, from a clone

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
docker compose -f docker-compose.selfhost.yml up -d --build
docker compose -f docker-compose.selfhost.yml exec stillopen python manage.py createsuperuser
```

Open <http://localhost:8000>. This builds the image on your machine and keeps everything in the `stillopen_data` volume. Add
`-f docker-compose.postgres.yml` for PostgreSQL and `-f docker-compose.caddy.yml` for automatic HTTPS (see the comments at the top of each file
and [SELF-HOSTING.md](SELF-HOSTING.md#putting-it-on-the-internet)). Update with `git pull` and the same `up -d --build`.

## 2. Plain Docker

Build the image yourself:

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
docker build -t stillopen .
docker run -d --name stillopen --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v stillopen_data:/data \
  -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
  stillopen
docker exec -it stillopen python manage.py createsuperuser
```

Or use a published image. The repository has a workflow (`.github/workflows/image.yml`) that pushes to `ghcr.io/<owner>/<repo>` when a version
tag such as `v1.0.0` is pushed. Nothing is published until the maintainer pushes such a tag, so check that the package exists first; then replace
`stillopen` in the `docker run` line above with `ghcr.io/<owner>/<repo>:<version>`. A host folder instead of a named volume must be writable by uid 10001.

## 3. From source (Python and Node)

You need Python 3.12 or later, and Node 22 or later with pnpm to build the app once.

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # or requirements-hosting.txt for PostgreSQL support
(cd frontend && pnpm install --frozen-lockfile && pnpm build)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Without the `pnpm build` step `/app/` shows a plain "not built" page. `runserver` is for trying it out; to keep it running use the next section's
gunicorn line.

## 4. Ubuntu server as a service

Do the "from source" steps in `/opt/stillopen` as a dedicated user (`sudo useradd --system --create-home --home-dir /opt/stillopen stillopen`),
and run `python manage.py collectstatic --noinput` once after each update (gunicorn comes with `requirements.txt`).
Then `/etc/systemd/system/stillopen.service`:

```ini
[Unit]
Description=StillOpen
After=network.target

[Service]
User=stillopen
WorkingDirectory=/opt/stillopen
EnvironmentFile=/opt/stillopen/.env
ExecStart=/opt/stillopen/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 1 --threads 16 --timeout 180
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`.env` holds `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY=<a long random string>`, `DJANGO_ALLOWED_HOSTS`, and the HTTPS lines from the table above.
Then `sudo systemctl enable --now stillopen` and put a TLS proxy (Caddy, nginx: see `deploy/Caddyfile` and `deploy/nginx.conf`) in front of port 8000.
Scheduled jobs are optional: [`deploy/crontab.example`](../deploy/crontab.example).

## 5. CapRover, Coolify, Dokploy

These platforms all build a repository's `Dockerfile` or run an image, and give you a domain with HTTPS. Only these settings are specific to StillOpen
(the exact screens differ per platform and version, so look for the matching option):

- **Build:** the repository root with the included `Dockerfile` (or the published image above). The container port is **8000**.
- **Persistent storage:** mount a volume at **`/data`**. Without it the database and secret key disappear when the container is replaced.
- **Environment variables:** `DJANGO_ALLOWED_HOSTS=<your domain>`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your domain>`, `DJANGO_HTTPS=1`,
  `DJANGO_BEHIND_PROXY=1`, `ALLAUTH_TRUSTED_PROXY_COUNT=1`. For PostgreSQL create a database on the platform and set `DATABASE_URL`.
- **One instance only:** keep a single replica, since rate limits are kept in process memory (or set `REDIS_URL`; see CHANGELOG).
- **Health check:** the image already has one; if the platform asks for a path, use `/robots.txt`.
- **First admin:** run `python manage.py createsuperuser` in the platform's terminal or exec feature for the container.

These notes describe what the image needs; they have not been tested on each platform.
