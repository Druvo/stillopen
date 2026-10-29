# Third-party material in the new app

## TailAdmin free Next.js admin dashboard (MIT)

The look of the app (colour scales, shadows, type sizes, the fixed sidebar with a mobile drawer, the sticky header, menu and card
styles) is adapted from TailAdmin's free Next.js dashboard: https://github.com/TailAdmin/free-nextjs-admin-dashboard

Only styles and layout ideas were taken (see `src/app/globals.css` and `src/components/app-shell.tsx`). Its demo pages, charts, fonts
(it loads Outfit from Google; this app vendors its own fonts instead, below) and images are not included.

```
MIT License

Copyright (c) 2023 TailAdmin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Alumni Sans and Albert Sans (SIL Open Font License 1.1)

The display and body typefaces (see `src/app/layout.tsx`, loaded with `next/font/local`) are Google Fonts'
Alumni Sans and Albert Sans, vendored as `public/fonts/*.woff2` -- the same files as the public pages'
`static/vendor/fonts/`, see that folder's `NOTICE.md` for the source and SHA-256 hashes. Licensed under the
SIL Open Font License, 1.1: https://openfontlicense.org/
