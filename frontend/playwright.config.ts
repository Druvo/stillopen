import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Browser tests run against the real thing: Django serving the built export (`pnpm build` first) on a throwaway database.
// They use the Chrome that is already installed (no browser download). E2E_PYTHON picks the interpreter (default: python).
const port = Number(process.env.E2E_PORT || 8777);
const python = process.env.E2E_PYTHON || "python";
const db = join(mkdtempSync(join(tmpdir(), "stillopen-e2e-")), "e2e.sqlite3");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: { baseURL: `http://127.0.0.1:${port}`, channel: "chrome", trace: "retain-on-failure" },
  webServer: {
    command: `${python} manage.py migrate --noinput && ${python} manage.py e2e_seed && ${python} manage.py runserver 127.0.0.1:${port} --noreload`,
    cwd: "..",
    url: `http://127.0.0.1:${port}/accounts/login/`,
    timeout: 180_000,
    reuseExistingServer: false,
    env: { STILLOPEN_DB: db, STILLOPEN_E2E: "1", DJANGO_SECRET_KEY: "e2e-only-not-a-secret", STILLOPEN_SEED_SOURCES: "0", STILLOPEN_LOGIN_RATE: "1000/m/ip" },
  },
});
