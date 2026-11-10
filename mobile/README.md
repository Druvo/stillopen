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

## What's built

The app now covers the website's screens, in the website's own light and dark colours (Albert Sans; the theme follows the saved
preference, dark by default). Tabs: Home, Postings, CVs and More; More lists everything else, grouped like the website sidebar.

- **Home**: board and list views, filters, "Find jobs now" with progress, guide cards, bulk actions, archive.
- **Jobs**: full job page (status, notes, "How you match", history), add / edit, apply assistant, all postings, saved searches, job sources.
- **After you apply**: interviews (with the calendar link), contacts and referrals, companies, question bank, offers, hiring-process timeline, Insights charts.
- **CVs and documents**: CV list/detail with the fact-check lock, builder, import, tailor, compare, "Ask for changes", ATS check, cover letters, documents.
- **Prep**: prep plans, today's practice, interview prep, message drafts (never sent).
- **Account**: profile, AI settings and usage, assistant tokens, notifications, help, data export/import, Google mail per job.

Where the app code lives: `app/` (routes), `src/screens/<area>/`, `src/api/<area>.ts`, shared kit in `src/ui` and theme in `src/theme.ts` +
`src/context/ThemeContext.tsx` (use `Text`/`TextInput` from `src/ui` and `useTheme`/`useStyles`, never a hard-coded colour).

## Known gaps

- Connecting a Google account needs the website (the OAuth return can't reach a phone session yet); everything after it works here.
- Adding or changing email addresses, and `.ics` downloads, are web-only.
- Text size and density are saved but not applied yet. Push notifications are not built (the backend sends none yet).
- Screens were checked in an Android emulator, not on iOS or a physical phone.
