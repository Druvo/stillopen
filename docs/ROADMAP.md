# StillOpen: gap analysis & roadmap to a complete candidate-facing product

Written 2026-10-23, superseding the 2026-10-22 version (that draft predates the scan/repost/liveness
features, which are now built — see `CLAUDE.md` and the feature inventory below). Verified against the
current tree; file:line cited where useful. Market comparison covers Teal, Huntr, Simplify.jobs, Jobscan,
LoopCV, and self-hosted alternatives (JobSync, JobOps, ShortList, Jobify, ApplyPotato, Reactive Resume).

## 1. What StillOpen already does (verified, not aspirational)

**Account/auth** — username+password, Google OAuth (allowlist-gated), self-registration with mandatory
email confirmation, admin-created accounts never blocked, account deletion (typed-confirmation, cascades,
deletes files), full JSON data export. Real multi-tenant isolation: every `Application`, `KnowledgeSource`,
`Document`, `Event`, `LivenessRun`, `ScanRun`, `CVVersion`, `UserProfile`, `SearchArea` has an owner,
filtered everywhere, covered by 55 tests in `tracker/tests_multiuser.py`.

**Tracking** — manual add (paste or auto-fetch from URL), admin-configurable Buckets/Statuses/ScoreBands,
dashboard with tabs/urgency sort/stats, job edit with manual-override protection, status API that never
regresses a status backward.

**Evaluation** — 6 AI provider paths (off/keyword, Anthropic, OpenAI-compatible — covers
OpenRouter/Groq/Gemini/DeepSeek/Ollama/LM Studio, generic Custom HTTP, Claude Code CLI, Claude Agent SDK),
free keyword fallback that never overwrites a real score, SSRF-guarded outbound calls (`netguard.py`),
encrypted BYOK keys, output clamping/validation, job text always treated as untrusted data.

**CV tailoring** — AI or keyword tailoring, immutable version history, full diff/restore, a fact-check gate
that blocks export/print of a flagged-and-unapproved version, DOCX/Markdown/print export, per-hour quotas.

**Apply assistant** — checklist, CV picker, plain-text email draft (never sent), application recording with
exact-CV-version linkage, follow-up reminders surfaced on the dashboard (no email nudge yet).

**Job discovery** — zero-token connectors for Greenhouse/Lever/Ashby/SmartRecruiters/Recruitee (single
company boards) + RemoteOK/We Work Remotely/Himalayas (aggregators), `ScanRun`/`ScanLogEntry` with a
collapsible scan log, title-matched against target roles **plus a skill-overlap fallback** (the candidate's
own CV/knowledge terms vs. a posting's title+description -- several connectors already return description
text in the same list response, no extra request -- `STILLOPEN_SKILL_MATCH_MIN_OVERLAP` shared terms is
enough; surfaced as an Event note and a "Skill match" dashboard badge so it's never a silent guess), shared
`Posting`/`PostingSighting` records (company+title keyed, so aggregators never cross-contaminate), a
browsable "All postings" page, and repost/ghost-job detection (2+ URLs across 2+ scan dates for the same
company+title, flagged as an observation). Explicitly rejected after live verification: Workable (dead API), LinkedIn (ToS/anti-bot),
bdjobs.com (client-side SPA, no API), Canada Job Bank (44 MB monthly dump, server times out).

**Liveness** — HTTP phrase-match or a Playwright-backed `node` mode (admin-only) for JS-rendered sites, auto-
close of expired postings into the closed bucket.

**Documents/RAG** — CV + up to 40 knowledge documents (PDF/.txt/.md), career-ops import, BM25 or embeddings
retrieval with automatic lexical fallback, Paperless-ngx push (admin-only).

**Fit/geo** — ~90 countries + cities, remote/hybrid/onsite + visa/relocation/salary matching against a
user's `SearchArea`s, manual-override-safe auto-detection from posting text.

**MCP server** — 19 read-mostly tools, no delete/settings/key access by design, strictly per-user.

**Admin** — one `SiteConfig` singleton drives almost every behavior (buckets, statuses, score bands,
sources, expired-phrase list, legal text, landing copy); server-touching features (career-ops path,
Paperless, CLI/SDK AI, local-model URLs, Playwright liveness) are admin-only by design.

No TODO/FIXME markers anywhere in the Python source — gaps are tracked in prose (this file), not code debt.

## 2. Market position: what the best tools in this space have that StillOpen doesn't

| Capability | Teal | Huntr | Simplify | Jobscan/LoopCV | Self-hosted (JobSync/JobOps) | **StillOpen today** |
|---|---|---|---|---|---|---|
| Kanban/pipeline board | yes | yes | — | — | yes | tabs by bucket, no drag-reorder |
| One-click browser-extension capture (any job site → tracker) | yes | yes | yes | — | some | **not wanted** — everything stays in-panel by decision (see Tier 1 #1 for the in-panel alternative) |
| **Autofill into ATS application forms** | — | partial | yes (flagship) | — | — | **none** (by design: app never submits applications) |
| Resume/JD match score | yes | yes | yes | yes (flagship) | yes | yes — keyword + optional AI, already competitive |
| Generative resume rewrite / cover letter | yes (weak, per reviews) | yes | yes | — | some | tailoring yes, **cover letters: not built** |
| Contact/networking tracker | — | yes | — | — | — | **none** |
| Interview scheduling + reminders | — | yes | — | — | some | Event has an `interview` kind, **no scheduling/reminders/prep** |
| Offer comparison (salary/bonus/equity) | — | — | — | — | — | **none** (whitespace — no competitor does this well either) |
| Analytics (response rate, funnel, time-to-offer) | — | partial | — | — | — | **none** beyond 4 summary numbers |
| Job alerts / saved recurring search | yes (board aggregation) | — | — | — | — | one-shot scan only, **no recurring/scheduled scan or digest** |
| **"Is this posting still open" live check** | — | — | — | — | — (ApplyPotato: via Gmail only) | **yes — a genuine differentiator, lean into it** |
| **Referral tracking** | — | — | — | — | — | **none — whitespace, no competitor has this either** |
| Cost/token transparency for AI use | — | — | — | — | — | tokens + cost per call, monthly total on Profile -> AI settings |
| Mobile app | native | native | extension | — | — | responsive web only |

Takeaways:
- StillOpen's match-scoring and CV-tailoring depth are already at or above commercial-tool quality.
- Teal/Huntr/Simplify's stickiest feature is a browser-extension one-click capture — **deliberately not
  wanted here**: everything stays inside the panel. The in-panel paste-URL quick-add (Tier 1 #1) and the
  recurring/scheduled scan across the 8 existing connectors (Tier 1 #4) are the chosen substitutes, and
  between them they cover most of the same "frictionless discovery" value without a second codebase to
  maintain (an extension) or leaving the app.
- "Still open" checking and referral tracking are both **whitespace** — no major competitor does them well.
  Positioning opportunity, not just a gap to close.
- Generative rewriting (cover letters, free-text application answers) is the one area every competitor
  leans on an LLM for — StillOpen's BYOK model already covers this architecturally, it just needs the
  cover-letter feature built on the existing `cvgen.py`/`ai.py` pipeline.
- Autofill-into-ATS and bulk auto-apply are both explicitly **non-goals**: StillOpen's own principle is
  "the app never submits an application" (`CLAUDE.md`) — keep that; it's also the feature with the highest
  ongoing maintenance burden (breaks per-site) and the most ToS/ethics risk (LoopCV-style auto-apply).

## 3. Prioritized build list — ranked by value-per-effort, split by AI dependency

### Tier 1 — highest leverage, build first

1. **Everything-in-panel quick add, no extension — done.** Decision: no browser extension — all capture
   stays inside the app. The dashboard has a "Paste a job URL" bar (`views.quickadd_fetch`,
   `services/jobtext.fetch_posting`/`guess_role_company`) that fetches title+description in one step and
   hands off to the add-job form via the session (prefilled, one-shot, never auto-saved -- the person still
   reviews and submits). No AI required. Not yet done: running the match evaluation automatically right
   after a quick-add save (currently still a separate "Evaluate match" click, same as a manually-added job).
2. **Cost/token transparency -- done.** Every paid-provider call (`evaluate_application` and the CV-tailoring
   `complete()`) now logs an `AIUsageEvent`: tokens from the provider's own response (Anthropic, any OpenAI-
   compatible endpoint), cost either reported directly (Claude Code CLI, Agent SDK) or estimated from a small
   static per-model price table (never a guess for a model not in it). Surfaced as a running monthly total on
   Profile -> AI settings and appended to each evaluation's Event note. The free keyword match logs nothing --
   it makes no network call. Not yet done: a pre-click estimate before the person presses Evaluate (today's
   estimate is only known after the call, since it needs the actual token count), and the static price table
   isn't admin-editable yet (a `ScoreBand`-style admin screen would be the natural next step if prices drift
   enough to matter).
3. **Follow-up email nudges -- NEXT UP (queued, not started).** `EMAIL_HOST` is already wired for account
   confirmation; reuse it for "it's been N days since you applied to X" using the existing follow-up date
   field. No AI needed, cron-friendly (`manage.py` command + a scheduled task, same pattern as
   `check_liveness`). User has explicitly asked to come back to this one next.
4. **Recurring/scheduled scan with a digest.** Today's "Search jobs" is a one-shot manual click. Add an
   opt-in daily/weekly scheduled scan (cron + the existing `scan.py` machinery) with an email digest of new
   matches. No AI needed — pure scheduling on top of what exists.

### Tier 2 — closes the competitive gap, moderate effort

5. **Contact/networking tracker.** New `Contact` model (name, company, role, LinkedIn/email, notes, linked
   `Application`s), a simple CRUD UI. No AI needed.
6. **Interview scheduling + prep.** Promote the existing `Event(kind="interview")` into a first-class
   scheduled item with date/time/location/format, calendar export (`.ics`, no OAuth needed), and a static
   STAR-method question bank by role/seniority (free, no AI). Optional AI tailoring of likely questions from
   the JD layered on top later.
7. **Cover letters.** Reuses `cvgen.py`'s keyword-reorder approach for a free tier, and the existing AI
   provider plumbing for a generated version — same fact-check-gate discipline as CV tailoring, same
   immutable-version pattern. Directly closes the one documented "not built yet" item in `README.md`.
8. **Offer comparison tool.** New `Offer` model (base/bonus/equity/benefits per application), a simple
   side-by-side comparison view. No AI needed, no competitor does this well — a real differentiator.
9. **Referral tracking.** Add a `referred_by`/`referral_note` field on `Application` or a small `Contact`
   link; surface it in the dashboard and as an MCP field. No AI needed, no competitor has this.
10. **Dashboard search/filter.** The "All postings" page already has search/source filters
    (`views.py:328-353`); the main dashboard tabs don't. Add a search box + bucket/source/date filters to the
    dashboard itself — pure UI, no backend gap.

### Tier 3 — polish / scale prerequisites, do before claiming "production-ready for the public"

11. **Move rate limiting off in-process cache onto Redis** (`views.throttled()`, `docs/HOSTING.md:24`) —
    required before running more than one server process, which the scheduled-scan feature above will want
    anyway.
12. **Per-IP rate limiting + CAPTCHA on registration and free-tier scan/evaluate endpoints** — documented as
    missing in `docs/HOSTING.md:52`.
13. **Close the SSRF time-of-check/time-of-use (DNS-rebinding) gap** between `netguard.check_public_url` and
    the actual request (`docs/HOSTING.md:53`) — pin the resolved IP and request against it directly.
14. **Exercise PostgreSQL for real**, not just SQLite in CI (`docs/HOSTING.md:57`).
15. **Onboarding wizard + sample data for new signups.** Today a fresh account is a blank dashboard; a short
    wizard (set target roles → add first job or run first scan → optional AI key) plus one seeded example
    posting would cut first-session confusion. No AI needed.
16. **Outcome calibration** ("do high-scored jobs actually get interviews?") — purely derived from `Event`/
    status-change history already being collected; a good differentiator once enough data accumulates.
17. **Analytics dashboard** — response rate, funnel (applied → interview → offer), time-to-offer. Pure
    aggregation over existing data, no third party needed. No competitor reviewed has a strong version of
    this — another whitespace opportunity.

### Deliberately out of scope (keep as non-goals, don't build)

- **Browser extension** — explicit product decision: everything stays in one panel, no second codebase
  (extension manifest, per-browser store listings, separate update cycle) to maintain alongside the app.
  Tier 1 #1 (in-panel paste-URL quick add) and the recurring scan (Tier 1 #4) are the chosen substitutes.
- **Auto-apply / bulk-submit across sites** (LoopCV-style) — ToS/ethics risk and conflicts with StillOpen's
  own "never submits an application" principle.
- **Autofill across third-party ATS portals** (Simplify's flagship) — technically free but the highest
  ongoing maintenance burden of anything on this list (breaks whenever a target site's DOM changes); revisit
  only if the browser extension (Tier 1 #1) proves popular and users specifically ask for it.
- **LinkedIn scraping/search** — already correctly rejected on ToS/anti-bot grounds; "paste a URL into Add
  job" remains the right answer.

## 4. Reference prior art

- **Reactive Resume** (self-hosted, MIT, Next.js/Shadcn) — the closest reference for "self-hosted + no
  telemetry + API/MCP access" positioning; worth a direct look at its MCP tool surface before finalizing
  StillOpen's own.
- **JobSync**, **JobOps** — closest direct open-source competitors (self-hosted trackers with AI assistance);
  worth a feature-by-feature README comparison before finalizing the public positioning/marketing copy.
- **ApplyPotato** — email-based status detection (Gmail filters → status update) is a pattern StillOpen could
  borrow for a lighter-weight "still open" signal in addition to the existing HTTP/Playwright liveness check.

## 5. One-line answer to "what does this need to be a complete, usable, helpful app"

Ship the Tier 1 list (in-panel paste-URL quick add, cost transparency, follow-up emails, scheduled scan)
first — all four are buildable without any paid AI API, keep everything inside the panel (no extension), and
close most of the practical gap with Teal/Huntr/Simplify. Then Tier 2 (contacts, interview prep, cover
letters, offers, referrals) makes it a genuinely complete job-search product rather than "tracker + scorer."
Tier 3 is what turns it from "fine for me and a few friends" into something safe to host for strangers at
scale.
