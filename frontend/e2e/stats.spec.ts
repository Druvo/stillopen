import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("alice's Insights shows every section of Your numbers with her seeded numbers", async ({ page }) => {
  await signIn(page, "alice", "/app/insights");
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
  // the funnel that was there before is still there
  await expect(page.getByRole("heading", { name: "How your search is going" })).toBeVisible();

  // Prep appears only when the site has prep plans switched on, which the numbers themselves say
  const stats = await page.evaluate(async () => await (await fetch("/api/v1/stats")).json());
  const hasPrep = stats.prep !== null;
  const hasCalibration = Boolean(stats.calibration); // the "Match and replies" section only appears once there is something to compare
  const titles = ["This week", "Last 8 weeks", "Match quality", ...(hasCalibration ? ["Match and replies"] : []), "Waiting for a reply", "Where jobs come from", "Kinds of work and countries", "Skills that keep coming up", ...(hasPrep ? ["Prep"] : []), "Roles on the boards"];
  await expect(page.locator("#your-numbers h3")).toHaveText(titles);

  const week = page.locator("section", { has: page.getByRole("heading", { name: "This week" }) });
  // other specs add a job to alice and put off her follow-up, so these are "at least what was seeded" (3 found today, 1 sent)
  await expect(week.locator("li", { hasText: "New jobs found" })).toHaveText(/^([3-9]|\d{2,})New jobs found$/);
  await expect(week.locator("li", { hasText: "Applications sent" })).toHaveText(/^([1-9]|\d{2,})Applications sent$/);
  await expect(week.locator("li", { hasText: "Follow-ups due" })).toBeVisible();
  await expect(week.locator("li", { hasText: "Interviews coming up" })).toHaveText(/^[1-9]\d*Interviews coming up/);

  // the chart is a figure with a caption and the same numbers in a table for screen readers
  const figure = page.locator("figure", { hasText: "week by week" });
  await expect(figure.locator("figcaption")).toBeVisible();
  await expect(figure.getByRole("table", { name: "Weekly numbers" }).getByRole("row")).toHaveCount(9);

  await expect(page.getByText(/Average fit across your jobs: \d+%/)).toBeVisible();
  await expect(page.getByText(/Nothing is waiting for a reply right now|waiting for a reply/).first()).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Added by you" })).toBeVisible();
  await expect(page.getByText("Remote", { exact: true }).first()).toBeAttached();
  await expect(page.getByText(/Check how well a few jobs fit you and the skills that keep coming up will appear here/)).toBeVisible();
  await expect(page.getByText(/matched Backend Engineer this week, and \d+ last week/)).toBeVisible();
});

test("a person with no jobs sees an empty state that says what to do", async ({ page }) => {
  await signIn(page, "carol", "/app/insights");
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
  await expect(page.getByText(/You are not tracking any jobs yet/)).toBeVisible();
  await expect(page.locator("#your-numbers").getByRole("link", { name: "Go to my dashboard" })).toHaveAttribute("href", "/app/");
  await expect(page.locator("#your-numbers h3")).toHaveCount(0);
});

test("the This week card on the dashboard links to the full numbers", async ({ page }) => {
  await signIn(page, "alice");
  const card = page.getByRole("region", { name: "This week" });
  await expect(card).toBeVisible();
  await expect(card.getByText("New jobs", { exact: true })).toBeVisible();
  await expect(card.getByText("Waiting for a reply", { exact: true })).toBeVisible();
  await card.getByRole("link", { name: "See all your numbers" }).click();
  await expect(page).toHaveURL(/\/app\/insights$/);
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
});

test("the numbers read well at 375 px and in dark mode", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice", "/app/insights");
  await expect(page.getByRole("heading", { name: "Your numbers" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Last 8 weeks" })).toBeVisible();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(() => (document.documentElement.dataset.theme = "dark"));
  expect(await overflow()).toBeLessThanOrEqual(0);
  await expect(page.locator("figure").first()).toBeVisible();
});
