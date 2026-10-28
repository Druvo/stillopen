import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Makes the pictures in the README (docs/images/*.png and the frames for demo.gif) from the real app on a throwaway database with an
// invented person, "Jane Doe" (`manage.py e2e_seed --demo`). Not part of the normal test run (the default config only reads *.spec.ts);
// run it with `pnpm readme:images` after `pnpm build`. Uses the Chrome that is already installed. E2E_PYTHON picks the interpreter.
const port = Number(process.env.E2E_PORT || 8821);
const python = process.env.E2E_PYTHON || "python";
const db = join(mkdtempSync(join(tmpdir(), "stillopen-readme-")), "readme.sqlite3");

export default defineConfig({
  testDir: "e2e",
  testMatch: "ux-audit.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  timeout: 1_800_000,
  use: { baseURL: `http://127.0.0.1:${port}`, channel: "chrome", colorScheme: "light" },
  webServer: {
    command: `${python} manage.py migrate --noinput && ${python} manage.py e2e_seed --demo && ${python} manage.py runserver 127.0.0.1:${port} --noreload`,
    cwd: "..",
    url: `http://127.0.0.1:${port}/accounts/login/`,
    timeout: 180_000,
    reuseExistingServer: false,
    env: { STILLOPEN_DB: db, STILLOPEN_E2E: "1", DJANGO_SECRET_KEY: "readme-only-not-a-secret", STILLOPEN_SEED_SOURCES: "0", STILLOPEN_LOGIN_RATE: "1000/m/ip" },
  },
});
