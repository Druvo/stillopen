# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no numbered releases yet; `main` is the
supported version, so entries are grouped under **Unreleased** until the first tag.

## [Unreleased]

- "Ask for changes" on a CV version and on a cover letter: type what you want different ("make it shorter", "lead with my Django work", "less formal") and your own AI sends back a revised copy. It is fact-checked like a tailored CV (anything not in your own CV or documents is flagged, and a flagged copy cannot be downloaded until you approve it). On a CV the result is a new version and the old one is kept; on a cover letter the earlier text is kept and "Undo" brings it back. Needs your AI set up; limited per hour by `STILLOPEN_REFINE_PER_HOUR`.
- CV builder: optional Publications (plain one-line citations, "plain" or "APA-like") and References ("available on request" line, or up to three people) sections; three more plain download looks (Serif, Forest, Slate; font and colour only). "Export my data" now carries a format marker and the home country and time zone, and Profile > Your data can add an export back into the same account: a preview first, then a merge that only fills what is empty (profile answers, CV history, cover letters, job notes) and never overwrites.
- Optional Google connection (off until the site admin enters a Google OAuth client under Site configuration > Google connection): connect your own Google account on Profile > Connections to send an application from your own Gmail (only after you preview the exact message and press Send), see employer replies next to the job, get a draft reply and three free interview times, and keep your Google Calendar in step with your interviews both ways. Nothing is ever sent automatically, by the scheduler or by an AI assistant.
- Dashboard: a list with stage tabs is the default again (the board is one click away), filters hide behind a Filters button, a "Your search" card shows what drives your matches, and a layout you choose is remembered on your account for every device (view, tab, sort, filters, sidebar, theme, text size, density; set text size and density under Profile > Display). Opening the app is much faster: the job list now costs about 30 database queries instead of one per job (it was 187 for 45 jobs), answers are compressed and revalidated instead of re-sent, the per-source search log is only fetched when opened, and a reload paints from what the tab already had while it refreshes.
- Your numbers (Insights, and a "This week" card on the dashboard): jobs found, checked and applied to each week, how good your matches are, replies and who has been waiting longest, where your jobs come from, kinds of work and countries, skills that keep coming up in fit checks, prep progress, and how many new postings match your roles on the boards this week. Plain counts from your own search, never predictions or comparisons with others.
- Startups hiring: a new admin opt-in source reads Hacker News' monthly "Who is hiring?" threads (startups, current and
  previous month). Each post shows the apply email or link it publishes itself, as a plain link on the job card and
  All postings; nothing is ever sent for you. YC's job list was checked and not added (its terms forbid scraping).
- A private calendar link (Interviews screen > "Show these dates in your calendar"): subscribe Google, Apple or Outlook
  Calendar to `/calendar/<token>.ics` and upcoming interviews, follow-up days and apply-by days appear there. Read-only, dates plus
  company and role only (never notes, job text, meeting links or contacts), rate-limited per address, "Make a new link" revokes the old one
  at once, "Turn off" deletes it. Tunable with `STILLOPEN_CALENDAR_FEED_PER_HOUR`, `STILLOPEN_CALENDAR_FEED_BAD_PER_HOUR`,
  `STILLOPEN_CALENDAR_LINKS_PER_HOUR`.
- Container image: the `Dockerfile` now has an entrypoint that makes a secret key and migrates on start, a health check and image labels;
  `.github/workflows/image.yml` builds on pull requests and pushes `ghcr.io/<owner>/<repo>` on `v*` tags. New `docs/INSTALL.md`
  covers Docker Compose, plain Docker, from source, an Ubuntu service and CapRover/Coolify/Dokploy.

- Optional shared cache: set `REDIS_URL` and `pip install -r requirements-redis.txt` so per-person rate limits
  and the search-source cache are shared across every process/machine instead of split per worker. Unset,
  nothing changes. Fixed two Playwright e2e specs left broken by the earlier quick-add-bar removal (CI on
  `main` had been red for the last three pushes because of it) and corrected a stale doc claim that Postgres
  was only exercised through SQLite -- a `test-postgres` CI job against a real Postgres service already exists.
- Optional "Check writing" button on CVs and cover letters: a grammar/clarity check via LanguageTool
  (self-hostable, open-source). Off by default -- set `LANGUAGETOOL_URL` (Site configuration > Job search
  keys & writing check) to turn it on. Real linting only, no invented metrics.
- Every job card now shows "Recognized technologies": named tools the posting mentions (Docker, Kubernetes,
  React...), each marked whether your own CV/knowledge already covers it. Grounded in the US Department of
  Labor's O*NET database (a real, CC-licensed, named-technology vocabulary), not generic word frequency --
  ESCO was tried for this earlier and rejected as a poor fit; O*NET live-checked well. Zero-token, works
  without an AI key.
- Four free, no-sign-in tools at `/tools/`: a job-fit checker (the same free keyword match, paste a posting and
  a CV), "is this job still open?" (the same liveness check, paste a link), an offer comparator (the same
  per-currency comparison, never converted) and an RSS feed of the public job board. Nothing is saved; each is
  rate-limited per IP and shares the sign-up form's bot-trap discipline (a honeypot field, a minimum fill time,
  no CAPTCHA).
- "Draft ahead" (Profile > Job alerts): after a scheduled search, optionally prepares tailored CV drafts for the best
  new matches (top score band, at most `STILLOPEN_DRAFT_AHEAD_MAX`, default 3, per run) with the person's own AI
  settings. Drafts go through the normal tailoring and fact check, are never approved, exported or sent for them,
  and wait on the dashboard ("Drafts waiting for you") to open, approve or discard; the job-alert email mentions them
  in one line. Off at two levels: `SiteConfig.draft_ahead_site_enabled` and each person's own switch.
- A weekly digest email (Profile > Job alerts): applications sent, interviews, offers and follow-ups from the
  last 7 days, the same plain counts the Insights page shows. Off at two levels like the scheduled search
  email -- a site admin switches it on (Site configuration > Dashboard), each person opts in separately. Run
  `manage.py send_weekly_digest` on a weekly cron.
- Optional "Translate to English" button on a job's description, via LibreTranslate (self-hostable,
  open-source). Off by default -- set `LIBRETRANSLATE_URL`. The result is shown for reading only, never saved.
- CV downloads (DOCX and print/PDF) now offer a choice of three built-in looks -- Classic (unchanged), Modern
  (serif headings, a blue accent) and Compact (smaller, tighter spacing) -- font and colour variation only,
  still a plain single-column document so applicant-tracking systems can read it.
- A USAJobs source, off by default: the official, documented US federal job search API (needs a free key plus
  the email it was requested with -- Site configuration > Job search keys). A dashboard banner nudges admins
  when the source is enabled site-wide but missing one of those.
- Insights: a new "Does a higher match score lead anywhere?" table groups your own applied jobs by match band
  and shows interview/offer counts and rates per band (`services/pipeline.py`'s `by_score`, `/api/v1/insights`,
  `frontend/src/features/pipeline/insights.tsx`). Plain counts from the person's own data, no prediction.
- Optional self-hosted error tracking: set `GLITCHTIP_DSN` (or `SENTRY_DSN`) and `pip install -r
  requirements-errors.txt` to send uncaught errors to GlitchTip (open-source, Sentry-DSN-compatible) or Sentry.
  Off by default, `send_default_pii` stays off. See `docs/HOSTING.md`.
- Guided CV builder: a short Q&A (`/cv/build`) assembles a first CV from scratch for a candidate with nothing
  to paste yet -- no AI, nothing beyond what was typed. Saves through the same path as every other CV-creation
  method, so matching, tailoring and export treat it identically.
- Two more Bangladesh job sources, off by default (an admin opts in): `bdjobs.com` (an undocumented but real
  JSON search API) and `bikroy.com` Jobs (decoded from its server-rendered page). A dashboard banner nudges
  admins toward a Jooble key when Jooble sources exist site-wide but no key is configured.
- The classic candidate pages are removed. `/app/` is now the only interface for signed-in people, for everyone: the "New app (beta)" switch (site setting and per-person option) is gone, and so are the old Django-template screens, their forms and endpoints (dashboard, welcome, add and edit job, postings, profile and AI settings, documents, CVs and cover letters, apply assistant, interviews, contacts, offers, insights, prep plans, job sources, assistant tokens, and the old JSON calls for status, evaluate, liveness, scan, import and Paperless, which have twins under `/api/v1/`). Old addresses keep working: each redirects to the same screen in the app and keeps its query string. Sign-in lands on `/app/` (a new person on the welcome questions). Public pages, sign-in, the admin, `/mcp/`, and the file downloads the app links to (CV and cover letter downloads, the print page, document files, the data export) are unchanged. Running Django without Docker now needs the front end built once (`cd frontend && pnpm install && pnpm build`); until then `/app/` shows a plain page explaining that, with status 503. A migration drops the two switch columns.
- New app (beta): every signed-in screen is now also available in a newer interface at `/app/` (Next.js built as a static export that Django serves; no Node on the server). A board you can drag jobs across (also by keyboard, and from a status menu on every card), a list view, search and sorting, prep plans and daily practice, add and edit job, apply assistant, CVs (edit, compare, approve, restore) and cover letters, documents, all postings, interviews, contacts and referrals, offers, insights, profile, AI settings, job sources, assistant tokens and the welcome questions. Behind it is a JSON API at `/api/v1/` (django-ninja; normal sign-in session, CSRF on every change, another person's data is a 404, and a test walks every route to prove it). The page is served with a strict content security policy (`STILLOPEN_APP_CSP=0` turns it off). Off until the admin ticks "New app (beta)" in Site configuration; each person then opts in from their profile, classic pages with a twin send them there, and `?classic=1` is the way back. The classic pages stay for now; they are deleted only after the new app has been live for a release. Downloads and print pages stay on their classic addresses.
- Operations: `deploy/backup-postgres.sh` (verified nightly dump with retention) and `deploy/crontab.docker.example` for the Docker setup.
- Prep plans (phase 2): a daily practice of 3 questions per plan (admin setting) drawn from this week and earlier, exact-match scoring, explanations with the official source after answering, a streak, and topics that need another look (two different questions missed within 30 days; clears after right answers on three separate days across two questions). The dashboard nudges when today's practice is waiting. Answers are in the data export.

- Prep plans (phase 1): from a job with skill gaps, "Prepare for this job" has the person's own AI account write a short study plan (default 4 weeks, 6 hours a week) with official-source reading and cited quiz questions. Everything the model returns is checked before it is saved; the person reviews the draft and starts it, ticks lessons off, and finished lessons count as study in the next fit check. The daily quiz comes next. Admin settings under Site configuration > Prep plans. See docs/design/prep-plans.md.

- Admin: email sending (Brevo or any SMTP, with a test page) and Google, GitHub and Facebook sign-in (client ID, secret, on/off) are now set in Site configuration and apply at once; environment variables still take precedence. Secrets are stored encrypted and never shown again. AI settings now ask only for a provider and a key, with the technical fields under Advanced.

- Connect an AI assistant: each person can make personal tokens (read only or read and change, with expiry and revoke) under Profile, and use Claude Code or any MCP client against the website at `/mcp/`. Same small tool list as the local server, always acting as the token's owner only. See docs/MCP.md.

- Sign-in: optional two-step sign-in for everyone (authenticator app, security key, recovery codes), and GitHub and Facebook sign-in beside Google, each with its own switch in the admin.

- PostgreSQL: the whole suite now also runs on PostgreSQL in CI; `docker-compose.postgres.yml` adds a database to the self-host setup; `manage.py copy_to_postgres` moves an existing SQLite install over and checks row counts. Background search and open/closed workers no longer close the calling thread's database connection.

- Public job board: every country in the world in the country filter (not just the top 40), plus filters for visa sponsorship, relocation help, kind of job, level and how recently posted. These are read from each posting's own words.

### Added
- **Open source under Apache-2.0**, with `LICENSE`, `NOTICE`, a code of conduct, a security policy, a contributing guide, issue and pull-request templates,
  Dependabot, and a self-hosting guide (`docs/SELF-HOSTING.md`).
- **Public side**: a landing page that explains the product with live numbers and charts, a public job board (`/openings/`) with search, filters and a
  page per opening, `robots.txt` and a sitemap. Only sources whose terms allow it are shown, with credit links, short excerpts and no JobPosting markup.
- **A standard look**: light by default with a remembered dark toggle, one brand colour, logo, system fonts only.
- **Jobs find themselves**: about 120 key-free sources ship by default (remote feeds and employer hiring boards, including Malaysia, the Gulf and Dhaka);
  a search starts when the dashboard opens, reads sources in parallel, drops jobs outside a person's places, scores the rest for free (skill coverage, no AI) and
  shows the best first. Optional Jooble connector for Bangladesh, Malaysia and the Gulf.
- Dashboard shows every job first, then filters (stage, search, fit, match, work, country, posting, found) and five sorts.
- Fact-checked **cover letters**; **interviews**, **contacts and referrals**, **offers** with comparison, an **Insights** funnel; interview reminders and
  opt-in job-alert emails; the same pipeline through the **MCP server**.
- Candidates can add their own company boards (private, guarded fetch).
- Operator tools: `check_email`, `check_jooble`, `refresh_postings`, `seed_sources`, `update_legal_text`; cron and Windows Task Scheduler files; plain-language
  privacy and terms templates; GitHub Actions running the tests and a migration check.

### Changed
- Sign-up works without SMTP (email confirmation applies only where email can be delivered), and the welcome page asks where a person would work.
- Search is about twice as fast (first jobs in about 25 seconds) with a visible progress bar.

### Fixed
- Greenhouse's escaped HTML no longer leaks tags into excerpts or match scoring; a fresh-install migration crash; wrong canonical URLs; and many smaller
  first-run problems found by walking the app as a new person.

[Unreleased]: https://github.com/Druvo/stillopen/commits/main
