# Handoff: mobile app + device testing (2026-11-09)

Session summary for whoever continues this. Covers what was built, what's verified, what's not, and a few
environment quirks on this machine that cost a lot of time to diagnose -- read the "Environment quirks" section
before debugging anything that looks like a networking or process-management bug.

## What was asked

"I need an android app for this site. android and ios and this site as BE" -- a native mobile client (Android +
iOS) for StillOpen, using the existing Django site as the backend. Scope decided with the user: React Native
(Expo), full feature parity as the eventual goal, starting with the daily-use core.

## What's done

### Backend (`E:\stillopen`)
- `tracker/api/mobileauth.py` (new): bearer-token auth for `/api/v1/`, reusing the existing `ApiToken` model (the
  same personal-access-token system already used for the web MCP endpoint, `/mcp/`). `POST /api/v1/auth/login`
  (public, rate-limited by IP) exchanges username/email + password for a token; everything else authenticates via
  `Authorization: Bearer so_...`. `POST /api/v1/auth/logout` revokes it.
- `tracker/api/routes.py`: `auth=[BearerAuth(), django_auth]` -- **order matters**, see the comment in the diff;
  `django_auth`'s CSRF check runs unconditionally on unsafe methods before it even checks for a session, so it has
  to come second or it blocks every bearer-authenticated POST.
- `tracker/views_cv.py`: `cv_download`/`cv_print`/`job_documents_zip` now use `bearer_or_login_required` (also in
  `mobileauth.py`) instead of plain `@login_required` -- these are classic Django views (they return files, not
  JSON), so a mobile client needs its own way in since it has no session cookie.
- `config/settings.py`: `STILLOPEN_MOBILE_LOGIN_ATTEMPTS_PER_HOUR` (default 20).
- `tracker/tests_mobileauth.py` (new, 14 tests) + one fix in `tracker/tests_api.py` (the route-inventory test now
  exempts the one intentionally-public route). **Full suite: 99/99 passing** as of this session.

### Mobile app (`E:\stillopen\mobile`)
Expo + TypeScript + **Expo Router** (file-based routing under `app/`, per the project's own `mobile/AGENTS.md` --
not raw React Navigation; read that file before adding navigation). Screens (`src/screens/`):
- `LoginScreen` -- sign in, token stored in `expo-secure-store`
- `DashboardScreen` -- stats, "Worth a look next", job list with match scores
- `JobDetailScreen` -- status change, fit check, next action, notes
- `CvListScreen` / `CvDetailScreen` -- master + tailored CVs, the fact-check lock/approve flow, real DOCX/Markdown
  downloads (authenticated fetch + `expo-file-system/legacy` + native share sheet, not a browser hop -- see the
  comment in `CvDetailScreen.tsx` about why `expo-file-system` changed its API in SDK 58)
- `ProfileScreen` -- read-only + sign out

`mobile/README.md` has the run instructions and the full feature-parity backlog (cover letters, documents,
interviews/offers/pipeline, prep plans, saved searches, notifications list, profile editing, insights, Google
connection, push notifications -- all already have working `/api/v1/` endpoints, this is a UI backlog only).

**Verified**: clean `npx tsc --noEmit`, clean `npx expo-doctor` (20/20). **Not verified**: actually running on a
device or emulator -- see below.

## What's NOT done / in progress

Device testing. The user chose Expo Go on a physical phone first; that phone wasn't actually available
("phone is not connected use avd"), so we pivoted to the Android emulator (AVD `AiPulse_Test`, already present on
this machine). That's blocked on installing Google's **Android Emulator Hypervisor Driver** (a different thing
from Windows' "Windows Hypervisor Platform" feature -- see quirk #3 below). Last instruction to the user: install
it via **Android Studio's own GUI** (Settings > Languages & Frameworks > Android SDK > SDK Tools tab > check
"Android Emulator Hypervisor Driver (installer)" > Apply), specifically to avoid an SDK-path mismatch discovered
in this session (quirk #2). Waiting on confirmation that's done.

Next steps once the emulator can boot:
1. Boot it: `emulator.exe -avd AiPulse_Test` (find `emulator.exe` under `%LOCALAPPDATA%\Android\Sdk\emulator\`).
2. Start the backend and Expo dev server, bound so the emulator can reach them -- **have the user run these
   themselves in their own terminal**, not through an agent's background process (see quirk #1). The Android
   emulator's special host alias is `10.0.2.2`, e.g. `EXPO_PUBLIC_API_BASE=http://10.0.2.2:<port>` in `mobile/.env`
   and a backend bound to `127.0.0.1:<port>` (not `0.0.0.0` or a LAN IP -- quirk #1 again).
3. `npx expo start` in `mobile/`, press `a` to install/launch on the running emulator (or `npx expo run:android`
   for a full native build if Expo Go's bundled modules turn out not to cover something we added).
4. Log in as the seeded demo user `jane` / `e2e-pass-12345` (see `manage.py e2e_seed --demo`, requires
   `STILLOPEN_E2E=1`) and confirm the dashboard, job detail, and CV approve/download flows all work for real.

## Environment quirks found this session (read before you lose an hour to these)

1. **Binding a dev server to this machine's real LAN IP silently fails from an agent's background process.**
   Every attempt (PowerShell `Start-Process`, Bash `nohup`, even foreground) to run
   `manage.py runserver 192.168.0.100:<port>` left the process alive but with **no actual TCP listener** -- no
   error, no traceback, just nothing. Binding to `127.0.0.1` or asking for `0.0.0.0` (the latter got blocked
   outright by this session's own permission classifier as "dangerous") behaved differently/inconsistently. Never
   got a root cause. A Windows Firewall consent popup was suspected and ruled out (user confirmed no popup).
   **Workaround**: don't try to make a background-started dev server reachable from another device (a phone on
   the LAN) via an agent's own process management -- have the human run that specific command themselves in their
   own terminal. Loopback (127.0.0.1-to-127.0.0.1) binding and curl worked fine every time.
2. **A freshly-created folder under the Android SDK path wasn't visible to the user's own elevated PowerShell**,
   even though `$env:USERPROFILE` matched exactly (`C:\Users\user` both sides), and even though *most* filesystem
   and process state in this session clearly is shared with the real machine (a sibling Claude session saw and
   correctly reported on this session's orphaned processes; most paths checked out fine). Only diagnosed as far
   as "an SDK path mismatch" (`ANDOID_HOME`/`ANDROID_SDK_ROOT` were never set, so the path used was a guess:
   `%LOCALAPPDATA%\Android\Sdk`) before moving to a workaround. **Workaround**: use Android Studio's own GUI for
   anything that writes into the Android SDK tree, rather than `sdkmanager` run from an agent's shell.
3. **The Android emulator needs Google's "Android Emulator Hypervisor Driver" (AEHD), not just Windows'
   "Windows Hypervisor Platform" feature.** `Get-ComputerInfo -Property HyperVisorPresent` stayed `False` even
   after the user enabled `HypervisorPlatform` via DISM and rebooted -- these are two different things. The
   emulator's own error message (`CPU acceleration status: Android Emulator hypervisor driver is not installed on
   this machine`) says exactly which one it wants; don't assume the generic Windows feature is sufficient.
4. **Many duplicate/orphaned dev-server processes accumulate fast in this kind of long session**, including a
   strange pattern of each one appearing twice -- once via the project's venv `python.exe`, once via the system
   `python.exe` with an identical command line -- never fully explained. **Also**: this machine runs several
   *unrelated* Expo/React Native projects in parallel across other sessions (`blood_lagbe`, `AiPulseMobile`,
   `abl-collections` were all seen running at once), which caused real port collisions more than once (this is
   also why the site was briefly showing a different project, "BloodBond", earlier in this same session -- a
   leftover server on port 8000 from before this session started). **Always check
   `Get-NetTCPConnection -LocalPort <port>` before trusting that a port is free**, and clean up background
   `manage.py runserver`/`expo start` processes you started once you're done with them
   (`Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*stillopen*' }`
   is how this session found and stopped its own 28 of them).

## Demo data

`manage.py e2e_seed --demo` (needs `STILLOPEN_E2E=1` set) creates 8 throwaway users (alice, bob, carol, dave,
erin, frank, grace, heidi) plus a demo person `jane` with 9 jobs across the pipeline stages -- password for all of
them is `e2e-pass-12345`. This is what both the web walkthrough and the mobile app were tested against this
session.
