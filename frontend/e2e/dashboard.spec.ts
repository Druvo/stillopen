import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

const card = (page: Page, text: string) => page.locator("article", { hasText: text }).first();

test("the header, the next step and the four tiles are there", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByText(/We (last looked at which jobs are still open|have not yet looked)/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Add job", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Check which are still open" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Search for jobs" })).toHaveCount(0); // no job sources in the test install
  await expect(page.getByRole("button", { name: "Import from career-ops" })).toHaveCount(0); // site admins only

  await expect(page.getByRole("heading", { name: "Your next step" })).toBeVisible();

  await expect(page.getByText("Jobs you are tracking")).toBeVisible();
  await expect(page.getByText("Applications sent")).toBeVisible();
  await expect(page.getByText(/^Average fit/)).toBeVisible();
  await expect(page.getByText(/^Closing within \d+ days$/)).toBeVisible();
});

test("the next step opens a screen of the app", async ({ page }) => {
  await signIn(page, "bob"); // bob has roles but no CV yet, so the next step is to finish the profile
  const go = page.getByRole("link", { name: "Tell us about you" });
  await expect(go).toHaveAttribute("href", "/app/profile?welcome=1");
  await go.click();
  await expect(page).toHaveURL(/\/app\/profile\?welcome=1/);
});

test("the last search shows its result and a log of every source", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByText(/Last search: .* ago — looked through 40 openings, 3 new for you/)).toBeVisible();
  await expect(page.getByText("Only the best matches were added.")).toBeVisible();
  await page.getByText(/Scan log -- where it searched/).click();
  await expect(page.getByText("Acme Careers")).toBeVisible();
  await expect(page.getByText("30 found, 6 matched, 3 new, 1 already tracked, 2 outside your areas")).toBeVisible();
  await expect(page.getByText("The board did not answer.")).toBeVisible();
});

test("a running search shows its progress, then the first jobs arrive by themselves", async ({ page }) => {
  let polls = 0;
  const run = { running: true, done: 1, total: 4, error: "", found: 5, added: 0, note: "", started_at: new Date().toISOString(), finished_at: null, phase: "reading", entries_count: 0 };
  await page.route("**/api/v1/scan/status", (route) => {
    polls += 1;
    if (polls === 1) return route.fulfill({ json: run });
    if (polls === 2) return route.fulfill({ json: { ...run, done: 4, phase: "sorting" } });
    return route.fulfill({ json: { ...run, running: false, done: 4, added: 2, phase: "done", found: 9 } });
  });
  await page.route("**/api/v1/dashboard", async (route) => {
    const real = await route.fetch();
    const body = await real.json();
    // After the third poll the search is over, so a refreshed dashboard must say so too.
    const scan = polls >= 3 ? { ...run, running: false, done: 4, added: 2, phase: "done", found: 9 } : run;
    await route.fulfill({ response: real, json: { ...body, can_scan: true, scan } });
  });
  await signIn(page, "alice");
  await expect(page.getByText("Reading job sources… 1/4")).toBeVisible();
  await expect(page.getByText(/Usually about a minute/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Reading 1\/4/ })).toBeDisabled();
  await expect(page.getByText("Sorting out the best matches for you…")).toBeVisible();
  await expect(page.getByText(/looked through 9 openings, 2 new for you/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Search for jobs" })).toBeEnabled();
  await page.unrouteAll({ behavior: "wait" }); // let any request still going through the mocks finish before the test ends
});

test("every job card shows what the classic card showed, with the extra actions under More", async ({ page }) => {
  await signIn(page, "alice");
  const more = (c: ReturnType<typeof card>) => c.getByRole("button", { name: /More actions/ });

  const acme = card(page, "Backend Engineer");
  await expect(acme.getByText("USD 90k")).toBeVisible();
  await expect(acme.getByRole("button", { name: "Check my fit" })).toHaveAttribute("title", /How we judge: /);
  await more(acme).click();
  await expect(page.getByRole("menuitem", { name: "Tailor my CV" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Get ready to apply" })).toHaveAttribute("href", /\/app\/jobs\/\d+\/apply$/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);

  const globex = card(page, "Platform Engineer");
  await expect(globex.getByText(/Deadline .* \(in 3 days\)/)).toBeVisible();
  await expect(globex.getByText("Open", { exact: true })).toHaveAttribute("title", "The page still loads.");
  await more(globex).click();
  await expect(page.getByRole("menuitem", { name: "View the posting" })).toHaveAttribute("href", "https://jobs.example.com/platform");
  await page.keyboard.press("Escape");

  const initech = card(page, "API Developer");
  await expect(initech.getByText(/via Email/)).toBeHidden(); // the applied line is inside Details, closed at first
  await initech.getByText("Details", { exact: true }).click();
  await expect(initech.getByText(/via Email/)).toBeVisible();
  await expect(initech.getByRole("button", { name: "Check my fit" })).toHaveCount(0); // nothing to read yet: no description and no link
  await more(initech).click();
  await expect(page.getByRole("menuitem", { name: "Tailor my CV" })).toHaveCount(0);
  await expect(page.getByRole("menuitem", { name: "Edit details" })).toBeVisible();
  await page.keyboard.press("Escape");
});

test("the filters are hidden at first, narrow the list when shown, are remembered on the account, and clear again", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("tab", { name: "All 3" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Work", { exact: true })).toBeHidden();
  await page.getByRole("button", { name: "Filters" }).click();
  await expect(page.getByText("Showing all 3", { exact: true })).toBeVisible();

  await page.getByLabel("Work", { exact: true }).selectOption("remote");
  await expect(page.getByText("Showing 1 of 3", { exact: true })).toBeVisible();
  await expect(page.locator("article")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Filters.*1 on/ })).toBeVisible();
  await page.waitForResponse((r) => r.url().endsWith("/api/v1/preferences") && r.request().method() === "PUT");
  await page.reload();
  await expect(page.getByText("Showing 1 of 3", { exact: true })).toBeVisible(); // remembered: the panel is still open and the filter still set

  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("Showing all 3", { exact: true })).toBeVisible();

  await page.getByLabel("Search", { exact: true }).fill("nobody at all");
  await expect(page.getByText("No jobs match these filters.")).toBeVisible();
  await page.getByRole("button", { name: "Show everything again" }).click();
  await expect(page.getByText("Showing all 3", { exact: true })).toBeVisible();

  await page.getByLabel("Sort by").selectOption("oldest");
  await page.getByLabel("Posting").selectOption("expired");
  await expect(page.getByText("Showing 0 of 3", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
});

test("the search box in the header filters the dashboard too", async ({ page }) => {
  await signIn(page, "alice");
  const box = page.getByRole("searchbox", { name: "Search your jobs" });
  await box.fill("Acme");
  await box.press("Enter");
  await expect(page).toHaveURL(/\/app\/\?q=Acme/);
  await expect(page.locator("article")).toHaveCount(1);
  await expect(page.getByRole("status").filter({ hasText: "Showing 1 of 3" })).toHaveCount(1); // read out for screen readers
  await expect(page.getByLabel("Search", { exact: true })).toHaveValue("Acme");

  // arriving from another screen with ?q= in the address works the same way
  await page.goto("/app/?q=Globex");
  await expect(page.locator("article")).toHaveCount(1);
  await page.getByLabel("Search", { exact: true }).fill("");
  await expect(page.locator("article")).toHaveCount(3);
});

test("a site admin sees the banners, the import button, Paperless and a job's files", async ({ page }) => {
  await page.route("**/api/v1/me", async (route) => {
    const real = await route.fetch();
    await route.fulfill({ response: real, json: { ...(await real.json()), is_staff: true, email_unverified_signups: true, legal_has_blanks: true } });
  });
  await page.route("**/api/v1/dashboard", async (route) => {
    const real = await route.fetch();
    const body = await real.json();
    body.jobs[0].documents = [{ id: 77, kind: "Report", title: "evaluation.md", paperless_id: null, paperless_error: "Paperless said no." }];
    await route.fulfill({ response: real, json: { ...body, can_import: true, paperless_on: true, paperless_url: "https://paper.example.com" } });
  });
  await page.route("**/api/v1/import", (route) => route.fulfill({ json: { ok: true, created: 2, updated: 1, documents: 0, message: "Imported: 2 new, 1 refreshed" } }));
  await signIn(page, "alice");

  await expect(page.getByText(/this server has no email set up/)).toBeVisible();
  await expect(page.getByText(/still have \[bracketed parts\] to fill in/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Site configuration > Legal/ })).toHaveAttribute("href", /\/admin\//);
  await expect(page.getByRole("link", { name: "Paperless", exact: true })).toHaveAttribute("href", "https://paper.example.com");

  await page.getByRole("button", { name: "Import from career-ops" }).click();
  await expect(page.getByText("Imported: 2 new, 1 refreshed")).toBeVisible();

  const withFile = page.locator("article", { has: page.getByText("evaluation.md") }).first();
  await withFile.getByText("Details", { exact: true }).click();
  await expect(withFile.getByRole("link", { name: "evaluation.md" })).toHaveAttribute("href", "/document/77/");
  await expect(withFile.getByRole("button", { name: "Send to Paperless" })).toBeVisible();
  await expect(withFile.getByText("(!)")).toHaveAttribute("title", "Paperless said no.");
});

test("an ordinary person never sees the admin-only controls, even if the page asked for them", async ({ page }) => {
  await signIn(page, "bob");
  await expect(page.getByText(/this server has no email set up/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Paperless", exact: true })).toHaveCount(0);
  const status = await page.evaluate(async () => (await fetch("/api/v1/import", { method: "POST", headers: { "X-CSRFToken": document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "" } })).status);
  expect(status).toBe(403);
});

test("on a phone nothing runs off the side, the filters fold away and the extra buttons sit under More", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);

  await expect(page.getByLabel("Fits your places")).toBeHidden();
  await page.getByRole("button", { name: "Filters" }).click();
  await expect(page.getByLabel("Fits your places")).toBeVisible();
  await expect(page.getByLabel("Sort by")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Filters" }).click();

  await page.getByRole("button", { name: "More actions", exact: true }).click();
  await expect(page.getByRole("menuitem", { name: "Check which are still open" })).toBeVisible();
  await page.keyboard.press("Escape");

  await expect(card(page, "Backend Engineer")).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);

  // the board scrolls sideways inside itself, not the page
  await page.getByRole("button", { name: "Board", exact: true }).click();
  const board = page.locator("div.snap-x").first();
  await expect(board).toBeVisible();
  expect(await board.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  expect(await overflow()).toBeLessThanOrEqual(0);
});

test("saving the first questions says so, and the page promises nothing is sent", async ({ page }) => {
  await signIn(page, "erin", "/welcome/");
  await expect(page).toHaveURL(/\/app\/welcome/);
  await expect(page.getByText("Your answers stay private to you. Nothing is ever sent to an employer, and we never apply for you.")).toBeVisible();
  await page.getByLabel("What kind of work are you looking for?").fill("Data Engineer");
  await page.getByLabel("Where do you live?").fill("Malaysia");
  await page.getByRole("button", { name: "Save and see my jobs" }).click();
  await expect(page).toHaveURL(/\/app\/$/);
  await expect(page.getByText("Lovely, that helps. We are searching for jobs that fit you now; they will appear here in a minute.")).toBeVisible();
});

test("a follow-up that is due can be put off, and then it is gone from the list", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: "Time to follow up" })).toBeVisible();
  await expect(page.getByText(/Initech — API Developer \(due/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coming up" })).toBeVisible();
  await expect(page.getByRole("link", { name: "All interviews" })).toHaveAttribute("href", "/app/interviews");
  await expect(page.getByRole("link", { name: "Open", exact: true }).first()).toHaveAttribute("href", /\/app\/jobs\/\d+\/apply$/);

  await page.getByRole("button", { name: "In 3 days" }).click();
  await expect(page.getByRole("heading", { name: "Time to follow up" })).toHaveCount(0);
});
