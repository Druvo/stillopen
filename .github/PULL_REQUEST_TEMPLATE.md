## What and why

<!-- What does this change, and why is it needed? Link the issue if there is one. -->

## How it was checked

- [ ] `python manage.py test` passes (or the modules I touched, with the reason in the description)
- [ ] `python manage.py makemigrations --check --dry-run` shows nothing (I committed any migration)
- [ ] I looked at it in a browser, if a page changed

## Project commitments (see CONTRIBUTING.md)

- [ ] Anything personal stays per-person (owner field or filter, plus an isolation test)
- [ ] Nothing loads from a third-party host in the browser
- [ ] Addresses a person can type go through `services/netguard.py`
- [ ] Nothing is applied or sent on a person's behalf
- [ ] README or docs updated for anything a person or an operator will notice
- [ ] New job sources are hidden from the public board until their terms are checked
