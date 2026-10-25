# Design: a staged move to Next.js for the signed-in app

Status: **phases 0 and 1 built** (branch `feature/nextjs-phase0`): the API foundation, `frontend/`, the Docker build, CI job and the dashboard with board, list and drag-and-drop. Phases 2 to 5
are not started. Decisions taken by the owner: Django stays the backend; the new front end is a **static export** (no Node server in production); the **dashboard with drag-and-drop** comes first.
Open questions in section 12 were answered with the recommended options (django-ninja, pnpm, a per-person opt-in on top of a site switch, board columns grouped by the admin's tabs, sign-in restyle left to phase 5).
Written 2026-10-25.

## 1. Why, and what for

The owner wants, together: a faster, more modern look; more interactive screens (drag-and-drop job status first); and a front end that future JavaScript-framework features can
be added to. The current UI is Django templates with Tabler and a little JavaScript. It works and is private and fast to host, but every interactive idea means more hand-written
JavaScript inside templates.

The valuable, hard-won parts are in Python and **do not change**: the search engine, scoring, AI calls and their safety rules, per-person isolation, MCP, email, backups, the quiz
logic, 880+ tests. Only the screens are replaced, one at a time. This is a *strangler* migration, not a rewrite.

### Non-goals

- Replacing Django, the database, the admin, or the search and AI code.
- A Node server in production (revisit only if public pages ever need server rendering, section 9).
- Changing what the product does. The first release of every screen is feature-for-feature with today's.
- Any third-party host in the browser (fonts, scripts, analytics): the existing rule stays (section 8).

## 2. What exists today (inventory)

About 70 routes in `tracker/urls.py`, of which 24 already answer JSON (status, evaluate, liveness and scan start and status, quick add). Screens by area:

| Area | Screens |
| --- | --- |
| Core | dashboard (every job on one page, filtered and sorted in the browser), add job, job edit, all postings, welcome (3 questions) |
| Fit and documents | CV list, CV detail, diff, tailor, approve, restore, download and print; cover letters; documents (knowledge); apply assistant |
| Pipeline | interviews, contacts and referrals, offers, insights |
| Account | profile, AI settings, job sources, connect an AI assistant, export, delete account |
| Prep plans | list, draft review, plan, today's practice |
| Stays on Django | public landing and job board, privacy and terms, admin (Unfold), sign-in, sign-up, email confirmation and two-step screens (allauth), the MCP endpoint, file downloads |

## 3. Target architecture

```
browser ──► Caddy ──► Django (gunicorn)
                       ├─ /                 public landing and job board (templates, SEO)
                       ├─ /accounts/        sign-in, sign-up, MFA (allauth templates, restyled later)
                       ├─ /admin/           Unfold
                       ├─ /mcp/             MCP endpoint
                       ├─ /api/v1/          NEW: JSON API for the app
                       └─ /app/ and /app/**  NEW: the signed-in app shell (a static export built by Next.js)
```

- **Next.js (App Router) built with `output: 'export'`**, `basePath: '/app'`. The build produces plain HTML, JS and CSS. There is no Node process at run time.
- **Django serves the files.** A `login_required` view returns the app shell (`index.html`) for any `/app/**` path, so deep links work and a signed-out visitor is sent to the
  normal sign-in page with `next=`. The hashed assets under `/app/_next/**` are served by WhiteNoise like every other static file, with long cache headers.
- **Client-side routing.** Because there is no server to render dynamic pages, detail screens read the id from the path in a client component (one catch-all route) and fetch from the API.
  No server components that need a running server; React Server Components are used only for static layout at build time.
- **Same origin.** The app and the API share the host, so the browser's existing session cookie authenticates API calls and there is no CORS, no token in JavaScript and nothing new to leak.
  State-changing calls send Django's CSRF token in `X-CSRFToken` (the cookie is already readable by script, see `CSRF_COOKIE_HTTPONLY = False`).
- **Docker**: a multi-stage build. Stage 1 (Node) runs `npm ci && npm run build` and keeps only `out/`; stage 2 is today's Python image with `out/` copied in. The final image has no Node.
  Self-hosters still run one `docker compose up`. Running Django without the build (plain `pip` development) keeps working: the new UI is off and the old templates serve.
- **Development**: `npm run dev` (Turbopack, hot reload) proxies `/api` and `/accounts` to Django on port 8765, so the same session cookie works while developing.

## 4. The JSON API (`/api/v1/`)

Choice (to confirm in section 12): **django-ninja** (typed schemas, OpenAPI for free, a generated TypeScript client with `openapi-typescript`) over Django REST Framework (more
batteries, more ceremony). Either works; what matters is the rules below.

**Isolation, the part that must not regress**

1. One router-level dependency does authentication (session) and attaches `request.user`; there is no route without it. Unauthenticated calls answer 401 JSON, never a redirect.
2. Every query goes through owner-scoped helpers (`owned(Application, request)` and the like); a row that is not the person's answers **404**, the same as today.
3. A **route inventory test** walks the OpenAPI schema and, for every route, asserts: signed-out gives 401; a second person's id gives 404; unsupported methods give 405. A new route cannot be added without these
   being checked, because the test enumerates routes instead of listing them by hand.
4. The existing service functions are reused (`services/*`, and the plain functions in `mcp_tools.py`, which already do "act for one person"). The API is a thin layer; business rules stay where they are.
5. Throttles (evaluations, scans, CV generation, prep runs) are the same ones the HTML views use.

**Conventions**: JSON in and out; errors as `{ "error": "plain words" }` with the status; lists paginated where they can grow (postings, answers), whole where they are small (a person's jobs);
dates ISO; ids integers; no secrets ever in a response (AI keys, SMTP, tokens stay write-only).

**Endpoints by phase** (names indicative):

| Phase | Endpoints |
| --- | --- |
| 1 | `GET /me`, `GET /dashboard` (jobs with fit, flags, insights, next step), `PATCH /jobs/{id}/status`, `POST /jobs/{id}/evaluate`, `POST /scan`, `GET /scan/status`, `POST /liveness`, `GET /liveness/status`, `GET /statuses` |
| 2 | prep plans: list, get, create, start, discard, remove, tick, today, answer |
| 3 | jobs (add, edit), CVs, cover letters, documents, apply assistant |
| 4 | interviews, contacts and referrals, offers, insights, profile, AI settings, sources, assistant tokens, export, delete |

## 5. The front end

- **Stack**: Next.js (App Router), React, TypeScript (strict), Turbopack (Next's own bundler, used by `dev` and `build`), Tailwind CSS, shadcn/ui (Radix primitives, copied into the repo), lucide icons,
  TanStack Query for server state, **dnd-kit** for drag-and-drop, Zod for the few client-side forms, Vitest and Testing Library for components, Playwright for end-to-end.
- **Font**: Geist, installed from npm (`geist`) and loaded with `next/font/local`, so it is served from our own host at build time. Geist is open (SIL OFL); the licence file ships in the repo.
- **Look**: light by default with a remembered dark mode (same as the public site), a neutral palette plus StillOpen's blue, generous spacing, the same plain-words copy.
- **Layout in the repo**: `frontend/` (its own `package.json`, `pnpm-lock.yaml`), not mixed into `tracker/`. `frontend/src/api/` holds the generated client; `frontend/src/features/<area>/` holds screens.
- **Accessibility**: keyboard and screen-reader paths are part of "done". Drag-and-drop has a keyboard sensor and a non-drag alternative (a status menu on every card); live regions announce moves and errors.

### The dashboard (phase 1, in detail)

Today: one page with every job as a card, tabs by stage, search, sort, filters, a match bar, badges, "Check my fit", tailor, prepare, apply, search status, the next-step card.

New:

- A **board view** (columns = statuses grouped as the admin configured them: Saved, Evaluated, Applied, Responded, Interview, Offer...) and a **list view** (today's layout). The person picks; the choice is remembered in `localStorage`.
- **Drag a card to another column to change its status**, calling the same rule the HTML view uses (`set_status`: stamps the applied date for statuses that count as applied, writes the timeline event). The move is **optimistic** and rolls back with a message if the API refuses.
- Filters, search and sorting stay client-side (the data is small: a person's own jobs). The job list is fetched once and cached; scan and liveness progress poll the status endpoints every 2 seconds only while running.
- Every action on today's card stays: check fit, tailor CV, cover letter, prepare, apply page, edit. Links to screens not yet migrated go to the Django pages, so nothing is lost mid-migration.
- Done when: all of today's dashboard behaviour is present, drag-and-drop works by mouse, touch and keyboard, and the old dashboard can be switched off without anyone missing something.

## 6. Migration plan (strangler)

A site setting **New app (beta)** (admin, off by default) plus a per-person toggle in the profile controls whether the main navigation points at `/app/...` or the old pages. Both UIs read the same
database, so there is nothing to migrate and rollback is flipping the switch.

| Phase | Scope | Rough effort (part-time, one developer) | Exit criteria |
| --- | --- | --- | --- |
| 0 | API foundation: router, auth, owner helpers, route-inventory test, OpenAPI, TypeScript client generation, `frontend/` scaffold, Docker multi-stage build, CI jobs, the app-shell view, Geist, the layout and design tokens | 1 to 2 weeks | a signed-in "hello" page at `/app/` in the production image; CI builds, lints, type-checks and runs Playwright smoke; isolation test live |
| 1 | Dashboard with board, list and drag-and-drop; search and liveness progress; welcome | 1 to 2 weeks | parity checklist signed off; Playwright covers drag, keyboard move, filters, optimistic rollback and two-person isolation |
| 2 | Prep plans and practice (they are new, so React-first costs nothing extra) | 1 week | all prep pages in React; old templates removed |
| 3 | Add and edit job, CVs (diff, approve, download), cover letters, documents, apply assistant | 2 to 3 weeks | each screen has parity and tests |
| 4 | Pipeline (interviews, contacts, offers, insights), profile and AI settings, sources, assistant tokens, export, delete | 2 to 3 weeks | old candidate templates deleted |
| 5 | Optional: restyle allauth screens to match; decide on the public site and admin | open | owner's call |

Rules while migrating: no feature work on a screen that is mid-move except bug fixes; every migrated screen keeps its Django URL working (redirecting to the new one when the switch is on) so bookmarks and emails keep working; the old
templates are deleted only after the new screen has been live for a release with no regressions.

## 7. Testing and CI

- Python: unchanged; plus the route-inventory test and an API test per endpoint (happy path, validation, isolation, throttle).
- Front end: `tsc --noEmit`, ESLint (with a rule banning `dangerouslySetInnerHTML`), Vitest for components and the API client, **Playwright** against the built production image (log in, drag a card, keyboard move, refresh and see it persisted, a second person cannot see the first's job).
- New CI jobs: `frontend` (install, lint, type-check, unit, build) and `e2e` (compose up, Playwright). Existing `test` and `test-postgres` stay required.
- A generated-client check: CI regenerates the TypeScript client from the OpenAPI schema and fails if it differs from what is committed, so the two cannot drift.

## 8. Security and the project's rules

| Rule | How the new front end keeps it |
| --- | --- |
| Strict isolation | Section 4: router-level auth, owned helpers, the enumerating route test, Playwright cross-person test |
| No third-party hosts | Geist and every asset are bundled; the Playwright run fails on any network request to another host; the existing `tests_selfhost.py` also covers the shell page |
| Untrusted job and model text | Rendered only as React text (escaped). No `dangerouslySetInnerHTML`, enforced by lint. Source links use `rel="noopener noreferrer"` |
| No secrets in the browser | Session cookie only (HttpOnly). No tokens in JavaScript or `localStorage` |
| CSRF | `X-CSRFToken` header on every state-changing request; Django's middleware stays on |
| Content Security Policy | Today there is none. A static Next export has small inline bootstrap scripts, so a strict policy needs script hashes generated at build time. Plan: ship without a CSP first (as today), add a hash-based CSP in phase 5 |
| App never acts for the person | Unchanged: no screen submits an application or sends a message; the server-side rules still decide |
| Plain words, empty states | Copy is carried over from the templates; each screen's empty state says what to do next |

## 9. Decisions and alternatives

- **Static export vs a Node server.** Static export keeps self-hosting at one container and removes a runtime to patch and monitor. What it gives up: server-rendered pages (not needed behind a login), Next's image optimiser and middleware (not needed). If the public job board ever
  needs a React front end for SEO, that is the moment to add a Node service for those routes only. Until then the public site stays on Django.
- **Next.js vs Vite + React.** Vite would also give a static SPA with less machinery. Next is chosen by the owner for its routing conventions, ecosystem and the possibility of server features later. The cost is a heavier toolchain; the export mode keeps the runtime light.
- **Own API vs reusing MCP tools.** The MCP functions are the right *service layer* to reuse, but MCP's tool shape (flat arguments, text results) is wrong for a UI. The API is a separate, typed layer over the same services.
- **django-ninja vs DRF.** Ninja: typed, OpenAPI-first, small. DRF: mature, larger. Recommendation: ninja, because the generated client and schema-driven tests are central to this plan.
- **Drag-and-drop library.** dnd-kit (accessible, keyboard support, maintained) over react-beautiful-dnd (unmaintained) or hand-rolled.
- **Why not a single big rewrite.** Feature freeze for months, parity bugs, and a second chance to break isolation in 20 places at once. The staged route ships something users can see after phase 1.

## 10. Self-hosters and contributors

- Running StillOpen is unchanged: `docker compose up`. The image build is longer (a Node stage) but the image is no bigger for it.
- Contributors who only touch Python do not need Node; the new UI is simply off in their dev setup. Front-end contributors need Node 22 or later and pnpm; `CONTRIBUTING.md` and `docs/SELF-HOSTING.md` get a short section each.
- Updates: `git pull` and the usual compose command; the app shell and API ship together in one image, so there is no version skew to manage.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| An endpoint forgets owner filtering | Router-level auth, owned helpers, the enumerating isolation test, code review checklist |
| Two UIs drift while both exist | Business rules only in services; API is thin; the old UI gets bug fixes only; short phases |
| Drag-and-drop is inaccessible | Keyboard sensor, a status menu on every card, Playwright keyboard test |
| Build toolchain churn (Next, React, Tailwind move fast) | Pin versions, Dependabot with the full CI, one upgrade window per quarter |
| Deep links and refresh on a static export | Django serves the shell for any `/app/**`; Playwright tests refresh on a detail route |
| Bundle size and speed regress | Budget in CI (bundle size check), code-split per feature, measure the dashboard with a few hundred jobs |
| Maintenance load for one developer | Strict phase exits; delete old templates promptly; keep the stack boring (no state libraries beyond TanStack Query) |

## 12. Open questions for the owner

1. django-ninja (recommended) or Django REST Framework?
2. pnpm (recommended) or npm?
3. Is a per-person "try the new app" toggle enough, or should phase 1 go live for everyone at once once the parity checklist passes?
4. Board columns: one column per status, or grouped by the admin's tabs (fewer columns)? Recommended: grouped by tab, with the status shown on the card.
5. Should phase 0 also restyle the sign-in screens, so the first impression matches the new look?

## 13. Definition of done for the whole move

The candidate area has no Django templates left except those intentionally kept (section 2); `tests_multiuser` and the API isolation tests pass; CI builds and tests the front end; the production image runs the app with no Node; the dashboard
loads a few hundred jobs fast on a phone; every old URL still lands somewhere sensible.
