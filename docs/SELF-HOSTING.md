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

## The app

Everything a signed-in person does is in the app at `/app/` (a board you can drag jobs across, and every other screen). Everyone gets it; there is no switch. The old page addresses (such as `/dashboard/`) redirect to it.

1. Docker: nothing to install. The image build compiles it, and the running image has no Node.
2. Python directly: build it once with Node 22 or later and pnpm (`cd frontend && pnpm install && pnpm build`), which writes `frontend/out/`. Without that folder `/app/` shows a plain "not built" page (status 503) and nobody can use the app, so do this step before you let people in.

The app's page is served with a strict content security policy (scripts only from your own server). `STILLOPEN_APP_CSP=0` turns it off if a proxy in front of it rewrites the page.

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

Paste each provider's client ID and secret in the admin under **Site configuration > Social sign-in** and tick its box; it applies at once, no restart.
(Or set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` and the `GITHUB_` and `FACEBOOK_` ones in `.env`; the environment takes precedence.) The page lists the exact redirect addresses to give each provider. While sign-up is *Closed*, only emails on the allowed list may use a social button;
with sign-up *Open*, anyone with a usable email may.

## Email

Without email set up, you can still use everything: sign-ups are not email-confirmed (the admin shows a notice) and reminders only print to the server log.
The easiest way: admin > **Site configuration > Email**. Fill in the server, port, login, password and sender, save, then open the
**send yourself a test email** link on that page. It applies at once. (Or set these in `.env`, which takes precedence; copy `.env.example`.)

```
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=StillOpen <jobs@example.com>
```

Then check it: `docker compose -f docker-compose.selfhost.yml exec stillopen python manage.py check_email --to you@example.com`
(without Docker: `python manage.py check_email --to you@example.com`). It prints the settings (never the password) and sends one test message.

## More countries (optional, free)

Out of the box StillOpen reads company hiring boards and remote-job feeds. Two free job searches add whole countries, each asked with the roles every person has chosen. Without a key they are skipped and nothing breaks; the dashboard shows you, as the owner, a reminder until one is set.

1. **Adzuna** (UK, US, Canada, Australia, New Zealand, India, Singapore, South Africa, Brazil, Mexico, Poland and most of western Europe). Register at <https://developer.adzuna.com>, copy the **app id** and **app key** from your dashboard, and paste them under Site configuration > Job search keys (or set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`). Test with `python manage.py check_adzuna --country gb`. Adzuna asks for a "Jobs by Adzuna" credit next to its results (the app adds it) and its free plan is rate limited, so searches are cached for a few hours and only ask the countries a person's search areas cover. Its results are never put on the public job board.
2. **Jooble** (Bangladesh, Pakistan, India, Malaysia, Singapore, Indonesia, the Philippines, Thailand, the Gulf, Egypt, Nigeria, South Africa, Brazil, Mexico, Poland, Turkey). Request a free key at <https://jooble.org/api/about> (they approve it by email), paste it in the same place (or set `JOOBLE_API_KEY`), and test with `python manage.py check_jooble --place pk`.

Two country searches need no key: JobTech (Sweden's public employment service) and Get on Board (tech jobs in Latin America). People can see where each of their search places stands, and what to do about an empty one, under Job sources > "Where we find jobs for you". Existing installs get the new sources once when you update; `python manage.py seed_sources` adds any that are missing.

## Scheduled jobs (optional)

None are required: a person's search runs when they open the dashboard, and the public job board refreshes itself when a visitor arrives and it is stale.
Schedule these only for emails and always-fresh data: interview reminders, follow-up emails, job alerts, the weekly summary, board refresh. Ready-made files:
[`deploy/crontab.example`](../deploy/crontab.example) (Linux/macOS) and [`deploy/windows/schedule-stillopen.ps1`](../deploy/windows/schedule-stillopen.ps1) (Windows).
With Docker, run the same commands through `docker compose ... exec -T stillopen python manage.py <command>`.

Each email type has two switches: yours (Site configuration > Dashboard: follow-up emails, job alerts, **weekly emails**) and each person's own tick under
Profile > Emails. Nothing is sent unless both are on, and only to an email address the person has confirmed. The weekly email is
`python manage.py send_weekly_summary` (one cron line, Monday morning is typical): one plain-text email per person, never twice in 6 days, and none at all
when there is nothing due or coming up. Emails link back to the app using Site configuration > Email > **public_base_url** (for example `https://jobs.example.com`);
if that is blank they fall back to the Sites domain, and without either they simply say where to go in the app instead of printing a link.

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

## More than one worker (optional, needs Redis)

By default StillOpen runs **one** gunicorn worker with 16 threads. That is deliberate: the per-person limits (AI checks, searches, CV tailoring, MCP calls),
the sign-in and sign-up limits, and the public board's refresh lock are all counted in Django's cache, and the default cache is each process's own memory.
With two workers every limit would be twice as loose. One worker is plenty for a household or a few hundred people; add workers only when
the CPU of that one process is the bottleneck.

To run several workers, give them a shared cache. Add the Redis file and a worker count:

```bash
# .env
STILLOPEN_WORKERS=4
# start
docker compose -f docker-compose.selfhost.yml -f docker-compose.redis.yml up -d --build
```

(add `-f docker-compose.postgres.yml` and `-f docker-compose.caddy.yml` as usual: the files stack in any combination). `docker-compose.redis.yml` runs `redis:7-alpine`
with no disk persistence (only counters and locks live there, so losing them on a restart merely resets everyone's rate-limit window) and sets
`REDIS_URL=redis://redis:6379/0` for the app. Without Docker: `pip install -r requirements-hosting.txt`, set `REDIS_URL` (any `redis://` or `rediss://` address) and start gunicorn
with `--workers N`. With Redis on, the limits are shared by every worker. If you raise `STILLOPEN_WORKERS` (or gunicorn's
`WEB_CONCURRENCY`) without `REDIS_URL`, `manage.py check` prints warning `stillopen.W003`.

What stays per process even with Redis: the **background threads**. A person's job search, the open/closed check, the prep-plan writer and the public-board refresh each run
as a thread inside the worker that started them. That is fine (the request that starts one returns at once and the page polls the database, which every worker shares;
a lock in the cache stops two workers refreshing the public board at the same moment), but a restart or deploy of that worker stops its threads. A search or plan that was
running is shown as stalled after a while and can be started again. Scheduled jobs (`deploy/crontab*.example`) are separate processes and do not care how many workers there are.

If Redis is unreachable, requests that count a limit fail with an error until it is back: keep it on the same host, as the compose file does.

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

**Automatic, for the Docker + PostgreSQL setup:** `deploy/backup-postgres.sh` writes a verified dump to `~/stillopen-backups` (and keeps a copy of the secret key),
and prunes backups older than 14 days. `deploy/crontab.docker.example` schedules it nightly at 02:30, together with the board refresh, interview
reminders, follow-up and job-alert emails. Paste it with `crontab -e`. A backup on the same machine does not survive losing the machine, so also copy
that folder somewhere else (rsync, rclone, a NAS). Restore command: see the top of the script.

Keep the secret key (`DJANGO_SECRET_KEY`, or `/data/.secret_key` in the Docker volume) with the backup: stored API keys cannot be decrypted without it.
To restore, put the file back and start the app.

### Copying backups off the machine

`deploy/backup-offsite.sh` takes the newest verified dump from `~/stillopen-backups`, copies it to a remote with **rclone** (preferred), `rsync` or `scp`, checks the copy
(rclone compares hashes or sizes; rsync/scp compare a SHA-256 read back over ssh), and deletes all but the newest 7 copies there. It never reads, prints or logs a
credential: rclone keeps its own in `rclone config`, and ssh uses a key file. It exits non-zero if anything fails, so cron's mail or your log shows it.

```bash
cp deploy/offsite.env.example ~/.stillopen-offsite.env && chmod 600 ~/.stillopen-offsite.env     # set OFFSITE_REMOTE (and OFFSITE_METHOD)
OFFSITE_DRY_RUN=1 deploy/backup-offsite.sh      # shows what it would copy, copies nothing
deploy/backup-offsite.sh                         # for real; deploy/crontab.docker.example runs it nightly at 03:10, after the dump at 02:30
```

Use an encrypted rclone remote (type `crypt`) so the provider cannot read your people's data. Optional extras in the env file: `OFFSITE_INCLUDE_MEDIA=1` (an archive of uploaded
files) and `OFFSITE_INCLUDE_SECRET_KEY=1` (the key that unlocks stored API keys: only to a remote you encrypt). Without the secret key a restored copy still works, but people
must paste their AI keys again.

**Restoring from the off-site copy, step by step** (a new machine, or after losing this one):

1. Install Docker and rclone, clone the project, and put your `.env` back (at least `POSTGRES_PASSWORD`, `DJANGO_ALLOWED_HOSTS`, the email lines).
2. Set up the same rclone remote (`rclone config`; for a crypt remote you need its password, keep that somewhere other than the backup itself).
3. See what is there and pick a file: `rclone lsf myremote:stillopen-backups` (the newest name sorts last).
4. Download it, and the secret key if you saved one: `rclone copyto myremote:stillopen-backups/stillopen-20261025T023000Z.dump ./restore.dump`
   and `rclone copyto myremote:stillopen-backups/secret_key ./secret_key`. (With rsync or scp, copy the same files from the remote folder.)
5. Check it reads back: `docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml run --rm -T db pg_restore --list < restore.dump | head`
6. Start only the database: `docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml up -d db`
7. Restore: `docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml exec -T db pg_restore -U stillopen -d stillopen --clean --if-exists < restore.dump`
8. Put the secret key where the app reads it: set `DJANGO_SECRET_KEY` in `.env` to its contents, or after the first start copy it to `/data/.secret_key` in the volume
   (`docker compose ... cp ./secret_key stillopen:/data/.secret_key`). Do this **before** people sign in, or stored API keys cannot be decrypted.
9. Start everything: `docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml up -d --build`, sign in, and check a person's jobs are there.
10. Uploaded files (if you archived media): `docker compose ... exec -T stillopen tar -xzf - -C /data < stillopen-media-....tar.gz`.

Test this once on a spare machine before you need it: a backup you have never restored is only a hope.

### Logs

Docker keeps each container's log in 3 files of at most 10 MB (set in every compose file), so logs cannot fill the disk. Without Docker, point gunicorn and your cron jobs at files in
`$APP/logs/` and install `deploy/logrotate.stillopen` (copy it to `/etc/logrotate.d/stillopen`, fix the paths, test with `logrotate --debug`).

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
| Limits are shared by every visitor, or one person's wrong passwords lock others out | The proxy settings are wrong. Behind a proxy set `DJANGO_BEHIND_PROXY=1` **and** `ALLAUTH_TRUSTED_PROXY_COUNT=1` (the number of proxies in front), and make the proxy send `X-Forwarded-For` (Caddy and the sample nginx file do). `manage.py check` warns about the first mismatch and the log names a wrong header at most once an hour |
| Public board is empty | `python manage.py refresh_postings`; make sure some sources are ticked *Show publicly* |

## Uninstalling

`docker compose -f docker-compose.selfhost.yml down -v` removes the container **and the data volume**. Export what you want to keep first
(Profile > Your data > export).

## Contributing and getting help

Questions and bugs: open an issue. Security problems: see [SECURITY.md](../SECURITY.md). Code: see [CONTRIBUTING.md](../CONTRIBUTING.md).
