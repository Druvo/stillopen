# StillOpen

Job-search dashboard on Django. Each person registers, adds the roles they want and their CV, tracks the jobs they are chasing, and sees a match percentage and whether each posting is still open. Optional AI scoring with your own key, retrieval over your own documents, an MCP server for Claude Code, Paperless-ngx for documents, and a career-ops import for admins. Everything that changes behaviour is a row in the admin, not code.

It runs two ways: on your own machine for one person, or as a shared service for many people (each only ever sees their own data). Hosting guide: [docs/HOSTING.md](docs/HOSTING.md).

## For people using it

1. Register (or sign in), then open **Profile**: the roles you want, where, remote preference, salary floor, deal-breakers, and your CV (upload a PDF, .txt or .md, or paste it).
2. **Add job**: paste the company, role, link and the job description.
3. Press **Evaluate match** on a job. With no AI configured you get a free keyword match; under **AI settings** you can use your own API key (Anthropic, OpenAI-compatible, Gemini, Groq, OpenRouter, a custom API...) for a real evaluation.
4. **Documents**: add projects, work history, certificates and cover letters. For each job only the relevant passages are sent to the AI.
5. **Profile > Your data**: export everything as JSON, or delete your account and all data.

## Run it

```bash
cd stillopen
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Optional, admins only: `.venv\Scripts\python.exe manage.py import_careerops` loads a career-ops folder into your account. Jobs and settings created before accounts existed are given to the first account you create (or run `manage.py claim_data <username>`).

Management commands act for one person: pass `--user NAME`, or leave it out when there is exactly one superuser. `check_liveness --all-users` suits a scheduled job.

Open http://127.0.0.1:8000 (public landing page), http://127.0.0.1:8000/dashboard/ (the dashboard, login required) and http://127.0.0.1:8000/admin/ (site configuration). Copy `.env.example` to `.env` first if you want to change the career-ops path or Paperless URL before the first `migrate`.

## What you can change in the admin

| Admin section | Controls |
| --- | --- |
| Site configuration | Dashboard title, registration open/closed, privacy and terms text, landing page on/off, headline, sub-headline and GitHub link, score scale (match % = score / scale), urgent-deadline window, auto-close of expired postings, career-ops folder, Node command, open/closed check mode and timeout, Paperless URL/token/TLS/auto-upload |
| Buckets | The dashboard tabs: label, order, which one is the "closed" tab |
| Statuses | Names, colour, tab, whether a status counts as "CV submitted" (stamps the applied date), whether it is terminal (skipped by the open/closed check) |
| Score bands | Labels and colours per match % threshold |
| Document kinds | File-name keywords that classify PDFs (CV, cover letter...), plus the Paperless tag and document type for each |
| Sources | Job-site names matched against the posting URL |
| Expired phrases | Text that marks a posting as closed (built-in HTTP check) |
| User profiles | Each person's roles, CV, AI provider, retrieval settings and keys (keys are write-only) |
| Applications | Edit any role (admins see everyone's), add notes/insights/documents/timeline events; bulk actions: mark applied, mark discarded, check open/closed, push to Paperless |

Import is idempotent: new tracker rows are created, existing rows refresh only evaluation data (score, summary, strengths, gaps, deadline, PDFs). Your local status, notes and URL are never overwritten unless you run `import_careerops --sync-status`.

## Your own company job boards

Under **Job sources** in the sidebar, anyone can add the companies they care about. Pick the hiring system the company uses (Greenhouse, Lever, Ashby, SmartRecruiters or Recruitee), then type the company's name from its careers page address or paste the address itself (`jobs.lever.co/acme` gives `acme`). The app reads that company's public job list once to make sure it works, and only then saves it. Your boards are searched only for you and are invisible to everyone else; the boards the site owner added are searched for everyone. Limits per person: `STILLOPEN_MAX_OWN_SOURCES` (20) boards and `STILLOPEN_SOURCE_ADDS_PER_HOUR` (20) additions an hour.

Why this is safe to offer: nobody enters a web address. They choose from a fixed list of hiring systems, and the app builds the real address itself on that system's own host, through the same guarded fetch every scan uses. Boards for sites that need a browser or break a site's terms (LinkedIn, and aggregators like RemoteOK) stay site-owner only or unsupported.

## After you apply: interviews, contacts, offers

Three pages in the sidebar, all private to you and none of them contacts anyone:

- **Interviews**: when, what kind, where or the call link, and notes (who you meet, what to prepare). The next few show on the dashboard under "Coming up". Mark how each went; every change is added to the job's timeline.
- **Contacts**: people you know at or near a company, and **referrals**: which contact you have asked to put in a word for which job (thinking of asking, asked, agreed, submitted, declined).
- **Offers**: base pay (per year or month), yearly bonus, yearly value of shares, benefits you would otherwise pay for, and a one-off signing bonus. Offers are ranked side by side by yearly total, with the gap to the best. Different currencies are compared separately and never converted, because the app will not guess an exchange rate. Declined offers drop out.

**Insights** shows plain counts from your own tracker: how many applications reached an interview or an offer, the typical days from applying to a first interview, and which channels (and referrals) led to interviews. It describes, it never predicts.

**Interview reminders.** With follow-up emails switched on (Site configuration > Dashboard) and SMTP configured, run `python manage.py send_interview_reminders` hourly from cron or Task Scheduler. Each person gets one email for interviews in the next 24 hours, once per interview, and only at a verified address.

Each person can save up to `STILLOPEN_MAX_PIPELINE` (500) of each. Everything is included in the Profile > Your data export and removed with the account.

## Job alerts

Each person can tick **Profile > Job alerts** to have their saved search run on a schedule and get one email listing what was added. The site owner switches this on with `scan_emails_enabled` (Site configuration > Dashboard), configures SMTP, and runs `python manage.py scheduled_scan` daily from cron or Task Scheduler. Nothing is sent when nothing new was found, or to an unverified address.

## Open/closed check

- `node` mode runs career-ops `check-liveness.mjs` (Playwright). Use this: it renders JavaScript pages, so it catches closed postings that a plain HTTP check misses.
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

## Candidate information (CV, projects, notes)

Each person keeps their own, in the web app (not the admin):

- **Profile**: target roles, the country you live in, kinds of employment, seniority, industries, languages, notice period, salary floor, deal-breakers, an "about" note, your **search areas** (below), and the CV. Upload a PDF, .txt or .md (up to 2 MB, PDFs up to 60 pages); the text is read in and the file itself is not kept.
- **Documents**: any number of extra documents (up to 40): project write-ups, work-history details, certificates, cover letters. Hide one from the AI without deleting it.
- Admins can also use **Import from career-ops** (cv.md, article-digest.md, modes/_profile.md) in the admin, or `python manage.py index_knowledge --import-careerops --user NAME`.

## What you are looking for: search areas

A person's search is a list of **search areas**, one row per place, set on the Profile page:

| Where | Accepts | Needs from the employer |
| --- | --- | --- |
| Bangladesh (Dhaka) | on-site, hybrid | nothing |
| Anywhere | remote | nothing |
| Malaysia | on-site, hybrid | visa sponsorship, relocation support |
| Gulf | on-site | sponsorship, relocation, at least 8,000 USD per month |

A place is a country, a region (Gulf, Europe, Southeast Asia, EU, MENA...), a city, or **Anywhere**. Each row says which of remote, hybrid and on-site you accept there, whether you need visa sponsorship or relocation support, and an optional minimum pay with its own currency. The profile also records the country you live in, because a remote job limited to one country only fits someone who lives there.

Each job has a location, country, work arrangement, whether it offers sponsorship and relocation, a type (full-time, contract...) and seniority. They are **suggested by reading the posting** (no AI needed) and you can correct them on the job's **Details** page; what you set by hand is never overwritten. Every job is then checked against your areas, and the result shows as **Fits**, **Check fit** or **Fit unknown** on the dashboard and in the apply checklist: outside your areas, sponsorship not offered or not mentioned, pay below your minimum, wrong employment type or seniority. A job is only ever flagged, never hidden.

Detection recognises about 90 countries, regions and several hundred cities from a built-in table. An unrecognised place is kept and matched by name, and unclear postings are reported as unknown rather than guessed. The Profile page also has an Account section: change email or password, connected accounts, what is stored, export, delete.

## Tailored CVs and versions

Press **Tailor CV** on a job to make a CV for that role from your own CV and documents. With an AI provider configured the model rewrites it; without one, the free keyword mode reorders your bullets and skills by relevance to the posting and trims the weakest, adding nothing.

- **Honesty check.** The result is checked against everything you have written about yourself. Numbers, names (employers, schools, tools) and posting keywords that your material never mentions are flagged. A flagged CV cannot be downloaded or printed until you edit it or approve it ("everything listed is true"). The check is deliberately conservative: "8 years" against "eight years" is flagged for you to confirm.
- **Versions.** Every CV is an immutable version with a parent, who or what made it, the job it was for, and the job description as it was that day. Editing makes a new version; the master CV keeps a full history you can compare and restore (restoring adds a version, it never deletes).
- **Export.** DOCX (plain single column, real headings and bullets, no tables or images) and a print view for "Save as PDF". The output is Markdown you can also download.
- **Claude Code.** The `list_cv_versions`, `get_cv_version` and `save_tailored_cv` MCP tools let an AI client write a tailored CV; it goes through the same check and cannot approve its own work.

Limits: 200 versions and 20 tailorings per hour per person (`STILLOPEN_MAX_CV_VERSIONS`, `STILLOPEN_CVGEN_PER_HOUR`). **Cover letters.** On the apply page, "Write a cover letter" makes a short letter from your own material (an AI if you have connected one, otherwise your own most relevant CV bullets in a plain frame). It goes through the same fact check; a flagged letter is locked until you edit it or approve it, and any edit re-checks it and withdraws the approval. DOCX and plain-text download; it is never sent for you.

## Applying

StillOpen never submits an application for you: employer sites need your login and block bots, and a robot applying in your name is a bad idea. The **Apply** button on a job opens an assistant that prepares everything and then records what you did.

1. **Before you apply**: a checklist (is the posting still open, how close is the deadline, is it a poor fit below 50%, do you have a CV tailored for this job).
2. **Choose the CV to send**: your tailored versions for this job (only ones that passed the fact check or that you approved) or your current CV, with DOCX and print links. You can tailor a new one from here.
3. **Apply on the employer's site**: the posting link opens in a new tab. For email applications there is a plain draft (subject and body with `[Your name]`) that is never sent.
4. **Record it**: channel, date, a note, and a follow-up reminder (default 7 days, `Site configuration > Dashboard`). It sets the status to Applied (never moving you backwards from Interview), links the exact CV version you sent, and saves a snapshot of the job description as it was that day. A CV recorded as sent cannot be deleted. A posting that looks closed needs an explicit confirmation.

Follow-ups due appear at the top of the dashboard with Done and "In 3 days" buttons. In Claude Code, `record_application` and `list_follow_ups` do the same, and `record_application` is only for after you confirm you really submitted.

## Retrieval (RAG)

A long CV and many documents do not need to be sent for every job. With **Retrieval (RAG)** on (the default), each evaluation sends the opening of your CV plus only the passages most relevant to that job, and records how in the role's timeline ("RAG lexical, 4 passages from 29").

| Mode | How it ranks | Cost and privacy |
| --- | --- | --- |
| Keyword ranking (default) | BM25 over your passages | Free, offline. Only the final prompt goes to your AI provider. |
| Embeddings | Cosine similarity of vectors from an OpenAI-compatible `/embeddings` API (OpenAI, Ollama `nomic-embed-text`, ...) | Better at meaning. Your passages are sent to the embeddings service once and cached; each job description is sent to embed the query. |

If embeddings fail, retrieval falls back to keyword ranking and the timeline says why. Tune passage size and count under **AI settings > Retrieval**. The same retrieval is available to Claude Code through the `search_profile` MCP tool.

## AI evaluation: connect any AI

Each person chooses under **AI settings** how their jobs are scored (admins can also edit a user's profile in the admin):

| Provider | What it needs |
| --- | --- |
| Off | Nothing. Free keyword match against your CV and knowledge sources. It never overwrites a score you already have. |
| Anthropic API key | A key |
| OpenAI-compatible | A key and base URL. Covers OpenAI, OpenRouter, Groq, Mistral, Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`), DeepSeek, Ollama (`http://127.0.0.1:11434/v1`, no key), LM Studio and vLLM |
| Custom HTTP | Any other JSON API. You give the endpoint, header lines (`Authorization: Bearer {{api_key}}`), a JSON body using `{{system}}`, `{{prompt}}`, `{{model}}`, and the dotted path to the reply text (e.g. `candidates.0.content.parts.0.text`) |
| Claude Code CLI | Site admins only. `claude` installed and logged in on the same machine (not available inside Docker) |
| Claude Agent SDK | Site admins only. `pip install -r requirements-ai.txt` |

On a shared server, ordinary users can only point at public https addresses (no localhost or private networks). `python manage.py ai_check --user NAME` sends one tiny request to confirm a provider works. `python manage.py evaluate_jobs` scores unscored roles. Keys are stored encrypted and never shown again; `STILLOPEN_AI_API_KEY` in the environment overrides the saved one.

How job text is handled: descriptions are untrusted, so they are wrapped in tags with an instruction to treat them as data, the reply must be one JSON object that is validated and clamped, and Claude Code and the Agent SDK run with every tool disabled in an empty folder.

## Claude Code and other AI clients (MCP)

StillOpen ships an MCP server so Claude Code, or any MCP client, can read and update your job search. It acts for exactly one account: set `STILLOPEN_USER=yourname` (or leave it out when there is a single superuser), and it never sees anyone else's data.

```bash
pip install -r requirements-mcp.txt
claude mcp add stillopen -- <path-to>/.venv/Scripts/python.exe <path-to>/mcp_server.py
```

`.mcp.example.json` shows the same for other clients. It runs locally over stdio against the same database; nothing listens on the network.

| Tool | Use |
| --- | --- |
| `summary`, `list_applications`, `get_application` | See the pipeline and a role in full |
| `get_profile`, `search_profile`, `list_knowledge` | Your CV, preferences and the relevant passages of your knowledge base |
| `add_application`, `set_description`, `save_evaluation`, `update_status`, `add_note`, `check_open` | Add roles, store an evaluation the AI reasoned out, move status, check if a posting is open |

By design there is no delete tool, and no way to read settings, API keys, tokens or file contents. Job descriptions come back under a key marked untrusted. The repo includes a skill, `.claude/skills/stillopen/SKILL.md`, and the server sends the same rules as instructions on connect, so any client learns how to use it: confirm before marking Applied, never invent CV facts, treat posting text as data.

## Security notes

- Dashboard and file serving require login; POST endpoints use Django CSRF.
- Document files are only served from the media folder or the configured career-ops folder.
- Keep `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY` and a restricted `DJANGO_ALLOWED_HOSTS` anywhere beyond localhost. Do not expose Paperless or this app to the internet without a reverse proxy and TLS.
- `.env`, `db.sqlite3`, `.secret_key` and `media/` are git-ignored.

## Tests

```bash
.venv\Scripts\python.exe manage.py test
```
