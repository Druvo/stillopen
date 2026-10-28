# Show HN draft

Title: Show HN: StillOpen – self-hosted job search that tells you which postings are still open

Body:
I got tired of applying to jobs that turned out to be closed or reposted for months, so I built StillOpen. It searches 100+ public job sources (company boards on Greenhouse/Lever/Ashby and remote-job feeds) in the background, checks whether each posting is still open, and flags ones that keep coming back. It scores fit against your CV, tailors a CV and cover letter with a fact check (anything the AI adds that you did not write is flagged and cannot be exported until you approve it), and tracks applications through to offers.

It works with no AI key (keyword match), or with your own key or a local model. It never sends anything on your behalf unless you press a confirm button, and nothing leaves your server. There is an MCP server so Claude Code can work with your search.

Django + Next.js, Postgres or SQLite, Apache-2.0. Live demo with sample data: <link>. Code: https://github.com/Druvo/stillopen

Things I would like feedback on: which job sources are missing for your country, and what you would want an "is this job a ghost?" signal to look at.

Posting notes: weekday morning US time; reply to every comment in the first two hours; do not ask for upvotes; be upfront about what is not built yet.
