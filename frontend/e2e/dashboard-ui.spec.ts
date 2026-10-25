import { expect, test } from "@playwright/test";
import { savedPreferences, signIn } from "./helpers";

const getMe = (page: import("@playwright/test").Page) => page.evaluate(async () => (await (await fetch("/api/v1/me")).json()) as { preferences: Record<string, unknown> });

test("the dashboard opens as a list with stage tabs, not the board", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("tablist", { name: "Show jobs by stage" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "All 3" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "List", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("article")).toHaveCount(3);
  await expect(page.locator("div.snap-x")).toHaveCount(0); // no board columns
  await expect(page.getByRole("button", { name: "Filters" })).toHaveAttribute("aria-expanded", "false");
});

test("a stage tab narrows the list, and the same tab narrows the board to one column", async ({ page }) => {
  await signIn(page, "alice");
  const tab = page.getByRole("tab", { name: /^Applied/ });
  const inStage = Number(await tab.locator("span").textContent()); // other specs move jobs around, so ask the tab how many it holds
  expect(inStage).toBeGreaterThan(0);
  await tab.click();
  await expect(page.locator("article")).toHaveCount(inStage);
  await expect(page.locator("article", { hasText: "API Developer" })).toBeVisible();
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator("section[aria-labelledby^=col-]")).toHaveCount(1);
  await page.getByRole("tab", { name: "All 3" }).click();
  await expect(page.locator("section[aria-labelledby^=col-]").nth(1)).toBeVisible(); // all columns again
});

test("the board is one switch away, and the choice is kept across a reload", async ({ page }) => {
  await signIn(page, "alice");
  await savedPreferences(page, () => page.getByRole("button", { name: "Board", exact: true }).click());
  await expect(page.locator("div.snap-x").first()).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Board", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("div.snap-x").first()).toBeVisible();
  expect((await getMe(page)).preferences.view).toBe("board");
});

test("the filters are hidden, the button shows them with a count of what is on, and Clear filters empties them", async ({ page }) => {
  await signIn(page, "alice");
  const button = page.getByRole("button", { name: "Filters" });
  await expect(page.getByLabel("Work", { exact: true })).toBeHidden();
  await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(button).toHaveAttribute("aria-controls", "job-filters-panel");
  await page.getByLabel("Work", { exact: true }).selectOption("remote");
  await page.getByLabel("Found", { exact: true }).selectOption("week");
  await expect(page.getByRole("button", { name: /Filters.*2 on/ })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Showing 1 of 3" })).toHaveCount(1);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("button", { name: "Filters", exact: true })).toBeVisible(); // no count any more
  await expect(page.getByText("Showing all 3", { exact: true })).toBeVisible();
  await button.click();
  await expect(page.getByLabel("Work", { exact: true })).toBeHidden();
});

test("choices come from the server, not only this browser", async ({ page }) => {
  await signIn(page, "alice");
  const saved = await savedPreferences(page, async () => {
    await page.getByLabel("Sort by").selectOption("company");
    await page.getByRole("button", { name: "Filters" }).click();
    await page.getByLabel("Work", { exact: true }).selectOption("remote");
  });
  expect(saved.status()).toBe(200);
  expect(saved.request().postDataJSON()).toMatchObject({ sort: "company" });
  await page.waitForTimeout(600); // let a second save for the rest of the changes finish
  // forget everything this browser kept: only the account is left
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload();
  await expect(page.getByLabel("Sort by")).toHaveValue("company");
  await expect(page.getByLabel("Work", { exact: true })).toHaveValue("remote");
  const prefs = (await getMe(page)).preferences;
  expect(prefs).toMatchObject({ sort: "company", filters_open: true });
  expect((prefs.filters as Record<string, string>).work).toBe("remote");
});

test("text size and spacing are set in Profile > Display and change the page itself", async ({ page }) => {
  await signIn(page, "alice", "/app/profile");
  // the labels are the big targets (the round inputs move when the text grows)
  const choose = (name: string) => page.locator("label", { hasText: new RegExp(`^${name}$`) }).click();
  const rootSize = () => page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
  expect(await rootSize()).toBe("16px");
  await choose("Large");
  await expect.poll(rootSize).toBe("18px");
  await choose("Larger");
  await expect.poll(rootSize).toBe("20px");
  await choose("Compact");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await choose("Dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.waitForResponse((r) => r.url().endsWith("/api/v1/preferences") && r.request().method() === "PUT");
  await page.waitForTimeout(500);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect.poll(rootSize).toBe("20px"); // from the account
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect((await getMe(page)).preferences).toMatchObject({ text_size: "larger", density: "compact", theme: "dark" });
});

test("the stage tabs work with the keyboard", async ({ page }) => {
  await signIn(page, "alice");
  const tabs = page.getByRole("tab");
  const first = tabs.nth(0);
  await first.focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(1)).toBeFocused();
  await page.keyboard.press("End");
  await expect(tabs.last()).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowRight"); // wraps to All
  await expect(first).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowLeft"); // and back to the last
  await expect(tabs.last()).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(first).toBeFocused();
  await expect(first).toHaveAttribute("tabindex", "0");
  await expect(tabs.nth(1)).toHaveAttribute("tabindex", "-1");
});

test("the Your search card sums up what drives the matches and says where to change it", async ({ page }) => {
  await signIn(page, "alice");
  const card = page.getByRole("region", { name: "Your search" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Backend Engineer")).toBeVisible();
  await expect(card.getByText("Your CV")).toBeVisible();
  await expect(card.getByRole("link", { name: "Your search: change roles" })).toHaveAttribute("href", "/app/profile");
  await expect(card.getByRole("link", { name: "Your search: change how fit is judged" })).toHaveAttribute("href", "/app/profile/ai");
  await expect(card.getByRole("link", { name: /^Your search: (change|add) places$/ })).toHaveAttribute("href", "/app/profile#areas");
  await card.getByRole("link", { name: "Your search: change roles" }).click();
  await expect(page).toHaveURL(/\/app\/profile$/);
});

test("a reload paints from the saved copy at once and refreshes behind it", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.locator("article")).toHaveCount(3);
  await page.waitForTimeout(600); // the copy is written a moment after the answers arrive
  await page.route("**/api/v1/dashboard", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });
  await page.reload();
  await expect(page.locator("article")).toHaveCount(3, { timeout: 1500 }); // no blank "Loading" while the slow answer is on its way
  await expect(page.getByText("Updating…")).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
});

test("signing out removes what this tab kept", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.locator("article")).toHaveCount(3);
  await page.waitForTimeout(600);
  expect(await page.evaluate(() => sessionStorage.getItem("stillopen-query-cache"))).not.toBeNull();
  await page.getByRole("button", { name: "Your account" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/app/"));
  expect(await page.evaluate(() => sessionStorage.getItem("stillopen-query-cache"))).toBeNull();
});

test("at 375 px the layout has no sideways scroll, and the side cards fold", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice");
  await expect(page.locator("article").first()).toBeVisible();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  const search = page.getByRole("button", { name: /^Your search/ });
  await expect(search).toHaveAttribute("aria-expanded", "false");
  await search.click();
  await expect(search).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("link", { name: "Your search: change roles" })).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  // the main controls are big enough to touch
  for (const control of [page.getByRole("button", { name: "Filters" }), page.getByRole("button", { name: "Board", exact: true }), page.getByRole("tab", { name: "All 3" })]) {
    const box = await control.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(43);
  }
});
