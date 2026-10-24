# Self-hosting StillOpen

StillOpen is free, open-source software (Apache-2.0) built to be run by you. This guide gets you from nothing to a working
instance, then covers email, putting it on the internet, backups and updates. For the longer operator checklist (shared service
for many people, public job board rules) see [HOSTING.md](HOSTING.md).

## Why run it yourself

- **Your data stays yours.** Your CV, notes and applications live in a database on your own machine or server. Nobody else can read them, and there is
  no account with a company to lose.
- **No lock-in, no price.** No subscription, no per-seat fee, no trial. You can export everything or delete everything from the Profile page.
- **You can read every line.** The code is public; nothing is hidden in a service you cannot inspect.
- **No third parties in the page.** No tracking, no ads, no external fonts or scripts. The only outside requests the server makes are the ones you can see below.

## What you need

- Either **Docker** (recommended) or **Python 3.12+**.
- About **512 MB of memory** and a few hundred MB of disk. SQLite is the default database, which is plenty for one person or a small group;
  PostgreSQL is supported for a shared service.
- A computer that is on when you want jobs refreshed. A small VPS or a home server is ideal; a laptop works for personal use.

## Option A: Docker (about five minutes)

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
docker compose -f docker-compose.selfhost.yml up -d --build
docker compose -f docker-compose.selfhost.yml exec stillopen python manage.py createsuperuser
```

Open <http://localhost:8000> (the admin is at `/admin/`). The first start creates the database, adds about 120 job sources and generates a
secret key that is kept in the Docker volume, so nothing needs configuring and you stay signed in across restarts and updates.

Everything you add lives in the `stillopen_data` volume (database, uploads, secret key). If a port is taken, set `STILLOPEN_PORT=9000` in `.env`
(on Windows, some ranges around 8000 are reserved by the system and refuse connections; pick another).

## Option B: Python directly

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # add -r requirements-mcp.txt for the MCP server, -r requirements-ai.txt for the Agent SDK provider
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

`runserver` is for trying it out. To keep it running, use gunicorn the way the `Dockerfile` does (one worker with 16 threads: per-person rate limits
live in process memory) behind a reverse proxy, with `DJANGO_DEBUG=0` and `DJANGO_SECRET_KEY` set.

## First ten minutes as the owner

1. Sign in at `/admin/` with the account you created. Under **Site configuration**:
   - **Registration**: leave it *Closed* for personal use, or set it to *Open* to let others sign up (read the checklist in [HOSTING.md](HOSTING.md) first).
   - **Landing page** and **Public job board**: the text visitors see, an on/off switch, and a contact email for employers who want a listing removed.
   - **Legal**: the privacy and terms text. Fill in the `[bracketed parts]` and have it reviewed for your country before you let other people sign up.
2. Open `/` and sign in as yourself. Answer the three welcome questions (roles, where you could work, your CV). A search starts by itself and your first
   jobs appear in about a minute. No AI key is needed.
3. Optional: **AI settings** to bring your own key for a deeper read of a job. Nothing is sent to an AI until you press a button that needs one.

## Sign-in options

**Two-step sign-in** is built in and free: each person can switch it on under Profile > Your account > Two-step sign-in. It supports an authenticator
app (Google Authenticator, Aegis, 1Password...), a hardware security key, and one-time recovery codes. Nothing to configure.

**Sign in with Google, GitHub or Facebook** is free too, but each needs an OAuth app that you create with the provider. The redirect (callback) address to give the provider is `https://jobs.example.com/accounts/google/login/callback/`, with your own domain, and
`github` or `facebook` in place of `google` for the others.

| Provider | Where to create the app | Notes |
| --- | --- | --- |
| Google | Google Cloud Console > APIs & Services > Credentials > OAuth client ID (Web application) | Verified emails only |
| GitHub | GitHub > Settings > Developer settings > OAuth Apps | The app asks for the person's verified email; only a verified one is trusted |
| Facebook | developers.facebook.com > Create app > Facebook Login | The app must be switched to Live and have a privacy policy URL (use `/privacy/`). Facebook's email is not treated as verified, so a new person confirms it with the usual email link and is never attached to an existing account |

Put the keys in `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and the `GITHUB_` and `FACEBOOK_` ones), restart, then in the admin under
**Site configuration > Social sign-in** tick the providers you want. While sign-up is *Closed*, only emails on the allowed list may use a social button;
with sign-up *Open*, anyone with a usable email may.

## Email

Without email set up, you can still use everything: sign-ups are not email-confirmed (the admin shows a notice) and reminders only print to the server log.
To send real email, set these in `.env` (copy `.env.example`):

```
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=StillOpen <jobs@example.com>
```

Then check it: `docker compose -f docker-compose.selfhost.yml exec stillopen python manage.py check_email --to you@example.com`
(without Docker: `python manage.py check_email --to you@example.com`). It prints the settings (never the password) and sends one test message.

## Scheduled jobs (optional)

None are required: a person's search runs when they open the dashboard, and the public job board refreshes itself when a visitor arrives and it is stale.
Schedule these only for emails and always-fresh data: interview reminders, follow-up emails, job alerts, board refresh. Ready-made files:
[`deploy/crontab.example`](../deploy/crontab.example) (Linux/macOS) and [`deploy/windows/schedule-stillopen.ps1`](../deploy/windows/schedule-stillopen.ps1) (Windows).
With Docker, run the same commands through `docker compose ... exec -T stillopen python manage.py <command>`.

## Putting it on the internet

Do **not** expose the app directly over plain HTTP. Put a TLS-terminating reverse proxy in front.

**Easiest with Docker:** add a third file that runs [Caddy](https://caddyserver.com), which gets and renews the certificate by itself. Point your domain's A record at
the machine, open ports 80 and 443, put the lines from the top of `docker-compose.caddy.yml` in `.env`, and run:

```bash
docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml -f docker-compose.caddy.yml up -d --build
```

(Leave out the postgres file to stay on SQLite.) **Your own proxy instead:** with Caddy on the host, for example:

```
jobs.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then, in `.env`:

```
DJANGO_ALLOWED_HOSTS=jobs.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://jobs.example.com
DJANGO_HTTPS=1
DJANGO_BEHIND_PROXY=1
ALLAUTH_TRUSTED_PROXY_COUNT=1
```

and restart. The compose file publishes only on `127.0.0.1`, so the proxy is the only way in. `ALLAUTH_TRUSTED_PROXY_COUNT=1` makes the per-IP sign-up limits see visitors rather than the proxy.
Before you open registration to other people, run through the checklist in [HOSTING.md](HOSTING.md): email that works, completed legal text, schedules, and (if you show the public job board) the rules about which sources may be shown.

## What leaves your server

| What | When | Where it goes |
| --- | --- | --- |
| Reads of public job lists | When a search runs or the board refreshes | Employers' hiring pages and the open job feeds you have enabled. Nothing about a person is sent |
| Job titles and a country name | Only if you add a Jooble key | Jooble, to search on a person's behalf. Never a name, email or CV |
| Job text, preferences and relevant CV passages | Only when a person presses a button that needs AI, and has set up their own key | The AI provider that person chose |
| Email | Confirmations and the reminders people switch on | Your SMTP server |

Posting pages a person pastes are fetched through a guard that refuses private and internal addresses.

## PostgreSQL (optional)

SQLite is the default and is right for one person or a handful. Choose PostgreSQL when many people share one instance: SQLite lets only one
write happen at a time, and a search saves thousands of rows while others browse. Searches are not faster on PostgreSQL (they wait on
the network, not the database).

**New install with Docker:** add a database password to `.env` (letters and digits only, e.g. from `openssl rand -hex 24`) and use both files:

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >> .env
docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml up -d --build
```

**Without Docker:** `pip install -r requirements-hosting.txt`, create an empty database, then set
`DATABASE_URL=postgres://user:password@host:5432/stillopen`.

**Moving an existing SQLite install over:** stop the old app, start the PostgreSQL stack (above), then copy the old file in and run the copy.
Keep the same secret key (`DJANGO_SECRET_KEY`), or stored API keys cannot be decrypted.

```bash
# Docker: the old file is db.sqlite3 (or /data/db.sqlite3 in the old volume)
docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml cp ./db.sqlite3 stillopen:/tmp/old.sqlite3
docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml exec stillopen python manage.py copy_to_postgres --from /tmp/old.sqlite3 --replace
# Python install, with DATABASE_URL set:
python manage.py copy_to_postgres --from db.sqlite3
```

It builds the tables, loads everyone's data and checks every table has the same row count. The SQLite file is only read. People sign in again
(sessions are not copied). A large database takes a few minutes. `--replace` erases a PostgreSQL database that already has accounts.
Back up with `pg_dump -Fc` from then on.

## Backups

Back up the database (and, with Docker, the volume). It holds everyone's data, so treat backups like the data.

```bash
# Docker + SQLite: a consistent copy while it is running, then take it out of the container
docker compose -f docker-compose.selfhost.yml exec stillopen python -c "import sqlite3; s = sqlite3.connect('/data/db.sqlite3'); d = sqlite3.connect('/data/backup.sqlite3'); s.backup(d)"
docker compose -f docker-compose.selfhost.yml cp stillopen:/data/backup.sqlite3 ./stillopen-backup.sqlite3

# Python install: the file is db.sqlite3 next to manage.py (stop the app, or use the sqlite3 backup command), plus the media/ folder
# PostgreSQL: pg_dump -Fc stillopen > stillopen.dump
```

Keep the secret key (`DJANGO_SECRET_KEY`, or `/data/.secret_key` in the Docker volume) with the backup: stored API keys cannot be decrypted without it.
To restore, put the file back and start the app.

## Updating

```bash
git pull
docker compose -f docker-compose.selfhost.yml up -d --build      # Python install: pip install -r requirements.txt && python manage.py migrate, then restart
```

Migrations run on start. Read [CHANGELOG.md](../CHANGELOG.md) first. The image now runs as an ordinary user (uid 10001); if you are updating a volume created by an older
image that ran as root, give it to that user once: `docker compose -f docker-compose.selfhost.yml run --rm --user root stillopen chown -R 10001:10001 /data`.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Port already in use, or "forbidden by its access permissions" on Windows | Set `STILLOPEN_PORT` to another number (avoid ranges the system reserves) |
| Can sign in locally but not on your domain | `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` must name your domain; with HTTPS also `DJANGO_HTTPS=1` and `DJANGO_BEHIND_PROXY=1` |
| Signed in over plain http but the session does not stick | `DJANGO_HTTPS=1` makes cookies secure-only; use `0` only for plain-http testing on your own machine |
| No jobs appear | Check the person has a target role or a CV and that Job sources are not all paused; the dashboard's scan log shows each source's result |
| Search is slow the first time | About a minute is normal while about 120 sources are read; later searches reuse a six-hour cache |
| Emails do not arrive | `python manage.py check_email --to you@example.com`; then your provider's logs and spam folder |
| Public board is empty | `python manage.py refresh_postings`; make sure some sources are ticked *Show publicly* |

## Uninstalling

`docker compose -f docker-compose.selfhost.yml down -v` removes the container **and the data volume**. Export what you want to keep first
(Profile > Your data > export).

## Contributing and getting help

Questions and bugs: open an issue. Security problems: see [SECURITY.md](../SECURITY.md). Code: see [CONTRIBUTING.md](../CONTRIBUTING.md).
