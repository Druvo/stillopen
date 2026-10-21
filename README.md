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

Open http://127.0.0.1:8000 (public landing page), http://127.0.0.1:8000/dashboard/ (the dashboard, login required) and http://127.0.0.1:8000/admin/ (configuration). Copy `.env.example` to `.env` first if you want to change the career-ops path or Paperless URL before the first `migrate`.

## What you can change in the admin

| Admin section | Controls |
| --- | --- |
| Site configuration | Dashboard title, landing page on/off, headline, sub-headline and GitHub link, score scale (match % = score / scale), urgent-deadline window, auto-close of expired postings, career-ops folder, Node command, open/closed check mode and timeout, Paperless URL/token/TLS/auto-upload |
| Buckets | The dashboard tabs: label, order, which one is the "closed" tab |
| Statuses | Names, colour, tab, whether a status counts as "CV submitted" (stamps the applied date), whether it is terminal (skipped by the open/closed check) |
| Score bands | Labels and colours per match % threshold |
| Document kinds | File-name keywords that classify PDFs (CV, cover letter...), plus the Paperless tag and document type for each |
| Sources | Job-site names matched against the posting URL |
| Expired phrases | Text that marks a posting as closed (built-in HTTP check) |
| Applications | Edit any role, add notes/insights/documents/timeline events; bulk actions: mark applied, mark discarded, check open/closed, push to Paperless |

Import is idempotent: new tracker rows are created, existing rows refresh only evaluation data (score, summary, strengths, gaps, deadline, PDFs). Your local status, notes and URL are never overwritten unless you run `import_careerops --sync-status`.

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

## Your candidate information (CV, projects, notes)

Everything about you lives in the admin, in two places:

- **Site configuration > Your profile**: your CV as plain text, and your preferences (target roles, locations, remote, salary floor, deal-breakers). If you leave the CV blank and set the career-ops folder, `cv.md` from that folder is used.
- **Knowledge sources**: any number of extra documents, such as project write-ups, work-history details, certificates, cover letters or notes. Paste text or upload `.txt`, `.md` or `.pdf` (up to 2 MB). The **Import from career-ops** button adds `cv.md`, `article-digest.md` and `modes/_profile.md`. Untick "enabled" to hide a source from the AI without deleting it.

`python manage.py index_knowledge --import-careerops` does the import and indexing from the command line.

## Retrieval (RAG)

A long CV and many documents do not need to be sent for every job. With **Retrieval (RAG)** on (the default), each evaluation sends the opening of your CV plus only the passages most relevant to that job, and records how in the role's timeline ("RAG lexical, 4 passages from 29").

| Mode | How it ranks | Cost and privacy |
| --- | --- | --- |
| Keyword ranking (default) | BM25 over your passages | Free, offline. Only the final prompt goes to your AI provider. |
| Embeddings | Cosine similarity of vectors from an OpenAI-compatible `/embeddings` API (OpenAI, Ollama `nomic-embed-text`, ...) | Better at meaning. Your passages are sent to the embeddings service once and cached; each job description is sent to embed the query. |

If embeddings fail, retrieval falls back to keyword ranking and the timeline says why. Tune passage size and count in **Retrieval (RAG)**. The same retrieval is available to Claude Code through the `search_profile` MCP tool.

## AI evaluation: connect any AI

In **Site configuration > AI evaluation** choose how a job is scored:

| Provider | What it needs |
| --- | --- |
| Off | Nothing. Free keyword match against your CV and knowledge sources. It never overwrites a score you already have. |
| Anthropic API key | A key |
| OpenAI-compatible | A key and base URL. Covers OpenAI, OpenRouter, Groq, Mistral, Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`), DeepSeek, Ollama (`http://127.0.0.1:11434/v1`, no key), LM Studio and vLLM |
| Custom HTTP | Any other JSON API. You give the endpoint, header lines (`Authorization: Bearer {{api_key}}`), a JSON body using `{{system}}`, `{{prompt}}`, `{{model}}`, and the dotted path to the reply text (e.g. `candidates.0.content.parts.0.text`) |
| Claude Code CLI | `claude` installed and logged in on the same machine (not available inside Docker) |
| Claude Agent SDK | `pip install -r requirements-ai.txt` |

`python manage.py ai_check` sends one tiny request to confirm a provider works. `python manage.py evaluate_jobs` scores unscored roles. Keys are stored encrypted and never shown again; `STILLOPEN_AI_API_KEY` in the environment overrides the saved one.

How job text is handled: descriptions are untrusted, so they are wrapped in tags with an instruction to treat them as data, the reply must be one JSON object that is validated and clamped, and Claude Code and the Agent SDK run with every tool disabled in an empty folder.

## Claude Code and other AI clients (MCP)

StillOpen ships an MCP server so Claude Code, or any MCP client, can read and update your job search.

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
