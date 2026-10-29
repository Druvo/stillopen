# StillOpen design system: Bento Grid (light) / Dark Command Center (dark)

Full redesign, 2026-10-29, superseding the earlier "Quiet Confidence" pass. The two modes are deliberately
different *moods*, not just inverted colours: light reads as clean, modular, Apple/Linear-style tiles on
neutral paper; dark reads as a focused, near-black pro tool (Linear/Raycast/Arc lineage) with the same accent
hue at full glowing brightness. They share one component system, one radius scale and one typeface (Albert
Sans for everything -- no separate display face this time). Routes, copy, information architecture and the
TailAdmin-derived layout (sidebar, spacing, type *sizes*) are unchanged -- this redesign is the colour/type/
radius layer plus the theme-default mechanism, same scope discipline as every redesign pass before it.

**Dark is the default**, shown to a first-time visitor before they pick for themselves. An admin can change
that default from **Site configuration > Appearance** in the Django admin -- see "Admin-configurable default"
below. A visitor's own choice, once made, always wins over either default (the existing "so-theme"
localStorage key, shared by both frontends, is untouched by this feature).

## What changed, and why

- **One accent hue, two brightnesses.** Both themes use the same hue family (an olive/lime green) but tuned
  for their own surface: light mode uses an accessible dark olive (`#4a6400`, 6.7:1 contrast on white -- a
  raw neon lime fails as text or a filled-button background, so it is reserved for decorative use only in the
  light mode mockup and was not carried into the real token set); dark mode uses the actual neon lime
  (`#c6ff3d`, 16:1+ contrast on near-black) because that brightness is exactly what reads correctly there.
  This is why the two modes don't look like a simple colour inversion of each other -- each accent is tuned
  for its own background, not shared as one fixed hex.
- **Palette: cooler, more neutral than the previous "Quiet Confidence" warm paper.** Light mode's background
  is a flat neutral light grey (`#f2f2f0`) instead of a warm cream; dark mode is a true near-black (`#0a0a0b`)
  instead of the previous warm charcoal. Shadows and focus rings moved from a warm brown-black tint to a
  neutral black tint to match.
- **Typography: one grotesque, bolder.** The previous pass paired a serif display face with a sans body.
  This one drops the serif entirely -- both the Bento Grid and Dark Command Center reference mockups used a
  single modern grotesque throughout, so `.so-display`/`.so-display-hero` (Django) and `font-display`
  (Next.js) now just mean "the body font, bolder and tighter" (weight 700/800, `-0.02em` tracking) rather
  than a separate face. Fraunces (the previous display face) was un-vendored; Albert Sans now carries both
  roles, matching how Bento/Command Center actually read.
- **Corner radius: larger, Bento-tile-ish.** `--tblr-border-radius`/`--so-radius` moved from 10/14px to
  12/18px -- generous enough to read as rounded tiles without the mockup's more extreme 22px (which would
  look odd on small buttons and inputs at real UI scale). Next.js's `Card`/`ErrorBox` moved to `rounded-2xl`
  (16px) to match.
- **Chart/category colours re-tuned for both surfaces.** The six decorative `--so-c1`..`--so-c6` colours
  (bars, donut rings, dots) were changed to a medium-saturation, medium-lightness set that stays visible on
  both a white card and a near-black one, since (unlike the primary accent) these are shared, theme-invariant
  values -- re-tuning per theme would have meant doubling every chart-colour token for a mostly-decorative set.
- **Admin-configurable default, applied without a rebuild.** See the mechanism section below -- this is new
  machinery, not just new colours.

## What this redesign deliberately did not touch

- Routes, page structure, section order, copy and information architecture -- all unchanged.
- The TailAdmin-derived layout system (sidebar, shadows' *shape*, spacing scale, type *sizes*) -- unchanged.
- No literal "bento box" or "terminal" layout reflow. The mockups explored layout as well as colour/type, but
  reflowing every existing page into an asymmetric tile grid (or a CRT-terminal chrome) would have meant
  rebuilding dozens of templates/screens from scratch, far beyond a token-level redesign. What carried over is
  the *mood* (palette, type weight, radius, one accent hue) applied through the existing shared component
  architecture -- the same scope boundary every redesign pass in this project has kept to.
- No motion library was added; the project stays motion-cut by choice.

## Admin-configurable default theme

- **Model**: `SiteConfig.default_theme` (`tracker/models.py`), choices `dark`/`light`, defaults to `dark`.
  Edited from the Django admin at **Site configuration > Appearance**.
- **Django public pages**: the `site_config` context processor (`tracker/context.py`, already registered)
  exposes `site_config.default_theme`; the four base templates (`public_base.html`, `legal.html`,
  `email_test.html`, `allauth/layouts/base.html`) render it straight into `<html data-bs-theme="...">`.
  `static/js/theme.js` only overrides that server-rendered default when the visitor has their own stored
  `so-theme` preference -- otherwise it leaves the server's choice alone (previously it always forced light on
  load, overwriting whatever a template happened to render).
- **Next.js app**: the static export can't read `SiteConfig` at build time, so the shell (`frontend/src/app/
  layout.tsx`) ships with a literal `data-default-theme="dark"` fallback alongside the real, live
  `data-theme="dark"` attribute Tailwind's `dark:` variant reads. `tracker/views_app.py`'s `app_shell()` view
  now reads the built `index.html` into memory (rather than streaming it untouched) and patches
  `data-default-theme="dark"` to whatever `SiteConfig.load().default_theme` currently is, on every request --
  so an admin's change takes effect immediately, with no frontend rebuild. The Content-Security-Policy hash
  computation is keyed on the *original* file's bytes/mtime, not the patched copy, and stays valid: the patch
  only ever touches an HTML attribute value, never the inline `<script>` tags the policy hashes.
- The visitor's own `so-theme` localStorage choice is checked first, client-side, before either default --
  unchanged from before this feature.

## Fonts

One font now, Google Fonts OFL-1.1 licensed, vendored locally (never loaded from Google at runtime -- checked
by `tracker/tests_selfhost.py`):

- **Django side**: `static/vendor/fonts/albert-sans-variable.woff2`, declared via `@font-face` in
  `static/css/stillopen.css`. See `static/vendor/fonts/NOTICE.md` for the hash and upgrade path.
- **Next.js side**: the *same file*, copied to `frontend/public/fonts/`, loaded with `next/font/local` in
  `frontend/src/app/layout.tsx`.

## Tokens

### Django (`static/css/stillopen.css`)

```css
--tblr-border-radius: 12px;         /* was 10px */
--so-radius: 18px;                  /* was 14px */
--so-display-font: var(--tblr-font-sans-serif);   /* was a separate serif, "Fraunces" */

[data-bs-theme="light"] {
  --tblr-primary: #4a6400;          /* was #11695f (teal) */
  --tblr-body-bg: #f2f2f0;          /* was #faf7f2 (warm paper) */
  --so-warning: #9c5f1f;            /* re-tuned for AA against white -- the old #b8752e was 3.73:1, below 4.5 */
}
[data-bs-theme="dark"] {
  --tblr-primary: #c6ff3d;          /* was #5fd0bf */
  --tblr-primary-fg: #0a0a0b;       /* dark text on a bright lime button, not white */
  --tblr-body-bg: #0a0a0b;          /* was #1b1815 (warm charcoal) */
}
```

`.so-display` is now `font-weight: 700` (was 560 on a serif), `.so-display-hero` is `font-weight: 800` (was
440) -- the same classes, every template that already uses them (`openings.html`, `opening_detail.html`,
`landing.html`, every `tools_*.html`) picks up the new weight with no template change needed.

### Next.js (`frontend/src/app/globals.css` + `frontend/src/components/ui.tsx`)

```css
--font-sans: var(--font-albert-sans), system-ui, sans-serif;
--font-display: var(--font-albert-sans), system-ui, sans-serif;   /* was Fraunces */
--brand: #c6ff3d;    /* dark, default */          --brand: #4a6400;   /* :root[data-theme="light"] */
--bg: #0a0a0b;        /* dark, default */          --bg: #f2f2f0;      /* :root[data-theme="light"] */
```

Note the `:root` block is now the **dark** palette by default, with `:root[data-theme="light"]` as the
override -- flipped from the previous pass, to match dark being the default theme. `PageHeader`'s `<h1>` is
`font-display text-[2rem] font-bold` (was `font-medium` on a serif). `Card` and `ErrorBox` in `ui.tsx` moved
to `rounded-2xl` (16px, was `rounded-xl`/12px).
