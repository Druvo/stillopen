# Changelog

All notable changes. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no numbered releases yet; `main` is the
supported version, so entries are grouped under **Unreleased** until the first tag.

## [Unreleased]

- Sign-in: optional two-step sign-in for everyone (authenticator app, security key, recovery codes), and GitHub and Facebook sign-in beside Google, each with its own switch in the admin.

- PostgreSQL: the whole suite now also runs on PostgreSQL in CI; `docker-compose.postgres.yml` adds a database to the self-host setup; `manage.py copy_to_postgres` moves an existing SQLite install over and checks row counts. Background search and open/closed workers no longer close the calling thread's database connection.

- Public job board: every country in the world in the country filter (not just the top 40), plus filters for visa sponsorship, relocation help, kind of job, level and how recently posted. These are read from each posting's own words.

### Added
- **Open source under Apache-2.0**, with `LICENSE`, `NOTICE`, a code of conduct, a security policy, a contributing guide, issue and pull-request templates,
  Dependabot, and a self-hosting guide (`docs/SELF-HOSTING.md`).
- **Public side**: a landing page that explains the product with live numbers and charts, a public job board (`/openings/`) with search, filters and a
  page per opening, `robots.txt` and a sitemap. Only sources whose terms allow it are shown, with credit links, short excerpts and no JobPosting markup.
- **A standard look**: light by default with a remembered dark toggle, one brand colour, logo, system fonts only.
- **Jobs find themselves**: about 120 key-free sources ship by default (remote feeds and employer hiring boards, including Malaysia, the Gulf and Dhaka);
  a search starts when the dashboard opens, reads sources in parallel, drops jobs outside a person's places, scores the rest for free (skill coverage, no AI) and
  shows the best first. Optional Jooble connector for Bangladesh, Malaysia and the Gulf.
- Dashboard shows every job first, then filters (stage, search, fit, match, work, country, posting, found) and five sorts.
- Fact-checked **cover letters**; **interviews**, **contacts and referrals**, **offers** with comparison, an **Insights** funnel; interview reminders and
  opt-in job-alert emails; the same pipeline through the **MCP server**.
- Candidates can add their own company boards (private, guarded fetch).
- Operator tools: `check_email`, `check_jooble`, `refresh_postings`, `seed_sources`, `update_legal_text`; cron and Windows Task Scheduler files; plain-language
  privacy and terms templates; GitHub Actions running the tests and a migration check.

### Changed
- Sign-up works without SMTP (email confirmation applies only where email can be delivered), and the welcome page asks where a person would work.
- Search is about twice as fast (first jobs in about 25 seconds) with a visible progress bar.

### Fixed
- Greenhouse's escaped HTML no longer leaks tags into excerpts or match scoring; a fresh-install migration crash; wrong canonical URLs; and many smaller
  first-run problems found by walking the app as a new person.

[Unreleased]: https://github.com/Druvo/stillopen/commits/main
