import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// Everything here runs as bob and makes its own jobs, all with a company that starts with "JM ", and removes them again afterwards, so the
// other specs (which count alice's and bob's seeded jobs) are not disturbed.
const WHO = "bob";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- the replies are read loosely, as the test needs
type Reply = { status: number; json: any };

async function call(page: Page, method: string, path: string, body?: unknown): Promise<Reply> {
  return page.evaluate(
    async ([m, p, b]) => {
      const token = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
      const r = await fetch(`/api/v1${p as string}`, {
        method: m as string,
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return { status: r.status, json: await r.json().catch(() => ({})) };
    },
    [method, path, body] as const,
  );
}

async function addJob(page: Page, company: string, role = "Tester", extra: Record<string, unknown> = {}): Promise<number> {
  const r = await call(page, "POST", "/jobs", { company, role, allow_duplicate: true, ...extra });
  expect(r.status).toBe(200);
  return r.json.id as number;
}

const jobsOf = async (page: Page) => (await call(page, "GET", "/dashboard")).json.jobs as { id: number; company: string; role: string; status_id: number }[];

// (the source-health test signs in as alice itself)
const asAlice = (title: string) => title.startsWith("source health");

test.beforeEach(async ({ page }, testInfo) => {
  if (!asAlice(testInfo.title)) await signIn(page, WHO);
});

test.afterEach(async ({ page }, testInfo) => {
  if (asAlice(testInfo.title)) return;
  for (const job of await jobsOf(page)) if (job.company.startsWith("JM ")) await call(page, "DELETE", `/jobs/${job.id}`);
  await call(page, "PUT", "/preferences", { hide_weak: false });
});

const card = (page: Page, text: string) => page.locator("article", { hasText: text }).first();

test("removing a job asks first, says exactly what goes with it, and only then removes it", async ({ page }) => {
  const id = await addJob(page, "JM Remove Co");
  await call(page, "POST", "/interviews", { application: id, scheduled_at: "2030-01-15T10:00", kind: "video" });
  await page.goto("/app/?q=JM%20Remove");
  await card(page, "JM Remove Co").getByRole("button", { name: /More actions for/ }).click();
  await page.getByRole("menuitem", { name: "Remove for good…" }).click();

  const dialog = page.getByRole("dialog", { name: /Remove Tester at JM Remove Co for good\?/ });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("This also removes its interview and its history.");
  await expect(dialog).toContainText("This cannot be undone.");
  await expect(dialog.getByRole("button", { name: "Mark as not for me instead" })).toBeVisible();

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(card(page, "JM Remove Co")).toBeVisible(); // still there

  await card(page, "JM Remove Co").getByRole("button", { name: /More actions for/ }).click();
  await page.getByRole("menuitem", { name: "Remove for good…" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove for good" }).click();
  await expect(page.getByText("Removed Tester.", { exact: true })).toBeVisible();
  await expect(page.locator("article", { hasText: "JM Remove Co" })).toHaveCount(0);
  expect((await call(page, "GET", `/jobs/${id}/details`)).status).toBe(404);
});

test("the soft choice comes first: Not for me keeps the job and can be undone", async ({ page }) => {
  await addJob(page, "JM Soft Co");
  await page.goto("/app/?q=JM%20Soft");
  const c = card(page, "JM Soft Co");
  await c.getByRole("button", { name: /More actions for/ }).click();
  await page.getByRole("menuitem", { name: "Not for me" }).click();
  await expect(c.getByRole("combobox").locator("option:checked")).toHaveText("Not for me");
  const bar = page.getByRole("status").filter({ hasText: "Tester is now Not for me." });
  await expect(bar).toBeVisible();
  await bar.getByRole("button", { name: "Undo" }).click();
  await expect(c.getByRole("combobox").locator("option:checked")).toHaveText("Saved");
});

test("several jobs at once: choose, move to Not for me, then undo from the message", async ({ page }) => {
  await addJob(page, "JM Bulk A");
  await addJob(page, "JM Bulk B");
  await addJob(page, "JM Bulk C");
  await page.goto("/app/?q=JM%20Bulk");
  await page.getByRole("button", { name: "Select jobs" }).click();
  const bar = page.getByRole("region", { name: "Actions for the chosen jobs" });
  await expect(bar).toBeVisible();
  await expect(bar.getByRole("button", { name: "Not for me", exact: true })).toBeDisabled(); // nothing chosen yet

  // by keyboard: focus a checkbox and press Space
  const first = page.getByRole("checkbox", { name: "Select Tester at JM Bulk A" });
  await first.focus();
  await page.keyboard.press("Space");
  await expect(first).toBeChecked();
  await expect(bar).toContainText("1 selected");

  await bar.getByRole("checkbox", { name: /Select all in this tab \(3\)/ }).check();
  await expect(bar).toContainText("3 selected");
  await bar.getByRole("checkbox", { name: /Select all in this tab/ }).uncheck();
  await expect(bar).toContainText("Choose the jobs you want to act on.");
  await page.getByRole("checkbox", { name: "Select Tester at JM Bulk A" }).check();
  await page.getByRole("checkbox", { name: "Select Tester at JM Bulk B" }).check();

  await bar.getByRole("button", { name: "Not for me", exact: true }).click();
  const undo = page.getByRole("status").filter({ hasText: "2 jobs are now Not for me." });
  await expect(undo).toBeVisible();
  await expect(card(page, "JM Bulk A").getByRole("combobox").locator("option:checked")).toHaveText("Not for me");
  await expect(card(page, "JM Bulk B").getByRole("combobox").locator("option:checked")).toHaveText("Not for me");
  await expect(card(page, "JM Bulk C").getByRole("combobox").locator("option:checked")).toHaveText("Saved"); // not chosen, not moved
  await expect(bar).toBeHidden(); // the choosing mode ended

  await undo.getByRole("button", { name: "Undo" }).click();
  await expect(card(page, "JM Bulk A").getByRole("combobox").locator("option:checked")).toHaveText("Saved");
  await expect(card(page, "JM Bulk B").getByRole("combobox").locator("option:checked")).toHaveText("Saved");
});

test("choosing several jobs: set a status from the menu, remove after a confirmation, and the board has no choosing mode", async ({ page }) => {
  await addJob(page, "JM Many A");
  await addJob(page, "JM Many B");
  await page.goto("/app/?q=JM%20Many");
  await page.getByRole("button", { name: "Select jobs" }).click();
  const bar = page.getByRole("region", { name: "Actions for the chosen jobs" });
  await bar.getByRole("checkbox", { name: /Select all in this tab/ }).check();

  await bar.getByRole("button", { name: "Set status for the chosen jobs" }).click();
  await page.getByRole("menuitem", { name: "Applied" }).click();
  await expect(card(page, "JM Many A").getByRole("combobox").locator("option:checked")).toHaveText("Applied");

  await page.getByRole("button", { name: "Select jobs" }).click();
  await page.getByRole("region", { name: "Actions for the chosen jobs" }).getByRole("checkbox", { name: /Select all in this tab/ }).check();
  await page.getByRole("button", { name: "Remove…" }).click();
  const dialog = page.getByRole("dialog", { name: "Remove 2 jobs for good?" });
  await expect(dialog).toContainText("This also removes their history.");
  await dialog.getByRole("button", { name: "Remove for good" }).click();
  await expect(page.getByText("Removed 2 jobs.")).toBeVisible();
  await expect(page.locator("article", { hasText: "JM Many" })).toHaveCount(0);

  await addJob(page, "JM Many C");
  await page.goto("/app/?q=JM%20Many");
  await page.getByRole("button", { name: "Board" }).click();
  await expect(page.getByRole("button", { name: "Select jobs" })).toHaveCount(0);
});

test("the edit screen shows the job's history, with a kind word and a day for each line", async ({ page }) => {
  const id = await addJob(page, "JM History Co");
  const applied = (await call(page, "GET", "/dashboard")).json.statuses.find((s: { name: string }) => s.name === "Applied").id;
  await call(page, "PATCH", `/jobs/${id}/status`, { status: applied });
  await page.goto(`/app/jobs/${id}/edit`);
  const history = page.getByRole("region", { name: "History" });
  await expect(history).toBeVisible();
  await expect(history).toContainText("Status set to Applied. Follow up on");
  await expect(history).toContainText("Added");
  const lines = history.getByRole("listitem");
  await expect(lines.first()).toContainText("Applied"); // newest first
});

test("a job with no history yet says what will show up there", async ({ page }) => {
  const id = await addJob(page, "JM Empty Co");
  await page.route("**/api/v1/jobs/*/history", (route) => route.fulfill({ json: { items: [], capped: false } }));
  await page.goto(`/app/jobs/${id}/edit`);
  await expect(page.getByText("Nothing has happened to this job yet.")).toBeVisible();
});

test("a spreadsheet: check it first, see the skipped and unreadable rows, then add; and the export downloads", async ({ page }) => {
  await addJob(page, "JM Sheet Old", "Data Analyst");
  const csv = [
    "Title,Employer,Link,Status,Date applied",
    "Backend Engineer,JM Sheet One,https://jm.example/1,Applied,25/10/2026",
    "Data Analyst,JM Sheet Old,,,",
    "Designer,JM Sheet Two,not a link,,",
    '=HYPERLINK("http://evil"),JM Sheet Three,,,',
  ].join("\n");
  await page.goto("/app/jobs/add");
  await page.setInputFiles('input[type="file"][accept^=".csv"]', { name: "jobs.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.locator('[aria-labelledby="import-title"]').getByRole("button", { name: "Check the file" }).click() // the spreadsheet card (the LinkedIn card has one too);

  await expect(page.getByText("2 jobs will be added, 1 row skipped because you already track it, 1 row could not be read.")).toBeVisible();
  const table = page.getByRole("table", { name: "Jobs that will be added" });
  await expect(table).toContainText("JM Sheet One");
  await expect(table).toContainText("Applied");
  await expect(page.getByText("is not a web address")).toBeVisible();
  expect(await jobsOf(page).then((j) => j.filter((x) => x.company === "JM Sheet One").length)).toBe(0); // nothing added by the check

  await page.getByRole("button", { name: "Add 2 jobs" }).click();
  await expect(page.getByText("Added 2 jobs")).toBeVisible();
  const mine = (await jobsOf(page)).filter((j) => j.company.startsWith("JM Sheet"));
  expect(mine.map((j) => j.company).sort()).toEqual(["JM Sheet Old", "JM Sheet One", "JM Sheet Three"]);

  // the export: a file, with the spreadsheet-formula job made harmless
  await page.goto("/app/jobs/add");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Export my jobs (CSV)" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^stillopen-jobs-\d{4}-\d{2}-\d{2}\.csv$/);
  const path = await download.path();
  const text = (await import("node:fs")).readFileSync(path, "utf-8");
  expect(text.charCodeAt(0)).toBe(0xfeff);
  expect(text).toContain("JM Sheet One");
  expect(text).toContain("'=HYPERLINK");
  expect(text).not.toMatch(/(^|,|\n)=HYPERLINK/);
});

test("a spreadsheet that cannot be used is explained, and nothing is added", async ({ page }) => {
  await page.goto("/app/jobs/add");
  await page.setInputFiles('input[type="file"][accept^=".csv"]', { name: "jobs.csv", mimeType: "text/csv", buffer: Buffer.from("Name,Thing\nA,B\n") });
  await page.locator('[aria-labelledby="import-title"]').getByRole("button", { name: "Check the file" }).click() // the spreadsheet card (the LinkedIn card has one too);
  await expect(page.getByRole("alert").filter({ hasText: "Company" })).toBeVisible();
});

test("adding a job you already track warns you, and lets you open it or add it anyway", async ({ page }) => {
  const id = await addJob(page, "JM Dup Co", "Senior Backend Engineer");
  await page.goto("/app/jobs/add");
  await page.getByLabel("Company", { exact: true }).fill("jm dup co");
  await page.getByLabel("Role", { exact: true }).fill("Backend Engineer");
  await page.getByRole("button", { name: "Save job" }).click();
  await expect(page.getByText("You already track Senior Backend Engineer at JM Dup Co (Saved).")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open it" })).toHaveAttribute("href", `/app/jobs/${id}/edit`);
  expect((await jobsOf(page)).filter((j) => j.company.toLowerCase() === "jm dup co").length).toBe(1);

  await page.getByRole("button", { name: "Add this one anyway" }).click();
  await expect(page).toHaveURL(/\/app\/?(\?.*)?$/);
  await expect.poll(async () => (await jobsOf(page)).filter((j) => j.company.toLowerCase() === "jm dup co").length).toBe(2);
});

test("Hide weak matches is a saved switch; the count says how many it hides, and Show them brings them back", async ({ page }) => {
  await addJob(page, "JM Weak Co");
  await addJob(page, "JM Strong Co");
  await page.route("**/api/v1/dashboard", async (route) => {
    const real = await route.fetch();
    const body = await real.json();
    // two of the test's jobs get a match percent: one weak, one strong (the unchecked ones in the list are never hidden)
    body.jobs = body.jobs.map((j: { company: string }) => (j.company === "JM Weak Co" ? { ...j, percent: 25 } : j.company === "JM Strong Co" ? { ...j, percent: 85 } : j));
    await route.fulfill({ response: real, json: body });
  });
  await page.goto("/app/?q=JM%20");
  await expect(page.locator("article", { hasText: "JM Weak Co" })).toBeVisible();

  await page.getByRole("button", { name: /Filters/ }).click();
  const panel = page.getByRole("region", { name: "Filters" });
  const weak = panel.getByRole("checkbox", { name: "Hide weak matches (under 40%)" });
  await weak.click(); // not .check(): the choice is kept in the query cache, which tells the page a tick later, and .check() reads the box straight away
  await expect(weak).toBeChecked();
  await expect(page.locator("article", { hasText: "JM Weak Co" })).toHaveCount(0);
  await expect(page.locator("article", { hasText: "JM Strong Co" })).toBeVisible();
  await expect(panel).toContainText("1 hidden as weak match");

  await page.reload();
  await expect(page.locator("article", { hasText: "JM Weak Co" })).toHaveCount(0); // it was saved with the person's other choices
  await page.getByRole("button", { name: /Filters/ }).click(); // closes the panel: the line under the toolbar says the same
  await expect(page.getByText("1 weak match is hidden (under 40%).")).toBeVisible();
  await page.getByRole("button", { name: "Show them" }).click();
  await expect(page.locator("article", { hasText: "JM Weak Co" })).toBeVisible();
});

test("an interview for a job that is not at Interview yet offers the move, and one tap makes it", async ({ page }) => {
  const id = await addJob(page, "JM Suggest Co");
  await page.goto(`/app/interviews?job=${id}`);
  await page.getByLabel("When", { exact: true }).fill("2030-01-15T10:00");
  await page.getByRole("button", { name: "Add interview" }).click();
  await expect(page.getByText("Move this job to Interview?")).toBeVisible();
  expect((await jobsOf(page)).find((j) => j.id === id)?.status_id).toBeTruthy();
  const before = (await jobsOf(page)).find((j) => j.id === id)!.status_id;
  await page.getByRole("button", { name: "Move this job to Interview" }).click();
  await expect(page.getByText("Moved to Interview.")).toBeVisible();
  await expect.poll(async () => (await jobsOf(page)).find((j) => j.id === id)!.status_id).not.toBe(before);
});

test("paste a reply: it suggests a status with the sentence it read, and changes nothing until you press the button", async ({ page }) => {
  const id = await addJob(page, "JM Reply Co");
  const before = (await jobsOf(page)).find((j) => j.id === id)!.status_id;
  await page.goto(`/app/jobs/${id}/apply`);
  await page.getByLabel("The email you got").fill("Hi,\nThank you for applying. Unfortunately we will not be moving forward with your application.\nBest wishes");
  await page.getByRole("button", { name: "Read it" }).click();
  await expect(page.locator("blockquote", { hasText: "Unfortunately we will not be moving forward with your application." })).toBeVisible(); // the sentence it read (the pasted email is in the box)
  await expect(page.getByText(/This looks clear\./)).toBeVisible();
  expect((await jobsOf(page)).find((j) => j.id === id)!.status_id).toBe(before); // nothing changed yet

  await page.getByRole("button", { name: "Set status to Rejected" }).click();
  await expect(page.getByText("Status set to Rejected.")).toBeVisible();
  await expect.poll(async () => (await jobsOf(page)).find((j) => j.id === id)!.status_id).not.toBe(before);
  const history = (await call(page, "GET", `/jobs/${id}/history`)).json.items.map((i: { text: string }) => i.text);
  expect(history.some((t: string) => t.startsWith("Reply pasted: Unfortunately we will not be moving forward"))).toBe(true);
});

test("a reply that says nothing clear is told so plainly", async ({ page }) => {
  const id = await addJob(page, "JM Unclear Co");
  await page.goto(`/app/jobs/${id}/apply`);
  await page.getByLabel("The email you got").fill("See you at the meetup on Friday!");
  await page.getByRole("button", { name: "Read it" }).click();
  await expect(page.getByText("We could not tell from this message where things stand.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Set status to/ })).toHaveCount(0);
});

test("source health: the dashboard says how many had trouble, and the sources screen says which and why", async ({ page }) => {
  await signIn(page, "alice"); // alice's seeded search had one source that did not answer
  await expect(page.getByText("1 of 2 sources had trouble in the last search.")).toBeVisible();
  await page.getByRole("link", { name: "See which" }).click();
  await expect(page).toHaveURL(/\/app\/sources/);
  await expect(page.getByText("1 of 2 sources had trouble in the last search.")).toBeVisible();

  await page.route("**/api/v1/sources", async (route) => {
    const real = await route.fetch();
    const body = await real.json();
    const now = new Date().toISOString();
    const board = { connector: "greenhouse", connector_label: "Greenhouse", enabled: true };
    body.mine = [
      { id: 901, name: "Worked Co", board_token: "worked", ...board, health: { state: "ok", checked_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(), last_ok_at: now, error: "", since: null } },
      { id: 902, name: "Broken Co", board_token: "broken", ...board, health: { state: "error", checked_at: now, last_ok_at: null, error: "HTTP 500", since: "2026-10-21T08:00:00Z" } },
    ];
    await route.fulfill({ response: real, json: body });
  });
  await page.reload();
  await expect(page.getByText("Worked 2 hours ago.")).toBeVisible();
  await expect(page.getByText("Not answering since 21 Oct: HTTP 500")).toBeVisible();
});

test("the dashboard's More menu has the CSV export", async ({ page }) => {
  await page.goto("/app/");
  await page.getByRole("button", { name: "More actions for your jobs" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: "Export my jobs (CSV)" }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
});
