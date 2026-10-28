# UX audit of the signed-in app

How it was done: `frontend/e2e/ux-audit.ts` (run with `playwright test -c playwright.audit.config.ts`, a copy of the README-images config) signs in as the demo person (`manage.py e2e_seed --demo`, "Jane") and takes a screenshot of every screen listed in `e2e/crawl.spec.ts` (25 screens) at 375, 768 and 1440 px in light and dark, 150 pictures in all. For each page it also records facts: sideways overflow, controls under 40 px, controls with no accessible name, whether there is an `<h1>`. The pictures were looked at by hand; the facts found two overflows and no unnamed controls. Request counts were taken with Playwright's response log.

Status: fixed = changed in this branch; kept = looked at and left on purpose; open = real, not done.

| Screen | Problem | Fix | Status |
| --- | --- | --- | --- |
| All postings, 375 | A long source name in the select pushed the page 200 px sideways | Every `select` gets `max-width: 100%; min-width: 0` (globals.css). Guarded by `polish.spec.ts` (no sideways scroll on 25 screens at 375) | fixed |
| CV compare, 375 | "Compare v3 with" select overflowed by 12 px | Row wraps; same select rule | fixed |
| Dashboard, 375 | The page opened scrolled about 1000 px down. The tab row called `scrollIntoView` on mount, which scrolls the whole page to the tabs, below five side cards | The row is now scrolled sideways only (`toolbar.tsx`). Test: dashboard opens at `scrollY` 0 | fixed |
| Whole app, 375 | No search at all on a phone (the header box is hidden under 768 px) | A header search button opens the palette | fixed |
| Whole app | Dates written four ways: `2026-10-28`, `Oct 31, 2026, 04:55 AM`, `29 Sep`, locale-dependent | One helper, `lib/dates.ts`: "29 Sep 2026", "Tue 3 Nov 2026, 14:30". Used on interviews, offers, contacts, CV versions, apply, postings, mail, AI usage, profile. Dashboard wording already matched | fixed |
| Dashboard, new person | Nothing says what the first steps are; five cards of advice compete | "Getting started" checklist (5 steps from data the dashboard already holds), closes for good (`checklist_dismissed`) | fixed |
| Whole app | No keyboard help, no way to jump to a screen | `?` help dialog, `/` and Ctrl/Cmd+K palette (screens and three safe actions), `g` then `d j c i p h`; "Keyboard shortcuts" in the user menu | fixed |
| Toasts | Errors left after 9 s, easy to miss | Errors stay 20 s (still dismissible); the live region is unchanged | fixed |
| Sign-out | A cache write queued just before sign-out could land after the clearing and leave the person's data in sessionStorage (the flaky "signing out removes what this tab kept") | The tab's storage refuses writes once sign-out starts; a half-made CV and a pasted job are cleared too | fixed |
| First load of the dashboard | `liveness/status` and `notifications/summary` were requested twice; every query was re-fetched right after being fetched, because the "refresh what the saved copy showed" step invalidated everything | It now invalidates only what came from the saved copy | fixed |
| `/api/v1/dashboard` | 45 queries (29 before the redesign). Profile read 4 times, site config 4, the user and time zone twice | Profile and zone passed down, `profile.user` kept: 40 queries. `tests_api_dashboard` now also asserts an absolute ceiling (45) | fixed |
| Dashboard | `/stats` is fetched with the dashboard though a card shows only when a goal is set or tiles use it | Kept: the stat tiles read it, and it is one small answer | kept |
| Lists with checkboxes (question bank, notifications) | Boxes are 24 px | Kept: 24 px meets WCAG 2.5.8, the whole label is the target, and phones get 44 px rows | kept |
| Inline text links (profile strength, postings) | 16-18 px high | Kept: links inside a sentence are exempt; standalone links use `link-target` (44 px on phones) | kept |
| Back links | "All versions", "Back to v3", an arrow "Dashboard" on Apply: three styles for one idea | Not unified: each is a real link and the sidebar and `g` shortcuts give a way back from every screen | open |
| Interviews, 375 | Card actions wrap into three rows of small buttons | Buttons are already 44 px high on phones; a menu would be tidier | open |
| Dark mode | Low-contrast text | None found by eye or by `a11y.spec.ts` (axe contrast, both themes) | kept |
| Focus rings | Missing or invisible | A global `:focus-visible` outline exists; the palette input has none of its own because the dialog frames it. A keyboard walk of the dashboard, apply and a CV (`polish.spec.ts`) found a ring on every control except the date field on Apply, where Chrome reports `:focus` false while the field is active (`:focus-within` did not help); not judged by the test | kept / open |
| Motion | Animations ignoring the OS setting | `globals.css` has one `prefers-reduced-motion` rule that cancels every animation and transition | kept |
| Empty states | Without a next step | None found: notifications, offers, question bank and companies each say what to do | kept |
