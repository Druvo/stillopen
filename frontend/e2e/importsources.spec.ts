import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// Runs as bob. Every job made here has a company starting with "IS " and is removed afterwards, so the other specs are not disturbed.

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- replies are read loosely
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

test.beforeEach(async ({ page }) => {
  await signIn(page, "bob");
});

test.afterEach(async ({ page }) => {
  const jobs = (await call(page, "GET", "/dashboard")).json.jobs as { id: number; company: string }[];
  for (const job of jobs) if (job.company.startsWith("IS ")) await call(page, "DELETE", `/jobs/${job.id}`);
});

// A representative forwarded alert (written for this test, not captured from real mail).
const EMAIL = `Backend Engineer
IS Acme Robotics
Berlin, Germany
https://jobs.example.org/apply/501?utm_source=mail&trk=abc

Data Analyst
IS Initech
Remote
https://jobs.example.org/apply/502?trk=zzz
`;

test("an email is checked first, a job already tracked is flagged, and only ticked jobs are added", async ({ page }) => {
  const made = await call(page, "POST", "/jobs", { company: "IS Initech", role: "Data Analyst", allow_duplicate: true });
  expect(made.status).toBe(200);
  await page.goto("/app/jobs/add");
  const card = page.getByRole("region", { name: "Import from an email" });
  await card.getByLabel(/Paste the email here/).fill(EMAIL);
  await card.getByRole("button", { name: "Check" }).click();

  await expect(card.getByText("2 jobs found, 1 job you already track.")).toBeVisible();
  const rows = card.getByTestId("email-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toContainText("You already track Data Analyst at IS Initech");
  await expect(card.getByRole("checkbox", { name: "Add Backend Engineer" })).toBeChecked();
  await expect(card.getByRole("checkbox", { name: "Add Data Analyst" })).not.toBeChecked();

  await card.getByRole("button", { name: "Add selected (1)" }).click();
  await page.waitForURL(/\/app\/?$/);
  const jobs = (await call(page, "GET", "/dashboard")).json.jobs as { company: string; role: string; url: string }[];
  const added = jobs.find((j) => j.company === "IS Acme Robotics");
  expect(added?.role).toBe("Backend Engineer");
  expect(added?.url).toBe("https://jobs.example.org/apply/501");
  expect(jobs.filter((j) => j.company === "IS Initech")).toHaveLength(1);
});

test("a pasted list with no links is offered without a link and says so", async ({ page }) => {
  await page.goto("/app/jobs/add");
  const card = page.getByRole("region", { name: "Import from an email" });
  await card.getByLabel(/Paste the email here/).fill("IS Product Designer\nIS Fabrikam\nDubai, United Arab Emirates\nPromoted\nEasy Apply\n");
  await card.getByRole("button", { name: "Check" }).click();
  await expect(card.getByText("No link: you will need to open it on LinkedIn to apply.")).toBeVisible();
});

test("the careers form shows the plain message when a page has no list of openings (stubbed answer)", async ({ page }) => {
  await page.route("**/api/v1/sources/careers-page", (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "We could not find a list of openings on that page. Try a page that lists jobs, or paste single job links into Add job." }),
    }),
  );
  await page.goto("/app/sources");
  const card = page.getByRole("region", { name: /Add a company.s careers page/ });
  await card.getByLabel("Address of the careers page").fill("https://careers.example.com/");
  await card.getByRole("button", { name: "Check and add" }).click();
  await expect(card.getByText("We could not find a list of openings on that page.")).toBeVisible();
  await expect(card.getByRole("alert")).toContainText("paste single job links into Add job");
});

test("a LinkedIn link is kept, not read, and the description box is ready for the text (stubbed answer)", async ({ page }) => {
  await page.route("**/api/v1/quickadd", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true, role: "", company: "", description: "", duplicate: null, blocked_host: "linkedin", url: "https://www.linkedin.com/jobs/view/3812345678/",
        message: "LinkedIn does not let other apps read its pages, so we have kept the link and need the text from you: open the job on LinkedIn, select the description, copy and paste it below.",
      }),
    }),
  );
  await page.goto("/app/jobs/add");
  await page.getByLabel("Paste a link to the job").fill("https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc");
  await page.getByRole("button", { name: "Read the link" }).click();
  await expect(page.getByText("LinkedIn does not let other apps read its pages")).toBeVisible();
  await expect(page.getByLabel("Link to the posting")).toHaveValue("https://www.linkedin.com/jobs/view/3812345678/");
  await expect(page.getByLabel("The job description")).toBeFocused();
  await expect(page.getByRole("button", { name: "Fill the form from pasted text" })).toBeVisible();
});
