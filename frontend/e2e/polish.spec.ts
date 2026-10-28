import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/** Keyboard shortcuts, the jump-to palette, the getting-started checklist and the no-sideways-scroll rule on every screen. */

const screens = (job: number | null, cv: number | null) => {
  const list = ["/", "/postings", "/jobs/add", "/knowledge", "/cv", "/cv/new", "/interviews", "/contacts", "/companies", "/questions", "/offers", "/insights", "/prep", "/help", "/profile", "/profile/ai", "/profile/ai/usage", "/notifications", "/profile/assistant", "/sources", "/stats"];
  if (job) list.push(`/jobs/${job}/edit`, `/jobs/${job}/apply`, `/jobs/${job}/process`);
  if (cv) list.push(`/cv/${cv}`, `/cv/${cv}/diff`);
  return list;
};

async function waitForDashboard(page: Page) {
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
}

test("? lists the shortcuts, Esc closes it and gives focus back, and the user menu has an entry for it", async ({ page }) => {
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.keyboard.press("?");
  const dialog = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Search and jump to a screen")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  await page.getByRole("button", { name: "Your account" }).click();
  await page.getByRole("button", { name: "Keyboard shortcuts" }).click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Your account" })).toBeFocused();
});

test("letters do nothing while typing in a field", async ({ page }) => {
  await signIn(page, "alice");
  await waitForDashboard(page);
  const box = page.getByRole("searchbox", { name: "Search your jobs" });
  await box.fill("");
  await box.focus();
  await page.keyboard.type("?/g");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(box).toHaveValue("?/g");
});

test("/ opens the palette and a typed word jumps to a screen", async ({ page }) => {
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.keyboard.press("/");
  const palette = page.getByRole("dialog", { name: "Search and jump" });
  await expect(palette).toBeVisible();
  const input = palette.getByRole("combobox");
  await expect(input).toBeFocused();
  await input.fill("interv");
  await expect(palette.getByRole("option", { name: /Interviews/ })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/interviews$/);
  await expect(palette).toHaveCount(0);
});

test("Ctrl+K opens it even from the search box, the arrows choose, and Esc closes", async ({ page }) => {
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.getByRole("searchbox", { name: "Search your jobs" }).focus();
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Search and jump" });
  await expect(palette).toBeVisible();
  await palette.getByRole("combobox").fill("add");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/jobs\/add$/);
  await page.keyboard.press("Control+k");
  await expect(palette).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
  // a word that matches no screen can still search the jobs
  await page.keyboard.press("Control+k");
  await palette.getByRole("combobox").fill("zzzz");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/\?q=zzzz/);
});

test("g then a letter goes to a screen", async ({ page }) => {
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.keyboard.press("g");
  await page.keyboard.press("c");
  await expect(page).toHaveURL(/\/app\/cv$/);
  await page.keyboard.press("g");
  await page.keyboard.press("d");
  await expect(page).toHaveURL(/\/app\/$/);
});

test("on a phone the header has a button for the palette", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.getByRole("button", { name: "Search and jump to a screen" }).click();
  await expect(page.getByRole("dialog", { name: "Search and jump" })).toBeVisible();
  await page.keyboard.press("Escape");
});

test("a new person sees the getting-started checklist, and closing it is remembered", async ({ page }) => {
  await signIn(page, "carol");
  await waitForDashboard(page);
  const card = page.getByRole("region", { name: /Getting started/ });
  await expect(card).toBeVisible();
  await expect(card.getByRole("link", { name: "Track your first job" })).toBeVisible();
  await card.getByRole("button", { name: "Hide this checklist" }).click();
  await expect(page.getByRole("region", { name: /Getting started/ })).toHaveCount(0);
  await page.reload();
  await waitForDashboard(page);
  await expect(page.getByRole("region", { name: /Getting started/ })).toHaveCount(0);
});

test("the dashboard opens at the top on a phone, not scrolled down to the tabs", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice");
  await waitForDashboard(page);
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("no screen scrolls sideways at 375 px", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice");
  const ids = await page.evaluate(async () => {
    const get = async (p: string) => (await fetch(`/api/v1${p}`, { credentials: "same-origin" })).json();
    const dash = await get("/dashboard");
    const cvs = await get("/cv");
    return { job: dash.jobs?.[0]?.id ?? null, cv: cvs.masters?.[0]?.id ?? null };
  });
  const wide: string[] = [];
  for (const path of screens(ids.job, ids.cv)) {
    await page.goto(`/app${path === "/" ? "/" : path}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(250);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (over > 0) wide.push(`${path} (+${over}px)`);
  }
  expect(wide, wide.join(", ")).toEqual([]);
});

test("keyboard only: Tab reaches named controls with a visible focus ring on the dashboard, the apply screen and a CV", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "alice");
  const ids = await page.evaluate(async () => {
    const get = async (p: string) => (await fetch(`/api/v1${p}`, { credentials: "same-origin" })).json();
    const dash = await get("/dashboard");
    const cvs = await get("/cv");
    return { job: dash.jobs[0].id as number, cv: cvs.masters[0].id as number };
  });
  const problems: string[] = [];
  for (const path of ["/", `/jobs/${ids.job}/apply`, `/cv/${ids.cv}`]) {
    await page.goto(`/app${path === "/" ? "/" : path}`);
    await waitForDashboard(page);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    for (let i = 0; i < 45; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        const dateField = el.tagName === "INPUT" && /date|time|month/.test((el as HTMLInputElement).type); // Chrome reports no :focus on these although the field is active; not judged here
        const ring = dateField || (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none";
        const name = el.getAttribute("aria-label") || el.textContent?.trim() || (el as HTMLInputElement).labels?.[0]?.textContent?.trim() || el.getAttribute("title") || "";
        const r = el.getBoundingClientRect();
        return { tag: el.tagName.toLowerCase(), ring, name: name.slice(0, 30), visible: r.width > 0 && r.height > 0 };
      });
      if (!info) continue;
      if (!info.visible) problems.push(`${path}: focus on a hidden ${info.tag}`);
      else if (!info.name) problems.push(`${path}: ${info.tag} has no name`);
      else if (!info.ring) problems.push(`${path}: no focus ring on ${info.tag} "${info.name}"`);
    }
  }
  expect(problems, problems.join("\n")).toEqual([]);
});
