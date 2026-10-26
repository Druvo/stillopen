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
OpenRouter/Groq/Gemini/Mistral/DeepSeek/GLM/Ollama/LM Studio, generic Custom HTTP, Claude Code CLI, Claude
Agent SDK), free keyword fallback that never overwrites a real score, SSRF-guarded outbound calls
(`netguard.py`), encrypted BYOK keys, output clamping/validation, job text always treated as untrusted data.
A "Quick setup" dropdown on Profile -> AI settings fills in the base URL and a starting model for 8 popular
providers (OpenAI, Gemini, Groq, Mistral, DeepSeek, OpenRouter, GLM/Zhipu, plus Anthropic direct; Ollama/LM
Studio for site admins only, since local URLs are admin-only by design) with no backend change needed --
they're all the existing "openai" provider type under the hood, just pointed at a different base URL.

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
| Generative resume rewrite / cover letter | yes (weak, per reviews) | yes | yes | — | some | tailoring yes, cover letters built (fact-checked, same approval gate as CVs) |
| Contact/networking tracker | — | yes | — | — | — | contacts page |
| Interview scheduling + reminders | — | yes | — | — | some | interviews page with notes + dashboard "Coming up"; **no email/calendar reminders yet** |
| Offer comparison (salary/bonus/equity) | — | — | — | — | — | offers page, ranked per currency (no FX guessing) |
| Analytics (response rate, funnel, time-to-offer) | — | partial | — | — | — | **none** beyond 4 summary numbers |
| Job alerts / saved recurring search | yes (board aggregation) | — | — | — | — | one-shot scan only, **no recurring/scheduled scan or digest** |
| **"Is this posting still open" live check** | — | — | — | — | — (ApplyPotato: via Gmail only) | **yes — a genuine differentiator, lean into it** |
| **Referral tracking** | — | — | — | — | — | referrals per contact and job (also via MCP) |
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
3. **Follow-up email nudges -- done.** `manage.py send_followup_emails` (cron-friendly, same `--user`/
   `--all-users`-by-default pattern as `check_liveness`) sends one digest email per person per run listing
   every newly-due follow-up -- never one email per job, never a repeat for the same `follow_up_date`
   (`Application.follow_up_emailed_for` tracks it; a snooze or a new date clears it naturally). Requires a
   verified allauth email address and `SiteConfig.followup_emails_enabled` (off by default -- admin opts in
   once SMTP/`EMAIL_HOST` is configured). No AI needed.
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
11. **Guided CV builder for a candidate with nothing yet -- done.** `services/cvbuilder.py` + `POST /api/v1/
    cv/build` + the app's `/cv/build` screen: a short, free Q&A (contact, summary, skills, experience,
    education, projects, certifications) assembles a first Markdown CV, no AI, nothing beyond what was typed
    -- an empty section is simply omitted, never filled with invented placeholder text. Saves through the
    same `cvversions.record_master` path as pasting a CV by hand, so RAG, matching and tailoring all pick it
    up identically; no separate code path to keep in sync. Entry points: the CV list's empty state and its
    page header. Not yet done: an optional AI layer to turn rough typed answers into better-phrased bullets
    (same fact-check-gate discipline as tailoring would apply if this is ever added).

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

## Update, 2026-10-26: this file is stale — most of Tier 2 shipped already

A large external merge (PR chain through #21, "feature/nextjs-*") landed most of Tier 2 and more, outside
this document's tracking: contacts/referrals (`Contact`/`Referral` models, `services/pipeline.py`), interview
scheduling (`Interview` model, `tracker/api/prep.py` interview prep plans), offer comparison (`Offer` model,
compared per currency, never converted), cover letters (`views_cover.py`, `services/cvgen.py`-style fact-
checked generation), dashboard search/filter (fully built in the new Next.js app's `FilterBar`), ~100 seeded
job sources including non-English-speaking-region coverage via Jooble (Bangladesh/Malaysia/Gulf,
`tracker/seed_sources.py`), a public job board (`/openings/`), and the whole classic-pages-to-Next.js
rewrite. Tier 3 hardening also mostly landed (CI in `.github/workflows/tests.yml`, self-hosting docs,
dependabot). Treat this file as a historical record of the Tier 1 work done directly in this conversation
(quick-add bar, skill-overlap discovery matching, AI cost/token transparency, AI provider Quick setup preset
dropdown, follow-up email nudges) rather than a current gap list — a fresh audit against the post-merge
codebase would be needed before trusting this file for planning again.

### Bangladesh job sourcing (researched + built, 2026-10-26)

No Bangladesh job board publishes a documented, officially-supported public API -- but "no official API" turned
out not to mean "not buildable": two sites had real, usable data behind the scenes once actually checked live
(network tab / page source), not just researched secondhand.

- **bdjobs.com** — its *listing pages* are a client-side app (no server-rendered HTML), but a live network
  trace found a real, clean, undocumented JSON search API its own front end calls
  (`api.bdjobs.com/Jobs/api/JobSearch/GetJobSearch`), confirmed to answer a plain unauthenticated GET from a
  server with no cookies. Built as `scan.fetch_bdjobs` -- architecturally identical to every other connector
  (zero-token, no headless browser), with one caveat the user was given before deciding to proceed anyway:
  bdjobs.com's own robots.txt disallows generic bots (`Disallow: /`, exceptions only for named crawlers it
  recognises).
- **bikroy.com Jobs** — the opposite situation: its listing pages ARE server-rendered (Nuxt 3), so a plain GET
  already returns every posting, just embedded in the page's own `__NUXT_DATA__` hydration script (a
  devalue-style array-of-references graph) rather than a clean JSON body. Built as `scan.fetch_bikroy`,
  decoded with a small generic resolver (`_nuxt_resolve`) rather than a library or a headless browser. Its own
  robots.txt does **not** disallow this path for generic bots -- the more permissive of the two.
- **Skill.jobs** — live-checked (network tab, `/browse-jobs`): no JSON API, job data ships inside Next.js RSC
  (`?_rsc=` streaming) payloads, not a stable/parseable format; also sits behind a Cloudflare bot-challenge.
  Not usable.
- **Chakri.com** — unreachable at check time (Cloudflare 523, origin down); moot regardless of robots.txt.
- **bdtechjobs.com** — explicitly, by name, blocks `Python-requests`/`curl`/`wget`/`Scrapy`/`Selenium`/
  `HeadlessChrome` in its robots.txt, plus a legal notice against automated extraction. The one site checked
  with an unambiguous, specific "no" rather than a generic catch-all -- correctly never built.
- **BASIS job board** — robots.txt allows everything, but there's no real job-board content there worth a
  connector.
- **BPSC / government circulars** — PDF notices only, no structured data anywhere. Not feasible.
- **Kormo Jobs (Google)** — discontinued (shut down mid-2022).
- **Chakri.ai/app/ChakriBarta** — third-party scrapers *of* bdjobs/chakri.com themselves, nothing original to
  connect to.

Both `fetch_bdjobs` and `fetch_bikroy` ship OFF by default -- not seeded anywhere in `seed_sources.py` -- an
admin adds the `JobSource` (any board_token, it carries no meaning for either) themselves if they want it.

### Open-source integrations added (2026-10-26)

- **GlitchTip / Sentry-compatible error tracking** -- self-hosted, open-source, speaks the same DSN/API as
  Sentry. Off by default: `sentry-sdk` only imports and initialises when `GLITCHTIP_DSN` or `SENTRY_DSN` is
  set (`config/settings.py`, `requirements-errors.txt`). `send_default_pii` stays off; job descriptions and CV
  text never get attached to an error report. See `docs/HOSTING.md` checklist item 6.
- **ESCO (EU skills/occupations taxonomy)** -- researched, then live-verified against this app's actual
  tech-keyword vocabulary (`docker` -> 0 results, `kubernetes` -> 0 results, `react` -> 93 mostly-irrelevant
  soft-skill results): a poor semantic fit, **declined**, not built.
- **Outcome calibration** -- no external dependency; derived from data the app already collects
  (`Interview`/`Offer` rows, match score). Added `pipeline.by_score()`: groups a person's own applied jobs by
  the match-percent band shown on the card, with interview/offer counts and rates per band, so "does a higher
  score actually lead anywhere?" has a real (if small-sample) answer. Surfaced on the existing Insights page
  (`frontend/src/features/pipeline/insights.tsx`) under "Does a higher match score lead anywhere?".

### LanguageTool writing check (built, 2026-10-26)

A "Check writing" button on CVs and cover letters, calling a LanguageTool server (self-hostable,
open-source, the `erikvl87/languagetool` Docker image, or pointed at the public `api.languagetool.org`
instance). Off by default like Paperless and GlitchTip: nothing is sent anywhere until an admin sets
`SiteConfig.languagetool_url` / `LANGUAGETOOL_URL`. Unlike those two, there is no separate "enabled" toggle --
a URL is the opt-in, since this is a one-shot read of text the person is already editing, not a standing
integration. `services/languagetool.py`, `POST /api/v1/cv/{id}/writing-check` and `/cover/{id}/writing-check`
(owner-scoped, rate-limited the same as other external checks via `STILLOPEN_CHECKS_PER_HOUR`), a shared
`writing_check_enabled` flag on `/me`.

### Recognized technologies on the job card, via O*NET (built, 2026-10-26)

ESCO (see earlier entry) was rejected after live-checking: zero hits for "docker"/"kubernetes", noisy
soft-skill-only hits for "react". The same live-check against the US Department of Labor's O*NET database
(its "Software Skills" table, part of the Tools & Technology content model) came back genuinely different:
28 rows mention Docker, 15 mention Kubernetes, and Software Developers alone lists React, Django, TypeScript
and more, each flagged "Hot Technology" when O*NET's own employer-postings analysis shows it is actually in
demand. Built as `services/techskills.py` + a bundled `tracker/data/onet_tech_skills.json` (8,741 distinct
product names, deduplicated from O*NET's public `software_skills.csv`, release 31.0, CC BY 4.0, no
registration or key needed -- a one-time download, not a live API call, since this is reference data that
doesn't change search results day to day). Surfaced as a new "Recognized technologies" panel on every job
card (zero-token, works with or without an AI key), separate from the existing free keyword match (whose
tested strengths/gaps output was left untouched rather than risk its pinned-string tests for a vocabulary
swap).

### USAJobs connector (built, 2026-10-26)

Unlike every Bangladesh site above, USAJOBS (the US federal government's own job board) publishes and
*supports* a real, documented public Search API (developer.usajobs.gov) -- no robots.txt trade-off to weigh at
all. Needs a free key (instant approval, no phone number) plus the email address it was requested with, which
USAJobs requires as the `User-Agent` header on every call alongside `Authorization-Key` and a fixed
`Host: data.usajobs.gov`. Built as `scan.fetch_usajobs`, wired in exactly like Jooble (a site-wide search over
the person's own target roles, needs the site's key to do anything, ships OFF by default). Two new
`SiteConfig` fields (`usajobs_api_key`, `usajobs_email`, both env-overridable) under Site configuration > Job
search keys, and a dormant-source dashboard banner matching the existing Jooble one.

### Weekly digest email (built, 2026-10-26)

A plain weekly summary (applications sent, interviews, offers, follow-ups due) email, mirroring the existing
scheduled-search-alert pattern exactly: a site-wide switch (`SiteConfig.weekly_digest_site_enabled`) and a
per-person opt-in (`UserProfile.weekly_digest_enabled`, under Profile > Job alerts), `manage.py
send_weekly_digest` for a weekly cron, nothing sent to anyone without a verified email, and nothing sent when
genuinely nothing happened that week (no "0, 0, 0" email). `UserProfile.weekly_digest_sent_through` stops a
cron run twice in the same week from sending two emails. `services/pipeline.py`'s `weekly_counts`/
`weekly_digest_text`/`send_weekly_digest`.

### LibreTranslate job-description translation (built, 2026-10-26)

A "Translate to English" button on a job's description, calling a LibreTranslate server (self-hostable,
open-source, the `libretranslate/libretranslate` Docker image). Same discipline as LanguageTool: off by
default, a URL is the opt-in, owner-scoped, rate-limited via `STILLOPEN_CHECKS_PER_HOUR`, result shown for
reading only and never saved. `services/libretranslate.py`, `POST /api/v1/jobs/{id}/translate`,
`translate_enabled` on `/me`.

### OpenCorporates (employer legitimacy check) -- checked, declined (2026-10-26)

`Application.legitimacy` already exists as a free-text field, unused by any automated signal. OpenCorporates
(open company registry data, real and credible) was the obvious candidate to back it. Checked live:
cross-checking a posting's employer against a real registry needs an API key, and the free tier is
**200 requests/month, 50/day site-wide** -- far too small for a multi-user app where dozens of distinct
employers show up per person per week. Worse, the free tier's own terms require the product the data is
incorporated into to also be released under an open, share-alike licence with OpenCorporates attribution --
a real legal condition on how this app is distributed, not just a usage cap. Declined for the same reason as
ESCO/H-1B above: checked live, found genuinely too limited for this app's actual scale, not a forced shortcut.

### H-1B / visa-sponsor employer data -- checked, declined (2026-10-26)

Two candidate sources, both checked live rather than assumed:

- **USCIS H-1B Employer Data Hub** -- not a bulk file: it is an interactive crosstab query tool (pick filters,
  "Download to Excel"), no static URL to fetch. Building this without a headless browser would mean either
  scraping the tool's own postback flow or reverse-engineering whatever endpoint it calls, neither checked here
  -- same "not investigated enough to trust" category as the sites this session never scraped.
- **DOL LCA Disclosure Data** (the actual source USCIS's own hub and third-party sites like myvisajobs.com are
  built from) -- genuinely a bulk download, but multi-hundred-thousand rows per fiscal year, several MB per
  file, and the column schema has changed across years. Bundling and keeping this current responsibly is a
  materially bigger, ongoing maintenance commitment than the bdjobs/bikroy/O*NET data bundled this session (all
  one-time, stable, CC/public-domain, a few hundred KB).

Declined for now, same discipline as ESCO and bdtechjobs.com earlier: checked live, not just researched, and
the honest finding is "not cleanly buildable at this session's scope" rather than a forced low-quality shortcut.

### Redis cache + a Postgres CI fix (2026-10-26)

- **Redis**: `REDIS_URL` + `requirements-redis.txt` switches Django's cache (and so the per-person rate limits
  and the search-source cache) from per-process memory to a shared Redis instance, using Django's own built-in
  `RedisCache` backend (no third-party wrapper needed). Unset, nothing changes -- still one process on purpose.
- **Postgres in CI**: already there (`.github/workflows/tests.yml`'s `test-postgres` job runs the full suite
  against a real `postgres:16-alpine` service) -- the "only exercised through SQLite" line in `docs/HOSTING.md`
  was stale and has been corrected.
- While checking CI: found and fixed a real regression from this session's earlier quick-add-bar removal --
  two Playwright e2e specs (`frontend/e2e/dashboard.spec.ts`) still referenced the dashboard's old quick-add
  widget, which had moved to the Add Job page; CI on `main` had been red across the last three pushes because
  of it (`vitest`/`tsc`/`eslint` don't run Playwright, so it went unnoticed locally).

**Jooble** also legitimately aggregates Bangladesh listings and is already wired in (`scan.fetch_jooble`,
`token="bd"`, seeded as "Jooble Bangladesh", enabled by default but inert without a key). Free key from
jooble.org/api/about, pasted into Site configuration > Job search keys —
`context.staff_flags`'s `jooble_sources_dormant` flag nudges a staff member with a dashboard banner exactly
when a site-wide Jooble source is enabled but no key is set.

Any Bangladeshi company using Greenhouse/Lever/Ashby/SmartRecruiters/Recruitee for its own careers page
already works automatically the moment it's added as a `JobSource` row — no new connector code needed.
