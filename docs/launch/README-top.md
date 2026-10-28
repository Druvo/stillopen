<!-- Draft of the new top of README.md (replaces everything above "## Why run your own"). Not applied yet.
     Before publishing, replace the three TODO items: the demo GIF, the live demo link and the screenshots. -->

<p align="center">
  <img src="docs/images/logo.svg" alt="" width="72" height="72"><!-- TODO: add a logo or delete this line -->
</p>

<h1 align="center">StillOpen</h1>

<p align="center"><strong>Never apply to a dead job again.</strong><br>
StillOpen searches 100+ job sources for you, checks which postings are still open, flags reposts and ghost jobs,<br>
tailors your CV with a fact check, and tracks every application. Free, open source, self-hosted.</p>

<p align="center">
  <a href="https://stillopen.rnd.place">Live demo</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/MCP.md">Use it from Claude Code</a> ·
  <a href="docs/INSTALL.md">Install guides</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <a href="https://github.com/Druvo/stillopen/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/Druvo/stillopen/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"></a>
  <a href="https://github.com/Druvo/stillopen/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Druvo/stillopen"></a>
  <img alt="Self-hosted with Docker" src="https://img.shields.io/badge/self--hosted-Docker-blue">
</p>

<!-- TODO: a 15-20 second GIF: sign in -> a search finds jobs -> "still open" badges -> tailor a CV -> flagged claim shown -> move a card.
     Record with the seeded demo data (manage.py e2e_seed) so no real person appears. Keep it under 5 MB. -->
![StillOpen: a search finds open jobs, tailors a CV and tracks the application](docs/images/demo.gif)

> If StillOpen saves you a few hours of clicking through job sites, a star helps other job seekers find it.

## Why StillOpen

- **Finds the jobs for you.** 100+ built-in sources (company boards on Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee, plus remote-job feeds), searched in the background, no setup and no AI key.
- **Tells you what is still open.** Postings are checked for closing, and a job that keeps reappearing is flagged, so you stop applying to dead listings.
- **A CV that stays honest.** Tailored CVs and cover letters only use facts from your own material. Anything the AI adds that you did not write is flagged and cannot be exported until you approve it.
- **Your data stays yours.** One database on your machine or server. No ads, no tracking, no third-party scripts, fonts or images. Export or delete everything any time.
- **Use your own AI, or none.** Bring a key (Anthropic, OpenAI-compatible, Gemini, Groq, OpenRouter and more) or a local model, or just use the free keyword match.
- **Works with your assistant.** An MCP server lets Claude Code or any MCP client work with your search. It can read and organise, never send or delete.

## Quick start

```bash
docker run ...   # TODO: replace with the published image line once the first tagged release is out
```

or

```bash
git clone https://github.com/Druvo/stillopen.git
cd stillopen
docker compose -f docker-compose.selfhost.yml up -d --build
docker compose -f docker-compose.selfhost.yml exec stillopen python manage.py createsuperuser
```

Open <http://localhost:8000>. More ways to install (Compose, plain Docker, Ubuntu service, CapRover, Coolify, Dokploy): [docs/INSTALL.md](docs/INSTALL.md).

<!-- TODO: 4-6 screenshots in a table: dashboard list, board view, tailored CV with a flagged claim, "your numbers", job board.
     Capture at 1440x900 with the demo data. -->
