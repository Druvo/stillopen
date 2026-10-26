# Hosting StillOpen for other people

StillOpen is multi-user: each person registers, has their own profile, CV, jobs and AI settings, and can only see their own data. This guide covers running it as a shared service.

## What you are taking on

People will upload CVs and job-search notes, which is personal data. You are the operator of that data. Before opening sign-up:

- Replace the default **Privacy** and **Terms** text (Site configuration > Legal). The defaults are placeholders, not legal advice.
- Know where your server and backups are, who can reach the database, and how you would answer a deletion or export request. Each person can export and delete their own data from the Profile page.
- Take regular encrypted backups of the database and the media folder.
- Decide who pays for AI. By default nobody does: people use the free keyword match, or bring their own API key (stored encrypted, only used when they press Evaluate). Claude Code CLI and the Agent SDK are limited to site admins because they run on your server.

## Deploy with Docker

```bash
cp .env.example .env     # fill POSTGRES_PASSWORD, DJANGO_ALLOWED_HOSTS, EMAIL_*, DEFAULT_FROM_EMAIL
docker compose --profile web up -d --build
docker compose exec web python manage.py createsuperuser
```

This starts PostgreSQL, the app (gunicorn, one process with 16 threads) and nginx on `127.0.0.1:8080`. Put a TLS-terminating reverse proxy (Caddy, nginx or a cloud load balancer) in front of it, then set `DJANGO_HTTPS=1`, `DJANGO_ALLOWED_HOSTS=your.domain` and `DJANGO_CSRF_TRUSTED_ORIGINS=https://your.domain` in `.env` and restart. Do not expose the app on the open internet over plain HTTP.

The app runs as one process on purpose: the per-person rate limits live in process memory. To scale beyond one machine, switch Django's `CACHES` to a shared cache (Redis) first.

Without Docker: `pip install -r requirements-hosting.txt`, set `DATABASE_URL=postgres://user:pass@host:5432/stillopen`, run `python manage.py migrate`, then run gunicorn the way the Dockerfile does.

## Before you open the doors: a checklist

1. `python manage.py check_email --to you@example.com`: confirms SMTP really delivers.
2. Fill in Site configuration > Legal (privacy and terms): the `[bracketed parts]`, then have it reviewed. The admin dashboard warns until they are filled.
3. Schedule the emails: `deploy/crontab.example` or `deploy/windows/schedule-stillopen.ps1`.
4. Optional: a Jooble key for Bangladesh, Malaysia and the Gulf (`python manage.py check_jooble` proves it works).
5. Put a TLS reverse proxy in front and set `ALLAUTH_TRUSTED_PROXY_COUNT=1` so the per-IP limits see visitors, not the proxy.
6. Optional: error tracking. Set `GLITCHTIP_DSN` (or `SENTRY_DSN` -- GlitchTip, a self-hosted open-source
   option, speaks the same protocol as Sentry) and `pip install -r requirements-errors.txt`. Off by default:
   nothing is sent anywhere unless one of those is set. `send_default_pii` stays off -- job descriptions and
   CV text are personal/untrusted data and are never attached to an error report.
7. Optional: a writing check. Set `LANGUAGETOOL_URL` (self-hosted, e.g. the `erikvl87/languagetool` Docker
   image, or Site configuration > Job search keys & writing check) to switch on a "Check writing" button on
   CVs and cover letters. Off by default; a person's CV/letter text is sent to that one server only when they
   press the button.

## The public job board

`/openings/` shows openings from sources you mark **Show publicly** (Site configuration > Job sources). Before launch:

1. Read `README.md` > "The public site" for the rules, and look at each public source's terms yourself: they can change. The defaults are conservative (Remotive and others off).
2. Set a **contact email** in Site configuration > Public job board: it is shown to employers who want a listing removed. Remove a source by unticking Show publicly; its openings disappear from the board on the next page load.
3. Keep `public_details_indexable` off unless you have reviewed the search-engine implications of republishing excerpts.
4. Schedule `refresh_postings` (see `deploy/`), or rely on the on-visit refresh.

## Open registration

1. Configure SMTP (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`). Confirmation links are emailed. **Without SMTP, email confirmation is switched off** (a link that is only printed to the server log would lock every new person out), so people are signed straight in and admins see a warning on their dashboard; set `STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=1` to insist anyway. Open registration without confirmed addresses invites fake accounts, so configure email before a public launch.
2. In the admin, Site configuration > Registration, choose **Open**.
3. Optional: add Google sign-in (see the README). With sign-up Open, any Google account with a verified email can register.

People who register themselves only give an email and a password. They must confirm the email before they can sign in; clicking the link in that email confirms it, signs them in and opens a short welcome page. Accounts you create in the admin, or with `createsuperuser`, are never blocked by this. New accounts are never staff.

## How data is kept apart

- Every job, document, knowledge source, profile and liveness run belongs to a user. Every view, command and MCP tool filters by that user, and cross-account access returns 404. This is covered by `tracker/tests_multiuser.py`.
- AI and embeddings settings are per person. A person's config is a read-only overlay (`SiteConfig.for_user`), so it cannot overwrite the site-wide settings.
- Ordinary users cannot use features that touch the server itself: the career-ops folder import, Paperless, the Claude Code CLI and Agent SDK providers, and local-model URLs.
- Because the server fetches URLs that users supply (job links, AI endpoints), every outgoing request refuses non-http(s) schemes and any host that resolves to a private, loopback, link-local or cloud-metadata address, and redirects are checked hop by hop. AI requests do not follow redirects.
- Uploaded CV and document files are read for their text and discarded; only the text is stored. Deleting an account removes the profile, jobs, notes, documents and any stored files.

## No third-party requests from the browser

The interface (Tabler 1.7.0, MIT) is shipped inside the app under `static/vendor/tabler/` and served by your own server, and the admin theme's Google Fonts CDN is turned off. Visitors' browsers therefore contact only your domain, so nothing about who visits or what they open leaks to a CDN, and a compromised CDN cannot inject script into your users' sessions. `tracker/tests_selfhost.py` fails if any page starts loading an asset from another host. The files are checked against jsDelivr's published SHA-256 hashes; see `static/vendor/tabler/NOTICE.md` to upgrade.

## Limits per person

Set in `.env`: `STILLOPEN_MAX_APPLICATIONS` (500), `STILLOPEN_MAX_KNOWLEDGE` (40 documents), `STILLOPEN_EVALS_PER_HOUR` (30), `STILLOPEN_CHECKS_PER_HOUR` (12). Uploads are limited to 2 MB and PDFs to 60 pages.

## Not covered yet

Be honest with yourself about these before a public launch:

- **Bots and abuse:** sign-up has a hidden trap field, a minimum fill time and per-IP rate limits (`STILLOPEN_SIGNUP_MIN_SECONDS`, `STILLOPEN_SIGNUP_RATE` default `5/h/ip`, `STILLOPEN_LOGIN_FAILED_RATE`). There is deliberately no CAPTCHA: Turnstile and similar would load a third-party script, which this app never does. Behind a reverse proxy set `ALLAUTH_TRUSTED_PROXY_COUNT=1` (and make the proxy set `X-Forwarded-For`), or every visitor shares the proxy's address and one limit. A determined human or a distributed bot network is still not stopped; add proxy-level limits if you see abuse.
- **Network isolation:** the private-address check happens before the request, so a hostile DNS server could still answer differently the second time (DNS rebinding). For hostile multi-tenant use, run the app with restricted egress (a network policy, or an egress proxy that blocks private ranges).
- **Job search sources:** there is no shared job feed or auto-scraping yet. People add roles themselves.
- **Staff access:** site admins can read the database and therefore everyone's data. Keep the number of admins small.
- **Compliance:** cookie notices, data-processing agreements with AI vendors, and data-residency rules depend on where you and your users are. Get proper advice.
- **PostgreSQL:** the Postgres setup is configured but has only been exercised through the SQLite test suite. Try a staging deployment first.
