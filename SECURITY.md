# Security policy

StillOpen holds people's CVs and job-search notes, so security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Use GitHub's private reporting instead:
**Security tab > "Report a vulnerability"** on this repository. Include what you found, how to reproduce it, and the effect you
expect it to have. If private reporting is not available to you, open a plain issue asking for a private contact, without details.

You can expect an acknowledgement within a few days and a fix or a plan as soon as it is understood. We credit reporters who want credit.

## What counts

Anything that lets someone read, change or delete another person's data, run code or reach internal networks from the server,
or learn secrets. Examples we especially care about:

- crossing the **per-person isolation**: every job, CV, document, interview, contact, offer and cover letter belongs to one account;
- **server-side request forgery** through any address a person can supply (job links, AI endpoints, board names), see `tracker/services/netguard.py`;
- reading **stored API keys** (they are encrypted and write-only) or the Jooble/Paperless/SMTP secrets;
- bypassing **email confirmation**, rate limits or the sign-up bot traps;
- the **MCP server** exposing delete, settings, keys or file access (it must not);
- the **public job board** leaking a private board's postings or anything from a source marked not-public.

Out of scope: findings that need a malicious site administrator (administrators can read the database by design, and the
hosting guide says to keep that group small), missing hardening on a deployment that ignores `docs/HOSTING.md`, and
denial of service by raw traffic volume.

## Supported versions

Only the latest commit on `main` is supported. Run `git pull` and `python manage.py migrate` to update.

## How the app defends itself (for reviewers)

- Strict ownership: views, commands and MCP tools filter by owner; another person's row is a 404 (`tracker/tests_multiuser.py` and friends).
- Outgoing requests to user-supplied addresses refuse non-http(s) schemes and private, loopback, link-local and metadata addresses, hop by hop.
- Person-entered keys are encrypted at rest and never shown again; secrets never appear in MCP output, logs or error messages.
- Job text is untrusted: it is kept in data tags, model output is validated, and no model is given tools while it reads a posting.
- No third-party scripts, fonts or images on any page (`tracker/tests_selfhost.py`).
- Sign-up has a honeypot, a minimum fill time and per-IP limits; self-registered accounts confirm their email when email is configured.

If you deploy publicly, follow the checklist in [docs/HOSTING.md](docs/HOSTING.md) and [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md).
