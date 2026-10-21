# StillOpen

Job-search dashboard on Django, fed by your career-ops folder, with Paperless-ngx for documents.
Everything that changes behaviour is a row in the admin, not code.

## Run it

```bash
cd stillopen
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py import_careerops
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000 (dashboard) and http://127.0.0.1:8000/admin/ (configuration). Copy `.env.example` to `.env` first if you want to change the career-ops path or Paperless URL before the first `migrate`.

## What you can change in the admin

| Admin section | Controls |
| --- | --- |
| Site configuration | Dashboard title, score scale (match % = score / scale), urgent-deadline window, auto-close of expired postings, career-ops folder, Node command, open/closed check mode and timeout, Paperless URL/token/TLS/auto-upload |
| Buckets | The dashboard tabs: label, order, which one is the "closed" tab |
| Statuses | Names, colour, tab, whether a status counts as "CV submitted" (stamps the applied date), whether it is terminal (skipped by the open/closed check) |
| Score bands | Labels and colours per match % threshold |
| Document kinds | File-name keywords that classify PDFs (CV, cover letter...), plus the Paperless tag and document type for each |
| Sources | Job-site names matched against the posting URL |
| Expired phrases | Text that marks a posting as closed (built-in HTTP check) |
| Applications | Edit any role, add notes/insights/documents/timeline events; bulk actions: mark applied, mark discarded, check open/closed, push to Paperless |

Import is idempotent: new tracker rows are created, existing rows refresh only evaluation data (score, summary, strengths, gaps, deadline, PDFs). Your local status, notes and URL are never overwritten unless you run `import_careerops --sync-status`.

## Open/closed check

- `node` mode runs career-ops `check-liveness.mjs` (Playwright). Use this: it renders JavaScript pages and caught the closed Falaq, Flyte and Pipeline postings.
- `http` mode is a plain request plus your expiry phrases. It cannot see closed postings on JavaScript sites and will report them as open.

Run it from the dashboard button, the admin action, or `python manage.py check_liveness` (suitable for Task Scheduler).

## Paperless-ngx

```bash
copy .env.example .env      # then fill PAPERLESS_ADMIN_USER, PAPERLESS_ADMIN_PASSWORD, PAPERLESS_SECRET_KEY
docker compose up -d
```

1. Open http://127.0.0.1:8010 and sign in with the admin user you chose.
2. Create an API token (profile menu, My Profile) and paste it into Site configuration, or set `PAPERLESS_TOKEN` in `.env` (the environment variable wins).
3. Tick "Paperless enabled". Documents then get a "Send to Paperless" button on the dashboard; titles are `Company - Role - Kind`, tagged `stillopen` plus the kind's tag. Re-sending finds the existing title instead of duplicating.

Optional container + nginx front end: `docker compose --profile web up -d --build` serves the dashboard on http://127.0.0.1:8080. Set `CAREEROPS_HOST_PATH` in `.env` to mount your career-ops folder, and use `http` check mode there (the image has no Node).

## Google sign-in

Username/password login always works. Google sign-in is optional and off until you set it up:

1. In Google Cloud Console create an OAuth client ID (type "Web application"). Add the redirect URI `http://127.0.0.1:8000/accounts/google/login/callback/` (use your real address and `https` in production).
2. In the admin open **Social applications**, add one: provider Google, your client ID and secret, and move your site into "Chosen sites". (Alternatively set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.)
3. In **Site configuration** tick "Google login enabled" and list who may sign in, one per line: `you@gmail.com` or a whole domain `@company.com`.

Rules: a Google account must have a verified email. A user already in the database with that email (for example you, the superuser, once your user has an email address set) is signed in as that user. New people are created only if they are on the allowed list, never as staff, so they get the dashboard but not the admin. Remember that everyone on the list sees all jobs and documents. Nobody can self-register with a password.

## Security notes

- Dashboard and file serving require login; POST endpoints use Django CSRF.
- Document files are only served from the media folder or the configured career-ops folder.
- Keep `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY` and a restricted `DJANGO_ALLOWED_HOSTS` anywhere beyond localhost. Do not expose Paperless or this app to the internet without a reverse proxy and TLS.
- `.env`, `db.sqlite3`, `.secret_key` and `media/` are git-ignored.

## Tests

```bash
.venv\Scripts\python.exe manage.py test
```
