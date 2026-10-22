# StillOpen: current-state audit, market comparison, roadmap

Written 2026-10-22. Facts below verified against the codebase at commit `659c8c7` (file:line cited). Market comparisons reference [career-ops](https://github.com/santifer/career-ops) and [ai-job-search](https://github.com/MadsLorentzen/ai-job-search), both evaluated hands-on in this same session (see reports/ in the sibling `career-ops` checkout for a worked example).

## 1. Direct answers to the questions asked

**"Search jobs button that live-searches" — does not exist today.** Adding a job is 100% manual: `tracker/views.py:270-283` (`add_job`) renders a form (company, role, URL, deadline, description, notes) — the user pastes everything. The only automated fetch is a single-URL pull when the description is left blank (`tracker/services/jobtext.py`, called from `ai.py:388-398`), not a search. No scraping/portal/discovery code exists anywhere in `tracker/` (confirmed by grep across the whole app).

**"Logs — where it's searching, what it found"** — nothing exists yet because there's no search yet. The closest analogue today is the per-application `Event` timeline (`tracker/models.py:733-752`): an AI evaluation writes one line like `"Evaluated (ai:anthropic): 84% match"` (`ai.py:417`). There's no scan-level log, because there's no scan.

**"Will it cost me tokens?"** — only if you turn on a paid AI provider and click **Evaluate match**. With `ai_provider = none` (the default), it's a free keyword match (`ai.py:364-383`) — zero network calls, zero cost. There is currently **no token/cost estimate or usage display anywhere** in the app — not before a call, not after. That's a real gap for a public tool (see §4).

**"Free options?"** — yes, two: (1) the built-in keyword-match fallback, always free, always available; (2) a local model via Ollama/LM Studio, by pointing `ai_base_url` at `http://127.0.0.1:11434/v1` under the OpenAI-compatible provider (`models.py:46`). The catch: local-model URLs are currently **admin-only** (`CLAUDE.md`'s own rule, enforced at `models.py:272-273`) — fine for your own single-user deployment where you're the admin, but it means an ordinary visitor on a shared/public instance can't point the app at their own free local model. Worth relaxing for single-user installs (§3).

**"Flexible AI" — architecturally, yes, already quite good.** Six provider paths exist: off/keyword, Anthropic, any OpenAI-compatible endpoint (which covers OpenRouter, Groq, Gemini, DeepSeek, Mistral, Ollama, LM Studio — `models.py:28`), a fully generic custom-HTTP template for literally any API shape, the Claude Code CLI, and the Agent SDK. Everyone brings their own key, stored encrypted (`tracker/crypto.py`), never logged. This is already more flexible than either career-ops (built around whichever CLI you happen to run it in) or most consumer job trackers (usually locked to one vendor).

## 2. Full comparison vs. similar tools

| Axis | **StillOpen** | **career-ops** | **ai-job-search** | Generic SaaS tracker (Teal/Huntr-style) |
|---|---|---|---|---|
| Interface | Web dashboard, multi-user | Chat inside an AI coding CLI | Chat inside Claude Code | Web dashboard |
| Entry cost | $0 (keyword match) | Needs Claude Pro/Max or API credits — **no AI CLI, no functionality at all** | Same — needs Claude Code + LaTeX toolchain | Usually a paid subscription |
| Job discovery | **None** (manual paste only) | Zero-token scanner over 100+ pre-configured Greenhouse/Ashby/Lever boards + reverse-ATS full sweep | Regional portal scrapers (Jobindex/Jobnet/LinkedIn/freehire) | Browser extension "save this posting" only |
| Evaluation depth | One blended match % + flat strengths/gaps list | A-H block framework: role summary, CV-match table with importance tiers, level strategy, comp/demand research, personalization plan, interview plan, Block G legitimacy, work-auth check, geo-mismatch check | Fit-framework scoring + drafter/reviewer CV-cover-letter pipeline with PDF layout verification | Usually no AI scoring at all, or a black-box vendor score |
| Posting legitimacy / ghost-job detection | Basic open/closed check only | Full legitimacy tier (High Confidence / Caution / Suspicious), repost detection, aggregator-vs-employer confirmation | Integrity gate (hidden text, injected instructions) | None |
| Multi-user / hosting | **Yes** — real multi-tenant isolation, self-registration, Google login, admin-configurable everything | No — one person's local files | No — one person's local files | Yes, but closed-source |
| CV tailoring | Yes — AI or keyword, with immutable version history, fact-check gate before export, diff/restore | Yes — much deeper: JD-keyword injection, recruiter-risk-map, ATS lint, hiring-manager-audit mode, LaTeX/PDF layout iteration loop | Yes — same depth as career-ops, drafter-reviewer with company research | Usually none or template-only |
| Negotiation / interview prep | None | Full suite: STAR+R story bank, negotiation scripts, offer/contract clause walk, salary-gap analyzer | STAR mapping, mock interview protocol | Rare, shallow |
| Follow-up automation | `EMAIL_HOST` wired for account emails only — no follow-up nudges yet | Follow-up cadence calculator + seeded reminders | `/outcome followup` drafts follow-ups | Sometimes, basic |
| Outcome calibration ("do my scores predict real interviews?") | None | Yes (`calibrate` mode) | None | None |
| Cost/token transparency | **None** | None either, but irrelevant — cost is your existing CLI subscription, not per-action | Same | N/A (flat subscription) |
| Abuse protection for public hosting | None yet (`docs/HOSTING.md:52`: "no CAPTCHA and no per-IP rate limiting") | N/A, single-user | N/A, single-user | Has it (commercial product) |
| MCP/agent integration | Yes — 19-tool read-mostly MCP server, explicitly no delete/settings/key access | N/A — it *is* the agent | N/A | None |

### Wins (what StillOpen genuinely does better)

1. **It's the only one of the three that's a real multi-user product.** career-ops and ai-job-search are single-operator tools that assume you personally run an AI coding CLI — they cannot become "a tool for the mass public" as-is; StillOpen already has the account system, data isolation, and admin configurability a public tool needs.
2. **It's the only one that works for free, for a stranger, with zero setup.** No AI CLI subscription required at all — keyword match needs nothing.
3. **BYOK across six provider shapes**, including a fully generic custom-HTTP escape hatch career-ops/ai-job-search don't have.
4. **CV version immutability + fact-check-before-export gate** is a genuinely good safety property most trackers (and even career-ops's simpler file-based CV) don't enforce as a hard, un-bypassable gate in the data model itself.
5. **MCP server with a deliberately narrow, safe tool surface** — lets a power user layer Claude Code on top without StillOpen itself needing to run an agent loop for every user (cost control by construction).
6. **Admin-editable everything** (statuses, buckets, score bands, document kinds, sources) without touching code — genuinely matches the "configurable, not hard-coded" principle in their own CLAUDE.md, and is exactly what a multi-tenant public tool needs that a single-user file-based system doesn't.

### Losses (the real gaps, ranked by impact)

1. **No job discovery at all.** This is the single biggest functional gap and exactly what was asked about. Both reference tools treat this as core; StillOpen treats it as entirely the user's job.
2. **Evaluation is one dimension.** A single % with a flat strengths/gaps list is far thinner than career-ops's A-H framework (separate legitimacy, comp, location-fit, level-strategy signals) — harder for a stranger to trust or act on.
3. **No legitimacy/ghost-job signal beyond binary open/closed.** For a public tool this matters *more* than for a personal one — strangers need protection from scams more than a careful solo user does.
4. **No cost/token visibility.** For a BYOK public tool this is close to a trust requirement, not a nice-to-have — people need to know what clicking "Evaluate" will cost before they click it.
5. **No follow-up/negotiation/interview layer.** Pure tracker + evaluator today; the two reference tools both go well past "track and score."
6. **Public-hosting hardening is explicitly incomplete** per their own docs: no CAPTCHA, no per-IP limiting, in-process (not shared) rate limiter that won't survive more than one server process.
7. **`Source` model is cosmetic**, not functional — it labels a posting's host but doesn't drive discovery of anything. Easy pivot point for real connectors (see below).

## 3. Concrete plan: live search + logs + cost + free-by-default + flexibility

This directly answers the question as asked, in priority order.

**A. Job discovery, zero-token first.** Add real connectors for Greenhouse/Lever/Ashby's public JSON APIs (the same pattern career-ops already validated — no LLM call needed to discover a posting, only to score it once found). Promote `Source` from a cosmetic label into a real `JobSource` model: `name`, `connector_type` (greenhouse/lever/ashby/custom), `board_id`, `enabled`. Admin (or, for a self-hosted single-user instance, the user) adds companies through the UI — no file editing, matching the existing "configurable in the admin" philosophy.

**B. A `ScanRun` model, mirroring the existing `LivenessRun` pattern** (`started_at`, `finished_at`, `running`, `total`, `done`, `error`) plus a child `ScanLogEntry` (source name, requests made, postings found, postings kept after filtering, duplicates skipped, elapsed ms). Surface this as a collapsible "Scan log" panel next to the existing "Open/closed checked N minutes ago" banner — this is the literal answer to "from where it's searching and what it found."

**C. Cost transparency, two layers:**
   - *The scan itself costs nothing* — ATS JSON APIs need no LLM call, so make that explicit in the UI ("Free — no AI used").
   - *Evaluation* is where cost can occur. Before the call: show an estimated input size (chars → rough token count) and, for a priced provider, a small admin-editable per-model price table (same admin-configurable pattern as `ScoreBand`) to show an estimated $ before the click. After the call: most Anthropic/OpenAI-compatible responses return actual usage — capture it and append to the existing `Event` line (`"Evaluated (ai:anthropic): 84% match — ~1,850 tokens, ~$0.004"`). Add a simple running "tokens used this month" counter per user, summed from these events — no new infra needed, just read what's already logged.

**D. Free-by-default, flexible when wanted:**
   - Keep keyword match as the true zero-cost default (already correct).
   - Relax the admin-only restriction on local-model URLs (`ai_base_url` → Ollama) for single-user/self-hosted instances specifically — detect "only one account exists" and treat that account as trusted the way `createsuperuser` already is, rather than gating a genuinely free, local, private option behind "admin only" when there's no one else to protect from.
   - Add a one-click "Use free local AI" setup doc link in Profile → AI pointing at Ollama install steps.
   - Add a per-user "ask before spending" toggle so BYOK users with a paid key never get surprised by an accidental click.

## 4. Closing the feature gap with career-ops (making it genuinely useful, not just a tracker)

Ranked by value-per-effort:

1. **Split the single match % into named sub-scores** (role fit, location fit, comp signal if stated, legitimacy) — reuses data already being parsed (JD text, `Source`/posting metadata), mostly a scoring-and-display change, no new infra.
2. **Repost/ghost-job detection almost for free** — `LivenessRun`/`ScanRun` history already timestamps every sighting of a URL; "seen N times across M scan runs over X days" is a cheap derived signal, same idea as career-ops's `detect-reposts.mjs`.
3. **Follow-up nudges** — `EMAIL_HOST` is already wired for account confirmation emails; reuse it for "it's been 10 days since you applied to X" reminders. Zero AI cost, high perceived value.
4. **Basic interview-prep templates** (STAR skeleton, common-question bank) as static content first, with *optional* AI tailoring layered on top later — keeps the free tier meaningfully useful, not just a bare tracker.
5. **Outcome calibration** ("are your high-scored jobs the ones that actually get interviews?") — a nice differentiator once enough `Event`/status-change history accumulates per user; purely derived from data already being collected.

## 5. Before calling this "for the mass public"

These are explicitly flagged as missing in their own `docs/HOSTING.md` and are real prerequisites, not polish:

- Per-IP rate limiting and a CAPTCHA on registration and on the free-tier scan/evaluate endpoints (today: none).
- Move the rate limiter off in-process memory onto a shared cache (Redis) — noted in `HOSTING.md:24` as required before running more than one process, which a real scan feature (background workers) will need anyway.
- Politeness/ToS discipline on the new scanner identical to career-ops's own stance (GET-only, respect robots.txt, no login bypass, no anti-bot workarounds) — scanning on behalf of many public users raises the stakes on this versus a single personal instance.
