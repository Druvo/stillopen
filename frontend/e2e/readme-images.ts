import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { PASSWORD, apiPut, DEFAULT_PREFS } from "./helpers";

// Not a normal spec (the name has no ".spec"): `pnpm readme:images` runs it against the demo data of `manage.py e2e_seed --demo`.
// Writes docs/images/{dashboard,board,cv-fact-check,insights,openings,mobile}.png at 1440x900 (mobile 390x844) and the frames in docs/images/.frames.
// Turning the frames into the README's GIF needs ffmpeg (not required for any test): see docs/images/README.md.
const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "../../docs/images");
mkdirSync(out, { recursive: true });

async function signInAsJane(page: Page, next = "/app/") {
  await page.goto(`/accounts/login/?next=${encodeURIComponent(next)}`);
  await page.locator("input[name=login]").fill("jane");
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
  await apiPut(page, "/preferences", { ...DEFAULT_PREFS, ai_prompt_dismissed: true }); // no "set up an AI" nudge in the pictures
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(next);
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
}

test.describe.configure({ mode: "serial" });

test("pictures for the README", async ({ page }) => {
  await signInAsJane(page);
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "dashboard.png") });

  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator("div.snap-x").first()).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "board.png") });
  await page.getByRole("button", { name: "List", exact: true }).click();

  await page.goto("/app/");
  const cv = page.locator("a[href*='/cv/']").first();
  await cv.click();
  await expect(page).toHaveURL(/\/app\/cv\/\d+/);
  await expect(page.getByRole("button", { name: /Everything listed is true: approve/ })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "cv-fact-check.png") });

  await page.goto("/app/insights");
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "insights.png") });

  await page.goto("/openings/");
  await expect(page.getByText("Senior Backend Engineer").first()).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "openings.png") });
});

test("a phone-sized picture", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await signInAsJane(page);
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: join(out, "mobile.png") });
  await context.close();
});

test("frames for the GIF", async ({ page }) => {
  // Frames, not a video: Playwright's own video recorder needs a separate download. One PNG per step, in docs/images/.frames (ignored by git).
  const dir = join(out, ".frames");
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  let n = 0;
  const frame = async () => {
    await settle(page);
    await page.screenshot({ path: join(dir, `frame-${String(++n).padStart(2, "0")}.png`) });
  };
  await signInAsJane(page);
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await frame();
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator("div.snap-x").first()).toBeVisible();
  await frame();
  await page.getByRole("button", { name: "List", exact: true }).click();
  await page.locator("a[href*='/cv/']").first().click();
  await expect(page.getByRole("button", { name: /Everything listed is true: approve/ })).toBeVisible();
  await frame();
  await page.goto("/app/insights");
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
  await frame();
  await page.goto("/openings/");
  await expect(page.getByText("Senior Backend Engineer").first()).toBeVisible();
  await frame();
  expect(readdirSync(dir).length).toBe(n);
});
