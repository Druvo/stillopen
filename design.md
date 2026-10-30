# StillOpen design system

Studied from [impeccable.style](https://impeccable.style/) (2026-10-29, URL mode: exact fonts/colours pulled
from the live DOM's computed styles, not guessed). Applied as a **theme-drift adoption**, not a pixel clone --
the DNA is the type pairing and corner radius; StillOpen's own brand blue, routes, copy and information
architecture are unchanged. Two separate frontends share this system: the public pages (Django + Tabler) and
the signed-in app (Next.js + Tailwind).

## What changed, and why

- **Type pairing.** Display headings now use **Alumni Sans** (a tall, condensed grotesque) at a light weight;
  body/UI text uses **Albert Sans** (a plain humanist grotesque). This was the single most distinctive move in
  the studied reference -- a page's biggest headline at an ultralight weight reads as considered restraint
  rather than a generic bold sans-serif default.
- **Corner radius, sharpened.** Buttons, cards, inputs and panels went from Tabler's default 8-12px / Tailwind's
  `rounded-xl`/`rounded-2xl` down to 4-6px (`rounded-sm`/`rounded-md`). Decorative pill shapes (stat badges,
  avatars, progress bars) are left alone -- a pill is a different, still-valid shape, not a radius mistake.
- **Brand colour: unchanged.** The reference site is almost achromatic; StillOpen keeps its existing blue
  (`#2563eb` / `--brand: #465fff`) as the one accent, per the redesign discipline of preserving brand.
  Structure, routes, and copy are unchanged too.

## Fonts

Both are Google Fonts, OFL-1.1 licensed, vendored locally (never loaded from Google at runtime -- this
project's self-hosting discipline is non-negotiable, checked by `tracker/tests_selfhost.py`):

- **Django side**: `static/vendor/fonts/{alumni-sans,albert-sans}-variable.woff2`, declared via `@font-face` in
  `static/css/stillopen.css`. See `static/vendor/fonts/NOTICE.md` for hashes and the upgrade path.
- **Next.js side**: the *same two files*, copied to `frontend/public/fonts/`, loaded with `next/font/local` in
  `frontend/src/app/layout.tsx` (zero network requests, Next.js self-hosts and subsets them at build time).

## Tokens

### Django (`static/css/stillopen.css`)

```css
--tblr-font-sans-serif: "Albert Sans", system-ui, ...;
--so-display-font: "Alumni Sans", var(--tblr-font-sans-serif);
--tblr-border-radius: 4px;   /* was 8px */
--so-radius: 6px;            /* was 12px */
```

`.so-display` (font-weight 340) and `.so-display-hero` (font-weight 230, the page's one biggest statement)
apply the display font; everywhere a page's `<h1>` used Bootstrap's `fw-bold` utility, that was replaced with
these two classes instead (`openings.html`, `opening_detail.html`, `landing.html`, every `tools_*.html`).

### Next.js (`frontend/src/app/globals.css` + `frontend/src/components/ui.tsx`)

```css
--font-sans: var(--font-albert-sans), system-ui, sans-serif;     /* was Geist */
--font-display: var(--font-alumni-sans), var(--font-albert-sans), system-ui, sans-serif;
```

`PageHeader`'s `<h1>` (used by every screen in the app) now reads `font-display text-[2rem] font-light` instead
of the plain body font at `font-semibold`. `buttonClass`, `Card`, `Notice` and `ErrorBox` in `ui.tsx` -- the
shared primitives nearly every screen renders through -- carry the sharper radius centrally, along with a
handful of panels that had their own bespoke `rounded-2xl`/`rounded-xl` outside those primitives
(`app-shell.tsx`'s account menu, `board.tsx`'s kanban column, `dashboard.tsx`'s empty state, `job-card.tsx`,
`toast.tsx`).

## What this redesign deliberately did not touch

- Routes, page structure, section order, copy and information architecture -- all unchanged.
- The brand accent colour -- unchanged.
- The TailAdmin-derived layout system (sidebar, shadows, spacing scale, type *sizes*) -- unchanged; only the
  *face* and *radius* carry the studied DNA, per the redesign discipline of replacing only what the brief asked
  for.
