import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-pass-12345"; // the throwaway e2e people made by `manage.py e2e_seed`

async function signIn(page: Page, name: string, next = "/app/") {
  await page.goto(`/accounts/login/?next=${encodeURIComponent(next)}`);
  await page.locator("input[name=login]").fill(name);
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
}

const path = (url: string) => new URL(url).pathname;

test("make a calendar link, read it without signing in, make a new one and the old one stops", async ({ page, request, context }) => {
  await signIn(page, "alice", "/app/interviews");
  await expect(page.getByRole("heading", { name: "Show these dates in your calendar" })).toBeVisible();
  await expect(page.getByText(/Anyone who has this link can read these dates/)).toBeVisible();

  await page.getByRole("button", { name: "Make my calendar link" }).click();
  const field = page.getByLabel("Your private link");
  await expect(field).toHaveValue(/\/calendar\/cal_[A-Za-z0-9_-]+\.ics$/);
  const first = path(await field.inputValue());

  // a calendar app is not signed in: the address alone must work, and show alice's dates only
  const feed = await request.get(first);
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  const text = await feed.text();
  expect(text).toContain("BEGIN:VCALENDAR");
  expect(text).toContain("Video call: Initech - API Developer");
  expect(text).toContain("Follow up: Initech - API Developer");
  expect(text).toContain("Apply by: Globex - Platform Engineer");
  expect(text).not.toContain("SecretCo");

  // it is still there after a reload
  await page.reload();
  await expect(page.getByLabel("Your private link")).toHaveValue(new RegExp(first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  // making a new one asks first, then the old address is a 404
  await page.getByRole("button", { name: "Make a new link" }).click();
  await expect(page.getByText(/The old link stops working straight away/)).toBeVisible();
  await page.getByRole("button", { name: "Yes, make a new link" }).click();
  await expect(page.getByText("New link made. The old one no longer works.")).toBeVisible();
  const second = path(await page.getByLabel("Your private link").inputValue());
  expect(second).not.toBe(first);
  expect((await request.get(first)).status()).toBe(404);
  expect((await request.get(second)).status()).toBe(200);

  // turning it off ends it
  await page.getByRole("button", { name: "Turn off" }).click();
  await expect(page.getByRole("button", { name: "Make my calendar link" })).toBeVisible();
  expect((await request.get(second)).status()).toBe(404);
  void context;
});

test("another person's link never shows alice's dates", async ({ page, request }) => {
  await signIn(page, "bob", "/app/interviews");
  await page.getByRole("button", { name: "Make my calendar link" }).click();
  const url = path(await page.getByLabel("Your private link").inputValue());
  const text = await (await request.get(url)).text();
  expect(text).not.toContain("Initech");
  expect(text).not.toContain("Globex");
  await page.getByRole("button", { name: "Turn off" }).click();
});

test("a guessed address is a plain 404", async ({ request }) => {
  const r = await request.get(`/calendar/cal_${"a".repeat(43)}.ics`);
  expect(r.status()).toBe(404);
});
