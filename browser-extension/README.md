# StillOpen browser extension: Add this job

A small Manifest V3 extension for Chrome, Edge and other Chromium browsers (and Firefox, with the `browser.*`
API shim most of these calls already fall back to). One click on a job posting opens that link in your own
StillOpen's Add Job page, which reads the posting for you the same way pasting the link there would.

## What it does, and doesn't do

- Stores one thing locally: the address of your own StillOpen install (`chrome.storage.sync`). Nothing else.
- On click, it reads the current tab's URL (only when you invoke the extension -- the `activeTab` permission
  grants that one-time access, nothing standing) and opens `{your server}/app/jobs/add?url=<that link>` in a
  new tab.
- It never reads the page's content, never injects a script into any site, and never talks to StillOpen's
  servers directly -- the new tab does that, using the session you're already signed in with there.
- It is not published to any extension store yet; install it unpacked (below) until it is.

Not a bypass of anything: you still need to be signed in to your own StillOpen tab for the Add Job page to
work, exactly as if you had opened it yourself and pasted the link in.

## Install (unpacked, until this is published)

**Chrome / Edge / other Chromium browsers**

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on "Developer mode" (top right).
3. Click "Load unpacked" and select this `browser-extension/` folder.
4. Click the extension's icon once, choose "Open settings", and enter your StillOpen address (e.g.
   `https://jobs.example.com`, or `http://localhost:8123` for a local install).

**Firefox**

1. Open `about:debugging#/runtime/this-firefox`.
2. Click "Load Temporary Add-on" and select `manifest.json` in this folder.
3. Same settings step as above (Firefox keeps this loaded only for the current session; `web-ext` and signing
   are needed for a permanent install, outside the scope of this unpacked setup).

## Icons

`icons/icon16.png`, `icon48.png` and `icon128.png` are plain solid-colour placeholders (StillOpen's brand
blue, `#2563eb`), generated rather than designed -- swap them for real artwork whenever this is prepared for
an actual store listing.
