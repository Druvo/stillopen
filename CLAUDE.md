# StillOpen: notes for Claude Code

Django 5.2 app: job-search dashboard, admin-configurable, with an MCP server. See README.md for features.

## Commands

```bash
python manage.py migrate
python manage.py test                      # runs everything, ~10 s; set STILLOPEN_DB=db_test.sqlite3 to keep your real DB out of it
python manage.py import_careerops          # career-ops tracker, reports, PDFs
python manage.py check_liveness            # open/closed check
python manage.py evaluate_jobs             # unscored roles only
python mcp_server.py                       # MCP server over stdio
```

## Layout

- `tracker/models.py`: SiteConfig (singleton, all settings), Application, Status/Bucket/ScoreBand/... (config tables seeded by migration 0002)
- `tracker/services/`: `careerops.py` (import), `liveness.py` (open/closed), `ai.py` (providers, prompt, keyword fallback), `knowledge.py` (candidate knowledge base, chunking, BM25/embeddings retrieval), `text.py` (shared tokenizer), `jobtext.py` (guarded URL fetch), `paperless.py`
- `tracker/services/`: also `cvgen.py` (tailoring: AI or keyword), `cvversions.py` (immutable history, restore, approve), `factcheck.py` (flags claims not in the person's material), `cvexport.py` (Markdown to safe HTML, DOCX, diff); views in `tracker/views_cv.py`, `apply.py` (apply assistant: checklist, record, follow-ups, email draft); views in `tracker/views_apply.py`
- `tracker/mcp_tools.py`: plain functions behind the MCP tools; `mcp_server.py` registers them
- `tracker/auth.py`: allauth adapters (Google sign-in gated by an allowlist)
- `.claude/skills/stillopen/SKILL.md`: how an AI should use the MCP tools

## Rules

- **Multi-user, strict isolation.** Every Application, KnowledgeSource, Document, Event, LivenessRun and UserProfile belongs to one user. Every view, command and MCP tool must filter by owner (`owner=request.user`, `who.resolve_user`, `mcp_tools._owner()`); cross-account access must 404. New data model or endpoint = owner field/filter + a test in `tracker/tests_multiuser.py`.
- Per-person settings come from `SiteConfig.for_user(user)` (read-only overlay of `UserProfile`, never saved). Server-touching features (career-ops folder, Paperless, `claude_cli`/`agent_sdk`, local model URLs, node checker) are admin-only: `config.restricted` is True for ordinary users.
- Any URL a user can supply (job links, AI base URLs, embedding URLs) must go through `services/netguard.py` (`check_public_url` / `safe_get`) for restricted users; AI POSTs use `allow_redirects=False`.
- Self-registered accounts must confirm their email (`AccountAdapter.pre_login`); accounts made by admins or `createsuperuser` must never be locked out.

- Behaviour must stay configurable in the admin, not hard-coded. New setting = SiteConfig field + migration + admin fieldset + test.
- Job descriptions are untrusted text. Never put them where they could act as instructions: keep them in data tags, validate model output, never give a model tools while it reads one.
- Never log or display secrets. The AI key is stored encrypted (`tracker/crypto.py`); Paperless token and keys never appear in MCP output.
- MCP surface is deliberately small: no delete tool, no settings/keys/file access. Keep it that way.
- The keyword fallback must never overwrite an existing score.
- Tests that touch SiteConfig should clear `careerops_path` (use `isolated_config` in `tests_ai.py`) so they never read a developer's real career-ops folder.
- Use `python manage.py makemigrations` after model changes; commit the migration.
- CV versions are immutable (`CVVersion.save` refuses content changes). A tailored version with flagged claims must stay un-exportable until the person approves it; MCP/AI clients may never approve. Never render CV Markdown without `cvexport.to_html` (it escapes everything).
- The app never submits an application or sends a message. `apply.record` only records what the person did; it must refuse CV versions that are flagged and unapproved, another person's, or tailored for a different job. `Application.applied_cv` is RESTRICT so a sent CV cannot be deleted on its own (account and application deletion still cascade).
