# Albert Sans (vendored)

`albert-sans-variable.woff2` is the variable-weight latin subset of the Google Fonts family **Albert Sans**
(fetched directly from `fonts.gstatic.com`, the same file Google Fonts itself serves, and kept here rather
than linked so no visitor's browser contacts Google). Licensed under the SIL Open Font License, 1.1:
https://openfontlicense.org/

SHA-256:

    c2fb6fda415c7bf5926c15aa98f759da45cdc5ac4ac6925a72a84db4eb3862a3  albert-sans-variable.woff2

To upgrade, fetch the same family's latin-subset `U+0000-00FF...` woff2 from
`https://fonts.googleapis.com/css2?family=Albert+Sans:wght@100..900`, replace the file, and update this note.
Used for both the site's display headings and body/UI text -- see design.md for why one grotesque carries
both roles. The same file is copied to `frontend/public/fonts/` for the signed-in app, loaded there with
`next/font/local` -- no second download, same bytes.
