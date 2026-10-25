import { expect, test } from "@playwright/test";
import { PASSWORD, signIn } from "./helpers";

test("signed out, the app sends you to sign in and back", async ({ page }) => {
  await page.goto("/app/");
  await expect(page).toHaveURL(/\/accounts\/login\/\?next=\/app\//);
});

test("the board shows only my jobs, and a keyboard move is saved", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByText("Backend Engineer").first()).toBeVisible();
  await expect(page.getByText("SecretCo")).toHaveCount(0);
  await page.getByRole("button", { name: "Board", exact: true }).click(); // the list is the default; the board is the other way to see the same jobs

  const card = page.locator("article", { hasText: "Backend Engineer" }).first();
  const jobId = Number((await card.getAttribute("id"))!.replace("job-", ""));
  const before = await page.evaluate(async (id) => (await (await fetch("/api/v1/dashboard")).json()).jobs.find((j: { id: number }) => j.id === id).bucket_key, jobId);

  await card.getByRole("button", { name: /Drag Backend Engineer/ }).focus();
  // The announcements double as the wait: each key is pressed once the previous one has been announced.
  const announced = (text: RegExp) => expect(page.locator("[id^=DndLiveRegion]")).toContainText(text); // visually hidden, so read, not "visible"
  await page.keyboard.press("Space");
  await expect(page.locator("article.rotate-1")).toBeVisible(); // the lifted copy: the drag has really started
  await announced(/Backend Engineer is over To apply/); // still over its own column
  // The keyboard sensor listens a moment after pickup, and a busy page can make that moment long: press again until it has moved.
  const live = page.locator("[id^=DndLiveRegion]");
  for (let attempt = 0; attempt < 6 && /over To apply/.test((await live.textContent()) ?? ""); attempt++) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(400);
  }
  await announced(/Backend Engineer is over (?!To apply)/);
  await page.keyboard.press("Space");
  await expect(page.getByRole("status").filter({ hasText: /Moved Backend Engineer/ })).toBeVisible();

  await page.reload();
  const after = await page.evaluate(async (id) => (await (await fetch("/api/v1/dashboard")).json()).jobs.find((j: { id: number }) => j.id === id).bucket_key, jobId);
  expect(after).not.toBe(before);
});

test("the status menu moves a job too (the non-drag way), and a failed move rolls back", async ({ page }) => {
  await signIn(page, "alice");
  const card = page.locator("article", { hasText: "Platform Engineer" }).first();
  const select = card.getByRole("combobox");
  const original = await select.inputValue();
  await page.route("**/api/v1/jobs/*/status", (route) => route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: "No." }) }));
  await select.selectOption({ label: "Applied" });
  await expect(page.getByRole("status").filter({ hasText: /Could not move Platform Engineer/ })).toBeVisible();
  await expect(select).toHaveValue(original); // put back
});

test("another person's job is a 404 through the API", async ({ page }) => {
  await signIn(page, "alice");
  const bobsJob = await page.evaluate(async () => {
    // find an id that is not in alice's list: ids are small integers, so probe a few
    const mine = new Set((await (await fetch("/api/v1/dashboard")).json()).jobs.map((j: { id: number }) => j.id));
    for (let id = 1; id < 20; id++) if (!mine.has(id)) return id;
    return 0;
  });
  expect(bobsJob).toBeGreaterThan(0);
  const status = await page.evaluate(async (id) => (await fetch(`/api/v1/jobs/${id}/details`)).status, bobsJob);
  expect(status).toBe(404);
});

test("reloading a deep link lands on the same screen, and the sidebar knows where you are", async ({ page }) => {
  await signIn(page, "alice", "/app/prep");
  await expect(page.getByRole("heading", { name: "Prep plans", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Prep plans", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Prep plans" })).toHaveAttribute("aria-current", "page");
});

test("no page asks another host for anything, and the policy blocks nothing of ours", async ({ page }) => {
  const foreign: string[] = [];
  const violations: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname) && url.protocol.startsWith("http")) foreign.push(request.url());
  });
  page.on("console", (message) => {
    if (/Content Security Policy|Refused to/i.test(message.text())) violations.push(message.text());
  });
  await signIn(page, "alice");
  for (const path of ["/app/", "/app/prep", "/app/profile", "/app/cv", "/app/postings", "/app/interviews", "/app/offers"]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
  }
  expect(foreign).toEqual([]);
  expect(violations).toEqual([]);
  const policy = (await page.request.get("/app/")).headers()["content-security-policy"];
  expect(policy).toContain("default-src 'self'");
  expect(policy.split("; ").find((p) => p.startsWith("script-src"))).not.toContain("unsafe-inline");
});

test("a new person starts at the welcome questions and can skip them", async ({ page }) => {
  await signIn(page, "carol", "/welcome/");
  await expect(page).toHaveURL(/\/app\/welcome/);
  await expect(page.getByRole("heading", { name: "Welcome to StillOpen" })).toBeVisible();
  await page.getByRole("button", { name: "Skip for now" }).click();
  await expect(page).toHaveURL(/\/app\/$/);
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  // Skipped for good: signing in again (no address to go back to) lands on the dashboard, not on the questions.
  await page.context().clearCookies();
  await page.goto("/accounts/login/");
  await page.locator("input[name=login]").fill("carol");
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await expect(page).toHaveURL(/\/app\/$/);
});

test("a company board with a bad name is refused at once, with nothing fetched", async ({ page }) => {
  await signIn(page, "alice", "/app/sources");
  await expect(page.getByRole("heading", { name: "Where we look for jobs" })).toBeVisible();
  await page.getByLabel(/The company's name in that address/).fill("not a valid name!");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/v1/sources") && r.request().method() === "POST"),
    page.locator("form").filter({ hasText: "Which hiring system" }).getByRole("button", { name: "Check and add" }).click(),
  ]);
  expect(response.status()).toBe(400); // refused by the form's own rules, before the server goes anywhere
  await expect(page.getByRole("alert").filter({ hasText: /\S/ }).first()).toBeVisible();
});

test("deleting an account needs the username typed, then it is gone for good", async ({ page, browser }) => {
  await signIn(page, "dave", "/app/profile");
  const remove = page.getByRole("button", { name: "Delete account and data" });
  await expect(remove).toBeDisabled();
  await page.getByLabel(/Delete my account/).fill("not-dave");
  await expect(remove).toBeDisabled();
  await page.getByLabel(/Delete my account/).fill("dave");
  await expect(remove).toBeEnabled();
  page.once("dialog", (dialog) => dialog.accept());
  await remove.click();
  await page.waitForURL((url) => !url.pathname.startsWith("/app/"));

  const again = await browser.newPage();
  await again.goto("/accounts/login/");
  await again.locator("input[name=login]").fill("dave");
  await again.locator("input[name=password]").fill(PASSWORD);
  await again.locator("form button[type=submit]").first().click();
  await expect(again).toHaveURL(/\/accounts\/login\//); // cannot sign in any more
  await again.close();
});
