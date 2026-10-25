# Use StillOpen from an AI assistant (MCP)

StillOpen speaks [MCP](https://modelcontextprotocol.io), so Claude Code, Cursor, Windsurf and any other MCP client can work with your job search directly:
list your jobs, judge fit against your CV, save an honest match, tailor a CV, add notes and track interviews, contacts and offers.

There are two ways to connect. Use the first if you use a website (yours or a shared one); the second if you run StillOpen on your own computer.

## 1. Over the web, with a personal token (any StillOpen website)

1. Sign in, then open **Profile > Your account > Connect an AI assistant**.
2. Give the token a name (for example *Claude Code on my laptop*), pick **Read only** or **Read and make changes**, and how long it should last. Press **Make token**.
3. Copy what the page shows. It is displayed **once**; StillOpen keeps only a hash, so a lost token cannot be recovered, only replaced.
4. In a terminal, paste the command it gives you. For Claude Code it looks like:

```bash
claude mcp add --transport http stillopen https://YOUR-SITE/mcp/ --header "Authorization: Bearer so_..."
```

Other assistants take the same three things (address, `Authorization: Bearer ...` header, HTTP transport) in their MCP settings; the page also shows a JSON snippet.

Then ask things like *"summarise my job search and what to apply to next"*, *"judge my saved jobs against my CV and save an honest match"* or *"tailor my CV for the Acme role"*.

**What a token can and cannot do**

| | |
| --- | --- |
| Whose data | Only the person who made it. Every tool runs as that person; another person's jobs return "not found" |
| Read only | Can list and read (jobs, profile, CV versions, interviews, offers, prep plans). Cannot change anything, and does not even see the tools that do |
| Read and make changes | Can also add jobs, notes, evaluations, interviews, contacts and offers, save a tailored CV, and record that *you* applied |
| Prep plans | `list_prep_plans` and `get_prep_plan` read; `request_prep_plan` (needs a read-and-change token) starts a plan for a job. It always arrives as a **draft** written by the person's own AI account, with the same limits as the app. It never returns practice questions or answers, and there is no tool to approve or start a plan: only the person can, in the web app |
| Never | Delete anything, read settings, API keys or files, approve a flagged CV, start or approve a prep plan, apply to a job or send a message for you |
| Revoke | Press **Revoke** on the same page: it stops working immediately. Tokens also expire (30 days, 90 days, 1 year or never) |
| Limits | 10 active tokens per person; 120 calls a minute per token; repeated wrong tokens from one address are blocked for a minute |

What the assistant reads (your CV, notes, job text) goes to the AI company behind that assistant. Use one you are comfortable with, and start with a read-only token.

Job descriptions are text copied from other websites. StillOpen labels them as untrusted and tells the assistant to treat them as data, but only give a *Read and make changes* token to an assistant you trust.

## 2. On your own computer (no token, no network)

If StillOpen runs on the same machine, the local server needs no token. It talks to your database directly and listens on nothing:

```bash
claude mcp add stillopen -- python /path/to/stillopen/mcp_server.py
```

It acts for the only superuser, or for the account named in the `STILLOPEN_USER` environment variable.

## Running a website: switches and settings

- **Turn it off:** admin > Site configuration > Dashboard > *Mcp remote enabled*. The page disappears and `/mcp/` answers 404.
- **Limits** (environment): `STILLOPEN_MAX_API_TOKENS`, `STILLOPEN_TOKEN_ISSUES_PER_HOUR`, `STILLOPEN_MCP_CALLS_PER_MINUTE`, `STILLOPEN_MCP_BAD_TOKENS_PER_MINUTE`.
- **Behind a proxy:** keep `/mcp/` on HTTPS and set `ALLAUTH_TRUSTED_PROXY_COUNT` so the wrong-token limit sees the caller, not the proxy (`manage.py check` warns when `DJANGO_BEHIND_PROXY=1` is set without it).
- **Several workers:** the per-token call limit is counted in Django's cache. With one worker that is process memory; with more than one, set `REDIS_URL` (see docs/SELF-HOSTING.md, "More than one worker") so all workers share the count.
- The endpoint is the simple, stateless form of MCP's streamable HTTP: one JSON reply per POST, no sessions, no browser cookies (so there is nothing for a cross-site page to ride on).
