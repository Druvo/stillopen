# Alumni Sans and Albert Sans (vendored)

`alumni-sans-variable.woff2` and `albert-sans-variable.woff2` are the variable-weight latin subsets of the
Google Fonts families **Alumni Sans** and **Albert Sans** (fetched directly from `fonts.gstatic.com`, the same
files Google Fonts itself serves, and kept here rather than linked so no visitor's browser contacts Google).
Both are licensed under the SIL Open Font License, 1.1: https://openfontlicense.org/

SHA-256:

    49015c322cbd9ee7fbfbdb25295a57a5ba4b35e6f9c92c6d42fd570267e45c36  alumni-sans-variable.woff2
    c2fb6fda415c7bf5926c15aa98f759da45cdc5ac4ac6925a72a84db4eb3862a3  albert-sans-variable.woff2

To upgrade, fetch the same family's latin-subset `U+0000-00FF...` woff2 from
`https://fonts.googleapis.com/css2?family=<name>:wght@100..900`, replace the file, and update this note.
Used for the site's display heading (Alumni Sans, a tall condensed grotesque at a light weight) and body/UI
text (Albert Sans). The same two files are copied to `frontend/public/fonts/` for the signed-in app, loaded
there with `next/font/local` -- no second download, same bytes.
