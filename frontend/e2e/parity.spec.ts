import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/** A call to the app's own API from inside the signed-in page (same cookie and CSRF token as the screens use). */
async function api<T = unknown>(page: Page, method: string, path: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([m, p, b]) => {
      const token = decodeURIComponent((document.cookie.split("; ").find((c) => c.startsWith("csrftoken=")) ?? "").slice("csrftoken=".length));
      const r = await fetch(`/api/v1${p}`, { method: m as string, headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [method, path, body] as const,
  ) as Promise<T>;
}

const messages = (page: Page) => page.getByRole("region", { name: "Messages" });

test("adding a job says what to do next, in a message that outlives the screen", async ({ page }) => {
  await signIn(page, "alice", "/app/jobs/add");
  await page.getByLabel("Company").fill("ParityCo");
  await page.getByLabel("Role").fill("Toast Tester");
  await page.getByRole("button", { name: "Save job" }).click();
  await expect(page).toHaveURL(/\/app\/$/);
  await expect(messages(page)).toContainText("Saved ParityCo - Toast Tester. Next, press Check my fit");
});

test("the apply screen: tailoring says how it went, CV choices show their version number, and Open stays in the app", async ({ page }) => {
  await signIn(page, "alice");
  const jobs = await api<{ jobs: { id: number; company: string }[] }>(page, "GET", "/dashboard");
  const acme = jobs.jobs.find((j) => j.company === "Acme")!;
  await page.goto(`/app/jobs/${acme.id}/apply`);
  await page.getByRole("button", { name: "Tailor a CV for this job" }).click();
  await expect(page).toHaveURL(/\/app\/cv\/\d+$/);
  await expect(messages(page)).toContainText(/Your tailored CV is ready|Tailored CV saved, but \d+ claim\(s\) are not in your own material/);

  await page.goto(`/app/jobs/${acme.id}/apply`);
  const choices = page.getByRole("radiogroup", { name: "CV to send" });
  if (await choices.count()) {
    await expect(choices.getByText(/^v\d+$/).first()).toBeVisible();
    await expect(choices.getByRole("link", { name: "Open" }).first()).toHaveAttribute("href", /^\/app\/cv\/\d+$/);
  }
});

test("offers show every amount and the reply-by date, and say what the total counts", async ({ page }) => {
  await signIn(page, "alice");
  const jobs = await api<{ jobs: { id: number; company: string }[] }>(page, "GET", "/dashboard");
  const globex = jobs.jobs.find((j) => j.company === "Globex")!;
  await api(page, "POST", "/offers", { application: globex.id, base: "5000", period: "month", currency: "USD", bonus: "3000", equity: "2000", other_benefits: "1000", signing: "4000", deadline: "2030-01-15" });
  await page.goto("/app/offers");
  await expect(page.getByText("The yearly total counts base pay, bonus, shares and benefits")).toBeVisible();
  await expect(page.getByText(/Declined offers drop out of the comparison/).first()).toBeVisible();
  const section = page.getByRole("region", { name: "Offers in USD" });
  for (const label of ["Base per year", "Bonus", "Shares", "Benefits", "Signing (one-off)", "Reply by"]) {
    await expect(section.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(section.getByText(/15 Jan 2030|Jan 15, 2030/).first()).toBeVisible(); // the browser's own date style
});

test("interviews say nothing is sent to anyone", async ({ page }) => {
  await signIn(page, "alice", "/app/interviews");
  await expect(page.getByText(/Nothing is sent to anyone/)).toBeVisible();
});

test("the profile has no beta switch, keeps its examples in the boxes, and /profile#areas lands on the places card", async ({ page }) => {
  await signIn(page, "alice", "/app/profile#areas");
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();
  await expect(page.getByText("New app (beta)")).toHaveCount(0);
  await expect(page.getByLabel("The roles you want")).toHaveAttribute("placeholder", /Senior Backend Engineer/);
  await expect(page.locator("#areas")).toBeInViewport();
});

test("a board that is already added is plain information, not an error", async ({ page }) => {
  await signIn(page, "alice", "/app/sources");
  await page.route("**/api/v1/sources", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ source: null, openings: 0, message: "", info: "You already added that board." }) });
  });
  await page.getByLabel(/The company's name in that address/).fill("acme");
  await page.locator("form").filter({ hasText: "Which hiring system" }).getByRole("button", { name: "Check and add" }).click();
  await expect(page.getByRole("status").filter({ hasText: "You already added that board." })).toBeVisible();
  // (Next.js keeps an empty, always-present alert for announcing page changes; an error would have words in it)
  await expect(page.getByRole("alert").filter({ hasText: /\S/ })).toHaveCount(0);
});

test("a failed prep plan: Try again makes the new plan first, and a refused request leaves the old plan and its reason on screen", async ({ page }) => {
  await signIn(page, "alice");
  const deletes: string[] = [];
  await page.route("**/api/v1/prep/plans/777", (route) => {
    if (route.request().method() === "DELETE") {
      deletes.push(route.request().url());
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 777, title: "Plan for Acme", status: "failed", status_label: "Failed", job: { id: 1, role: "Backend Engineer", company: "Acme" }, lessons_total: 0, lessons_done: 0,
        summary: "", progress: "", error: "The AI did not answer.", gap_skills: [], hours_per_week: 5, generator: "", percent: 0, question_count: 0, streak: 0, weak_topics: [],
        done_today: false, unchecked_links: 0, weeks: [],
      }),
    });
  });
  await page.route("**/api/v1/jobs/1/prep", (route) => route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: "Your AI is not set up." }) }));
  await page.goto("/app/prep/777");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Your AI is not set up." })).toBeVisible();
  await expect(page.getByText("The AI did not answer.")).toBeVisible(); // the old plan is still there
  expect(deletes).toEqual([]); // and nothing was discarded
});
