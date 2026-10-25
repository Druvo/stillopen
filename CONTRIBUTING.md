# Contributing to StillOpen

Thanks for helping. StillOpen is Apache-2.0 open source and every kind of contribution is welcome: bug reports, ideas, docs,
translations of the words, new job sources, tests and code. By contributing you agree your work is released under the
[Apache License 2.0](LICENSE).

Please read the [Code of Conduct](CODE_OF_CONDUCT.md). For security problems, **do not open a public issue**: see [SECURITY.md](SECURITY.md).

## Get it running (5 minutes)

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
python -m venv .venv
.venv/Scripts/activate            # Windows. On Linux/macOS: source .venv/bin/activate
pip install -r requirements-mcp.txt -r requirements-ai.txt   # the optional sets are covered by tests too
python manage.py migrate          # also adds ~120 job sources
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. Sign-up is closed by default: switch it to **Open** under Site configuration in `/admin/`, or just use the superuser.
Copy `.env.example` to `.env` to change settings. Everything that changes behaviour is a setting in the admin, not code.

## The new app (optional, `frontend/`)

Only needed if you work on the new interface at `/app/`; Python-only contributors can skip it. Needs Node 22 or later and pnpm.

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:3000/app/ , proxies /api and sign-in to Django on port 8765
pnpm lint && pnpm typecheck && pnpm test
pnpm size         # fails if the app's JavaScript grows past its budget (frontend/scripts/check-bundle-size.mjs)
pnpm e2e          # real-browser tests against Django serving the build; uses the Chrome you have installed (E2E_PYTHON=path/to/python if needed)
pnpm build        # writes frontend/out, which Django serves at /app/ (the Docker build does this for you)
```

In the admin, tick **New app (beta)** under Site configuration, then switch it on in your own profile. Rules for the API are in `tracker/api/__init__.py`.

## Tests

```bash
python manage.py test                                  # the whole suite, about 7 minutes
python manage.py test tracker.tests_public             # one module, seconds
python manage.py makemigrations --check --dry-run      # CI fails if a model change has no migration
```

`manage.py test` switches off the seeded job sources, the live-network search and public caching, so tests are deterministic and never touch the internet.
CI (`.github/workflows/tests.yml`) runs the same on every pull request.

## The rules that matter most

These are the project's design commitments; a pull request that breaks one will be asked to change. The long version is in [CLAUDE.md](CLAUDE.md).

1. **Strict per-person isolation.** Anything personal belongs to one user. Every view, command and MCP tool filters by owner, and another
   person's row is a 404. A new model or endpoint needs an owner field or filter **and a test in the isolation style** (see `tracker/tests_multiuser.py`, `tests_pipeline.py`).
2. **No third-party requests from a page.** No CDN, font, script or image from another host. Vendor files under `static/vendor/` instead (`tests_selfhost.py` enforces it).
3. **Anything a person types as an address goes through `services/netguard.py`.** Never fetch it with plain `requests`.
4. **Job descriptions are untrusted text.** Never place one where it could act as an instruction; validate model output; never give a model tools while it reads one.
5. **The app never applies or sends on a person's behalf.** It prepares and records.
6. **Honesty over flattery.** Scores are estimates and say so; a CV or letter may only use what the person's own material says (fact check).
7. **Behaviour stays configurable.** A new setting is a field, a migration, an admin entry **and a test**.
8. **Public pages follow the sources' terms.** New sources are hidden from the public board until their terms are checked (`seed_sources.PUBLIC_OK_CONNECTORS`). No JobPosting structured data.
9. **Plain words.** Text a person reads speaks to them directly: no jargon, no harsh labels, every empty state says what to do next.
10. **Secrets are never logged, shown or committed.**

## Adding a job source

A connector is one function in `tracker/services/scan.py` (`fetch_<name>(token) -> list[dict]` with `title`, `url`, `location`, `company`, `description`),
a choice in `JobSource.CONNECTORS`, tests with a mocked response (see `tracker/tests_engine.py`), and an entry in `tracker/seed_sources.py`.
Only add sources that publish an open, documented, key-free feed or API and whose terms allow automated reading. Check what they say about republishing before
you add them to `PUBLIC_OK_CONNECTORS`. Sites that forbid crawling (LinkedIn, Indeed, Glassdoor, bdjobs, JobStreet) are out.

## Pull requests

- Branch from `main`, keep a change focused, and explain **why** in the description.
- Add or update tests; run the module you touched and, before opening the PR, the whole suite.
- Commit messages: a short summary line (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `perf:`), a body when the reason is not obvious.
- Run `python manage.py makemigrations` after model changes and commit the migration.
- Update the README or docs for anything a person or an operator will notice.

## Reporting bugs and asking for features

Use the issue templates. For a bug, say what you did, what you expected and what happened, and include the version (`git rev-parse --short HEAD`)
and how you run it (local, Docker). Please remove personal data from anything you paste.
