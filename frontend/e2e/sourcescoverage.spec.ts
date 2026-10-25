import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

const AREAS = {
  days: 30,
  has_areas: true,
  empty_areas: 1,
  keys: { jooble: false, adzuna: false },
  areas: [
    {
      id: 1, place: "Pakistan", label: "Pakistan", known: true, postings: 0, boards: 0, level: "none", searches_ready: 0, searches_waiting: 1,
      searches: [{ name: "Jooble Pakistan", connector: "jooble", connector_label: "Jooble", ready: false, reason: "needs_key" }],
      tip: "Nothing lists jobs in Pakistan yet. Jooble covers Pakistan but needs a free key. Ask the site owner to add a free key, add a company's careers page under Job sources, or paste a job link into Add job.",
    },
    { id: 2, place: "Malaysia", label: "Malaysia", known: true, postings: 41, boards: 6, level: "ok", searches: [], searches_ready: 0, searches_waiting: 0, tip: "" },
  ],
};

/** The app is real; only the two answers this spec is about are fixed, so it never depends on what the seeded install has listed. */
async function fixAnswers(page: Page, opts: { staff: boolean; noKeys: boolean }) {
  await page.route("**/api/v1/sources/coverage", (route) => route.fulfill({ json: AREAS }));
  await page.route("**/api/v1/me", async (route) => {
    const real = await route.fetch();
    const me = await real.json();
    await route.fulfill({ json: { ...me, is_staff: opts.staff, no_search_keys: opts.noKeys } });
  });
}

test("the sources page shows, for each place, how many jobs we found and what to do when it is empty", async ({ page }) => {
  await fixAnswers(page, { staff: false, noKeys: false });
  await signIn(page, "alice", "/app/sources");
  await expect(page.getByRole("heading", { name: "Where we find jobs for you" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pakistan", exact: true })).toBeVisible();
  await expect(page.getByText("No jobs listed in the last 30 days.")).toBeVisible();
  await expect(page.getByText("Jooble: switched off until the site owner adds a free key")).toBeVisible();
  await expect(page.getByText(/Nothing lists jobs in Pakistan yet\. Jooble covers/)).toBeVisible();
  await expect(page.getByText(/paste a job link into Add job/)).toBeVisible();
  await expect(page.getByText("41 jobs listed in the last 30 days, from 6 job sources.")).toBeVisible();
  await expect(page.getByText("Well covered")).toBeVisible();
});

test("the sources card fits a phone without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await fixAnswers(page, { staff: false, noKeys: false });
  await signIn(page, "alice", "/app/sources");
  await expect(page.getByRole("heading", { name: "Where we find jobs for you" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the dashboard's Your search card adds one line for an empty place", async ({ page }) => {
  await fixAnswers(page, { staff: false, noKeys: false });
  // the card only asks about coverage for a person who has search areas, and alice's seed has none
  await page.route("**/api/v1/dashboard", async (route) => {
    const real = await route.fetch();
    await route.fulfill({ json: { ...(await real.json()), has_areas: true } });
  });
  await signIn(page, "alice");
  await expect(page.getByText("Nothing lists jobs in Pakistan yet.").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "See why and what to do" }).first()).toHaveAttribute("href", /\/app\/sources/);
});

test("the staff banner asks for a key until one exists", async ({ page }) => {
  await fixAnswers(page, { staff: true, noKeys: true });
  await signIn(page, "alice");
  await expect(page.getByText("Add a free Jooble or Adzuna key to find jobs in more countries")).toBeVisible();
  await expect(page.getByRole("link", { name: /Job search keys/ })).toHaveAttribute("href", "/admin/tracker/siteconfig/");
  await page.unroute("**/api/v1/me");
  await fixAnswers(page, { staff: true, noKeys: false });
  await page.reload();
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByText("Add a free Jooble or Adzuna key")).toHaveCount(0);
});

test("a person who is not staff never sees the key banner", async ({ page }) => {
  await fixAnswers(page, { staff: false, noKeys: true });
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByText("Add a free Jooble or Adzuna key")).toHaveCount(0);
});
