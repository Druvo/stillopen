# StillOpen mobile (Android + iOS)

Expo Router app, same backend as the website (`tracker/api/` on the main Django project), authenticated with a
personal access token instead of the web app's session cookie. See `tracker/api/mobileauth.py` on the backend side.

## Run it

```bash
cd mobile
npm install
npx expo start
```

Set `EXPO_PUBLIC_API_BASE` (in `.env` or your shell) to the backend's address before starting, e.g.:

```
EXPO_PUBLIC_API_BASE=http://192.168.1.23:8000
```

`localhost`/`127.0.0.1` only reaches the backend from the same machine; a physical device needs your computer's LAN
IP, and the Android emulator needs `10.0.2.2` in place of `localhost`.

Sign in with any existing StillOpen account (same username/password as the website).

## How auth works

- `POST /api/v1/auth/login` (public, rate-limited) takes username/email + password and returns a bearer token --
  a normal `ApiToken`, the same kind made under Profile > Connect an AI assistant, so it also works against `/mcp/`
  and shows up on, and can be revoked from, that same list.
- Every other call sends `Authorization: Bearer so_...` instead of a cookie. The token is kept in
  `expo-secure-store`, never `AsyncStorage`/plain storage.
- `POST /api/v1/auth/logout` revokes the token that request used.
- A CV download (`cv_download`/`cv_print`/`job_documents_zip`, classic Django views, not JSON) also accepts the
  same bearer token via `bearer_or_login_required` in `tracker/api/mobileauth.py`, since those return files, not
  JSON, and a mobile client has no session cookie to use.

## What's built so far

- Sign in / sign out, token persisted across restarts
- Dashboard: stats, "Worth a look next", job list with match score
- Job detail: status change (the board's columns), fit check, notes, next action
- CV list (master + tailored) and CV detail: full text, the fact-check lock/approve flow, DOCX/Markdown download
  via a proper authenticated download + native share sheet (not a browser hop)
- Profile: read-only, sign out

## Not built yet (real feature-parity backlog)

The web app's JSON API is large (`/api/v1/openapi.json` lists 100+ routes). This first pass covers the daily-use
core; the rest is still backend-API-ready, just not wired into a screen yet:

- Cover letters (view/edit/refine/approve, same pattern as CV)
- Documents (upload, Paperless linking)
- Interviews, offers, referrals, contacts, companies -- the whole post-"Applied" pipeline
- Prep plans / quiz
- Saved searches, job sources, "Add a job" / paste-a-link quick-add
- Notifications list (only the unread count is wired in; no screen yet)
- Profile editing (roles, places, CV text, preferences, AI settings)
- Insights/stats charts
- Google connection, calendar feed
- Push notifications (would need a server-side piece too: APNs/FCM registration, nothing in the backend sends these yet)

Each of these already has a working `/api/v1/...` endpoint (see `tracker/api/routes.py` and friends) -- this is a
UI backlog, not a backend one.
