# StillOpen: developer handover

Written 2026-10-25 for the next developer. Read this first, then [`CLAUDE.md`](../CLAUDE.md) (the rules and the file-by-file layout),
then the guides it links. Nothing secret is in this file; where a secret lives is said, never its value.

## 1. What this is

StillOpen is an open-source (Apache-2.0), self-hostable job-search app. A person signs up, says what roles and places they want and adds their CV; the app
searches about 115 company career pages and open job boards for them (no AI needed), scores fit, tailors CVs, tracks applications, interviews, contacts and
offers, and (new) writes a short study plan for the skills a job needs. A public job board and landing page show what is open. An MCP server lets Claude Code or
any AI assistant work with a person's own account.

- Stack: Django 5.2, SQLite by default or PostgreSQL, allauth, django-unfold (admin), Tabler (candidate UI, vendored), WhiteNoise, gunicorn, Docker.
- Repo: `github.com/Druvo/stillopen` (public). Default branch `main`. Production: `https://stillopen.rnd.place`.

## 2. Run it and test it

```bash
python -m venv .venv && .venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt                          # add -r requirements-hosting.txt for PostgreSQL
python manage.py migrate && python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8765                # Windows: some ports around 8000 are reserved by the system
STILLOPEN_DB=db_test.sqlite3 python manage.py test --noinput     # about 7 minutes, 880+ tests; keeps your real DB out of it
```

- CI (`.github/workflows/tests.yml`) runs the full suite twice: SQLite and PostgreSQL 16. Both must be green; `makemigrations --check` also runs.
- Run a subset while working: `python manage.py test tracker.tests_prep tracker.tests_quiz`.
- Tests that need PostgreSQL locally: start `postgres:16-alpine`, set `DATABASE_URL=postgres://...`, `STILLOPEN_SEED_SOURCES=0`.
- Under `manage.py test` the job-source seeding, caches and auto scans are off (`RUNNING_TESTS` in settings).

## 3. How it is laid out

`CLAUDE.md` has the authoritative map. In short:

| Area | Where |
| --- | --- |
| Models | `tracker/models.py` (SiteConfig singleton, Application, CV versions, pipeline, ApiToken...), `tracker/prep_models.py` (prep plans) |
| Search engine | `services/scan.py` (connectors, staged fetch, scoring, dedupe), `services/geo.py`, `services/fit.py`, `seed_sources.py` |
| AI | `services/ai.py` (providers, evaluation prompt), `cvgen.py`, `coverletter.py`, `prep.py` (study plans), `factcheck.py` |
| Public site | `views_public.py`, `services/public.py`, `landing_content.py`, templates `landing.html`, `openings.html` |
| Candidate UI | `views*.py`, `templates/tracker/`, `tracker/templates/tracker/dashboard.html` (client-side filtering) |
| Admin | `tracker/admin.py` (Unfold; Site configuration is tabbed) |
| Email and social login | `services/integrations.py`, `email_backend.py`, `auth.py` |
| MCP | `mcp_tools.py` (plain functions), `mcp_registry.py` (tool list), `views_mcp.py` (HTTP endpoint and token pages), `mcp_server.py` (local stdio) |
| Quiz | `services/quiz.py`, `views_prep.py` |
| Ops | `management/commands/`, `deploy/`, `docker-compose*.yml`, `Dockerfile` |

Management commands: `refresh_postings`, `scheduled_scan`, `send_interview_reminders`, `send_followup_emails`, `check_liveness`, `seed_sources`,
`check_email`, `check_jooble`, `copy_to_postgres`, `update_legal_text`, `import_careerops`, `claim_data`, `evaluate_jobs`, `index_knowledge`, `ai_check`.

## 4. The rules you must keep

These are in `CLAUDE.md`; the ones that bite most often:

1. **Strict per-person isolation.** Every row belongs to an owner; every view, command and MCP tool filters by it; another person's id is a 404. A new model or endpoint needs an owner filter and a test in `tracker/tests_multiuser.py`. The one deliberate exception is `Posting`/`PostingSighting` (facts about a company's board, shared).
2. **Job text is untrusted.** Put it only in data tags, clamp and validate model output, never give a model tools while it reads it.
3. **The app never applies to a job or sends a message for a person.** Flagged CVs cannot be exported until the person approves; assistants can never approve.
4. **No third-party requests from any page** (fonts, scripts, images). Tests in `tests_selfhost.py` cover the public pages and the admin. Vendor files under `static/vendor/`.
5. **Behaviour is configurable in the admin**: a new setting is a `SiteConfig` field, a migration, an admin entry and a test.
6. **Plain words to people.** No jargon, no harsh labels, every empty state says what to do next.
7. **MCP stays small**: no delete tool, no settings, keys or file contents.
8. **Public job board rules**: only sources ticked "Show publicly" (an allow-list in `seed_sources.PUBLIC_OK_CONNECTORS`), a short excerpt only, a credit link, no JobPosting structured data, 410 for gone openings.
9. **Secrets are encrypted at rest** (`tracker/crypto.py`, derived from `SECRET_KEY`) and never shown again. SMTP password, social secrets, AI keys: write-only fields.

## 5. Configuration

Environment variables win over the admin; the admin (Site configuration) works without a restart. See `.env.example` and `docs/SELF-HOSTING.md`.

| Need | Env | Admin |
| --- | --- | --- |
| Secret key | `DJANGO_SECRET_KEY` (Docker generates and keeps one in the volume) | n/a |
| Hosts, HTTPS | `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_HTTPS`, `DJANGO_BEHIND_PROXY`, `ALLAUTH_TRUSTED_PROXY_COUNT` | n/a |
| Database | `DATABASE_URL` (PostgreSQL) or `STILLOPEN_DB` (SQLite path) | n/a |
| Email | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Email tab, plus a test page at `/tools/email-test/` |
| Social login | `GOOGLE_`, `GITHUB_`, `FACEBOOK_` `CLIENT_ID` and `CLIENT_SECRET` | Social sign-in tab (switch, id, secret) |
| Prep plans, MCP tokens, registration, public board, legal text | limits as `STILLOPEN_*` | their own tabs |

Important: with no email configured, sign-ups are not email-confirmed (the confirmation rule follows whether email works, `integrations.require_email_confirmation`).
Open registration only after email works and the privacy and terms placeholders (`[bracketed parts]`) are filled in and reviewed.

## 6. What was built recently (state on 2026-10-25, `main`)

All merged unless said otherwise.

- Open-source readiness: Apache-2.0, community files, issue/PR templates, non-root Docker image, self-host compose files, `docs/SELF-HOSTING.md`.
- Public landing page and job board with live numbers, filters (country list of all 249, visa sponsorship, relocation, kind, level, posted within).
- Sign-in: allauth with optional two-step sign-in (authenticator, security key, recovery codes), Google, GitHub and Facebook.
- Web MCP endpoint `/mcp/` with personal tokens (read-only or read and change, expiry, revoke).
- Admin on Unfold with a grouped sidebar; email and social settings in Site configuration.
- PostgreSQL support: CI job, `docker-compose.postgres.yml`, `copy_to_postgres`; Caddy HTTPS via `docker-compose.caddy.yml`.
- Prep plans, phases 1 and 2: `docs/design/prep-plans.md`.

**Open PRs**

- Backups and schedules (#14) was merged on 2026-10-25 and the production server now runs it (a verified backup was written and the nightly job is installed).
- #4 to #9, #11, #12: Dependabot bumps. #4 to #7, #9 and #11 are green; the gunicorn, whitenoise and Docker-related ones are not exercised by tests (the suite does not run gunicorn), so
  try them in a staging container first. #12 (Django 6.1) is a major jump; skip until planned.

## 7. Production (the one running instance)

- One Oracle Cloud Always Free ARM VM (1 OCPU, 6 GB, Ubuntu 24.04), Docker Compose with three services: the app (gunicorn, 1 worker with 16 threads on purpose: per-person rate limits live in process memory), PostgreSQL 16, Caddy (automatic HTTPS).
- Compose files used together: `docker-compose.selfhost.yml`, `docker-compose.postgres.yml`, `docker-compose.caddy.yml`. Secrets live only in `~/stillopen/.env` on the VM (mode 600); the database password and secret key are not in the repo or this file.
- DNS: `A stillopen.rnd.place` pointing at the VM, DNS-only (not proxied), so Caddy can get its certificate.
- Update: `git pull` in `~/stillopen`, then `docker compose -f docker-compose.selfhost.yml -f docker-compose.postgres.yml -f docker-compose.caddy.yml up -d --build`. Migrations run on start.
- Cron (user crontab on the VM): nightly backup 02:30, board refresh every 6 hours, interview reminders hourly, follow-up and job-alert emails mornings, weekly source seed. Ready-made lines: `deploy/crontab.docker.example` (after #14 merges).
- The operator keeps private infrastructure notes (hosts, SSH keys, other servers) outside the repo. Ask the owner for access; never commit credentials.

## 8. Known issues and risks (honest list)

1. **Backups** run nightly at 02:30 into `~/stillopen-backups` on the VM and are verified (the dump is read back). They live on the same machine as the database, so also copy that folder somewhere else; a backup on the same VM does not survive losing it.
2. **Email is not set up** in production (no SMTP credentials yet). Until it is, confirmation, reminders and alerts do not send. Brevo's free plan (300 a day) is the plan; enter it in admin > Site configuration > Email, then use the test page.
3. **Social login keys are not entered** yet; the buttons stay hidden until a provider has keys and its switch on.
4. **Prep plans have not been run against a real AI provider.** Everything is tested with a stand-in model. Expect to tune the three prompts in `services/prep.py` (`GAPS_SYSTEM`, `SYLLABUS_SYSTEM`, `QUESTIONS_SYSTEM`) once real output is seen; the validators are deliberately strict, so poor output fails a plan rather than saving bad content.
5. **Streak uses the server timezone** (`TIME_ZONE`, default Asia/Dhaka), not each person's.
6. **Legal text** (privacy, terms) still has placeholders and needs a lawyer before open sign-up.
7. **Public board terms**: Remotive, We Work Remotely, Working Nomads, The Muse and Jooble are hidden from the public board on purpose (their terms). Re-read a source's terms before ticking "Show publicly".
8. **The sites StillOpen reads change.** Connectors in `services/scan.py` break when a provider changes its API; the scan log in the dashboard and `refresh_postings` output show per-source failures.
9. **Git history** contains an author identity with a work email address, and copyright is "Zahid Hasan and the StillOpen contributors". The owner should confirm both (and any employer IP policy) before promoting the project.
10. **A second, unrelated server** (a callcenter stack) in the same Oracle account had a full disk at last look. It is not part of StillOpen.

## 9. Gotchas learned the hard way

- **Never close the caller's DB connection from a worker.** `scan._worker` and `liveness._worker` only call `connections.close_all()` when run on a background thread; doing it on the main thread broke every PostgreSQL test and would break a request.
- **Tool functions run through `sync_to_async(thread_sensitive=True)`** in `mcp_registry._friendly`, so each web MCP call runs on the request's own thread and connection. A plain sync tool would run on an anonymous worker thread and leave a connection open.
- **`mcp_tools._owner()`** reads a context variable set by `acting_as(user)` (web) or a process default set by `set_user` (stdio). The web process never sets the default, so a forgotten `acting_as` fails closed.
- **Closing a streamed file response in a test** fires `request_finished`, which closes the test's connection on PostgreSQL. Use `tests.close_quietly`.
- **Migrations must be run on your dev DB** after pulling (`python manage.py migrate`); a missing column makes `SiteConfig.load()` fail on every page, which shows as a 500 on the login page.
- **Windows**: ports near 8000 can be reserved by the OS; use 8765. In Git Bash, paths passed to `docker` need `MSYS_NO_PATHCONV=1`. `.sh` files committed from Windows need the executable bit (`git update-index --chmod=+x`).
- **Cron does not expand variables inside variable values**; write commands out in full (see `deploy/crontab.docker.example`).
- **Docker health check** calls the app on `127.0.0.1`; settings always append it to `ALLOWED_HOSTS`.
- **Facebook's email is not treated as verified** (allauth default); a new Facebook person confirms by the usual link and is never attached to an existing account by email.

## 10. Where to go next (suggested order)

1. Copy the backups off the VM (section 8.1). Then decide the Dependabot PRs.
2. Owner steps that unblock the product: Brevo SMTP, Google and GitHub keys, legal text, a public contact address, two-step sign-in on the admin account.
3. Try prep plans with a real key; tune the prompts; look at the draft page with real output.
4. Prep plans phase 3: source read-back check (does the cited page support the answer), mock interview, mark milestones on the job timeline (design: `docs/design/prep-plans.md`).
5. Candidate-facing gaps from `docs/ROADMAP.md` (that file predates some of the above; check it against the code before trusting an item).
6. Nice to have: per-person timezone for the streak, MCP tools for prep plans (drafts only, never approving), a mobile-friendly pass on the dashboard, rotating logs on the VM.

## 11. Documents to read, in order

1. `README.md` (what it is and quick start)
2. `CLAUDE.md` (rules and layout)
3. `docs/SELF-HOSTING.md` (run it, email, HTTPS, PostgreSQL, backups, updates)
4. `docs/HOSTING.md` (running it as a shared service)
5. `docs/MCP.md` (assistants and tokens)
6. `docs/design/prep-plans.md` (the prep plan design and its status)
7. `docs/ROADMAP.md` (older gap analysis)
8. `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
