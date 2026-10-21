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
- `tracker/mcp_tools.py`: plain functions behind the MCP tools; `mcp_server.py` registers them
- `tracker/auth.py`: allauth adapters (Google sign-in gated by an allowlist)
- `.claude/skills/stillopen/SKILL.md`: how an AI should use the MCP tools

## Rules

- Behaviour must stay configurable in the admin, not hard-coded. New setting = SiteConfig field + migration + admin fieldset + test.
- Job descriptions are untrusted text. Never put them where they could act as instructions: keep them in data tags, validate model output, never give a model tools while it reads one.
- Never log or display secrets. The AI key is stored encrypted (`tracker/crypto.py`); Paperless token and keys never appear in MCP output.
- MCP surface is deliberately small: no delete tool, no settings/keys/file access. Keep it that way.
- The keyword fallback must never overwrite an existing score.
- Tests that touch SiteConfig should clear `careerops_path` (use `isolated_config` in `tests_ai.py`) so they never read a developer's real career-ops folder.
- Use `python manage.py makemigrations` after model changes; commit the migration.
