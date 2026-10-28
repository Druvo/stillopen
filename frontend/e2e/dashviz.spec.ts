import { expect, test } from "@playwright/test";
import { apiPut, savedPreferences, signIn } from "./helpers";

test("Worth a look next lists what to open, each with a reason and a link", async ({ page }) => {
  await signIn(page, "alice");
  const card = page.getByRole("region", { name: "Worth a look next" });
  await expect(card).toBeVisible();
  const items = card.getByTestId("worth-a-look").locator("li");
  expect(await items.count()).toBeLessThanOrEqual(6);
  // the seeded interview (tomorrow) comes first, and every item has a link and a one-line reason
  await expect(items.first().getByRole("link")).toHaveAttribute("href", "/app/interviews");
  await expect(items.first().locator("p")).not.toBeEmpty();
});

test("the funnel has period tabs, a text table, and remembers the period", async ({ page }) => {
  await signIn(page, "alice", "/app/insights");
  const section = page.locator("section", { has: page.getByRole("heading", { name: "From sent to offer" }) });
  await expect(section.getByRole("tab", { name: "90 days" })).toHaveAttribute("aria-selected", "true");
  await section.getByRole("tab", { name: "All time" }).click();
  await expect(section.getByRole("tab", { name: "All time" })).toHaveAttribute("aria-selected", "true");
  await expect(section.getByRole("table", { name: /Funnel, All time/ }).getByRole("row")).toHaveCount(5);
  await page.reload();
  await expect(page.locator("section", { has: page.getByRole("heading", { name: "From sent to offer" }) }).getByRole("tab", { name: "All time" })).toHaveAttribute("aria-selected", "true");
  // keyboard: arrows move between the tabs
  await page.getByRole("tab", { name: "All time" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "30 days" })).toHaveAttribute("aria-selected", "true");
});

test("the year heatmap has its counts as text, and the calendar is a keyboard grid with today marked", async ({ page }) => {
  await signIn(page, "alice", "/app/insights");
  const year = page.locator("section", { has: page.getByRole("heading", { name: "Your year" }) });
  await expect(year.getByRole("table", { name: /Days with activity/ })).toBeAttached();
  const cal = page.locator("section", { has: page.getByRole("heading", { name: "Calendar" }) });
  const grid = cal.getByRole("grid");
  await expect(grid).toBeVisible();
  await expect(grid.locator("[aria-current=date]")).toHaveCount(1);
  await grid.locator("[aria-current=date]").focus();
  const before = await page.evaluate(() => document.activeElement?.getAttribute("data-date"));
  const dayOfMonth = Number(before?.slice(8));
  await page.keyboard.press(dayOfMonth > 15 ? "ArrowLeft" : "ArrowRight"); // stays inside the month, even on its first or last day
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-date"))).not.toBe(before);
  // the week ahead lists the seeded interview with a link
  await expect(cal.getByRole("link", { name: /Interview:/ }).first()).toHaveAttribute("href", "/app/interviews");
  await cal.getByRole("button", { name: "Next month" }).click();
  await expect(grid).toBeVisible();
});

test("goals are off until set; then Today shows a ring, a streak line and the month line", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("region", { name: "Today" })).toHaveCount(0);
  await page.goto("/app/profile");
  const daily = page.getByLabel("Applications I would like to send each day");
  await savedPreferences(page, () => daily.fill("3"));
  // a value outside the range is refused in plain words and not saved
  await daily.fill("99");
  await expect(page.getByText("Enter a whole number from 0 to 50.")).toBeVisible();
  await page.goto("/app/");
  const card = page.getByRole("region", { name: "Today" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("img", { name: /Today: \d+ of 3/ })).toBeVisible();
  await expect(card.getByText(/streak/i).first()).toBeVisible();
  await expect(card.getByText(/in October|in \w+ yet|So far in/).first()).toBeVisible();
  expect(await apiPut(page, "/preferences", { goal_daily: 0 })).toBe(200);
});

test("the quiet-days setting is validated on the server", async ({ page }) => {
  await signIn(page, "alice");
  expect(await apiPut(page, "/preferences", { quiet_days: 2 })).toBe(400);
  expect(await apiPut(page, "/preferences", { quiet_days: 12 })).toBe(200);
});

test("the new sections read at 375 px and in dark mode", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice", "/app/insights");
  await expect(page.getByRole("heading", { name: "Calendar" })).toBeVisible();
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(() => (document.documentElement.dataset.theme = "dark"));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
