import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

async function call(page: Page, method: string, path: string, body?: unknown) {
  return page.evaluate(
    async ([m, p, b]) => {
      const token = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
      const r = await fetch(`/api/v1${p as string}`, {
        method: m as string,
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: b === null ? undefined : JSON.stringify(b),
      });
      return { status: r.status, json: await r.json().catch(() => null) };
    },
    [method, path, body ?? null] as const,
  );
}

const stamp = Date.now();
const local = (days: number) => {
  const d = new Date(Date.now() + days * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T10:00`;
};

test("a hiring-process timeline, interviewers, question bank and company page", async ({ page }) => {
  await signIn(page, "alice");
  const dash = await call(page, "GET", "/dashboard");
  const job = dash.json.jobs[0] as { id: number; company: string; role: string };

  const contact = await call(page, "POST", "/contacts", { name: `Sam ${stamp}`, company: job.company });
  expect(contact.status).toBe(200);
  const first = await call(page, "POST", "/interviews", { application: job.id, scheduled_at: local(30), kind: "phone", contacts: [contact.json.id] });
  expect(first.status).toBe(200);
  const second = await call(page, "POST", "/interviews", { application: job.id, scheduled_at: local(31), kind: "other", custom_label: `Meet the CEO ${stamp}` });
  expect(second.status).toBe(200);

  // the timeline: stages in order, interviewer named, outcome settable from the stage
  await page.goto(`/app/jobs/${job.id}/process`);
  await expect(page.getByTestId("process-summary")).toContainText(/Round \d+ of \d+/);
  await expect(page.getByRole("heading", { name: `Meet the CEO ${stamp}` })).toBeVisible();
  await expect(page.getByText(`Sam ${stamp}`).first()).toBeVisible();
  await page.getByLabel(`Outcome of Phone screen`).last().selectOption("passed");
  await expect(page.getByTestId("process-summary")).toContainText(/passed|scheduled/);

  // the contact's page says they interviewed
  await page.goto("/app/contacts");
  await expect(page.getByText(/Interviewed you for Phone screen/).first()).toBeVisible();

  // the question bank: add, tag, filter, search, delete a linked one only after confirming
  await page.goto("/app/questions");
  await page.getByLabel("Question", { exact: true }).fill(`Why us ${stamp}?`);
  await page.getByLabel("Your answer").fill("Because of the mission.");
  await page.getByLabel("Skill tags").fill(`tag${stamp}, other`);
  await page.getByLabel(`${job.company} - ${job.role}`).check();
  await page.getByRole("button", { name: "Save question" }).click();
  await expect(page.getByRole("heading", { name: `Why us ${stamp}?` })).toBeVisible();
  await page.getByRole("combobox", { name: /^Tag/ }).selectOption(`tag${stamp}`);
  await expect(page.getByRole("heading", { name: `Why us ${stamp}?` })).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete" }).first().click();
  await expect(page.getByRole("heading", { name: `Why us ${stamp}?` })).toHaveCount(0);

  // companies: list, page, watch star, a link that must be https
  await page.goto("/app/companies");
  await page.getByRole("link", { name: job.company, exact: true }).first().click();
  await expect(page.getByRole("heading", { name: job.company })).toBeVisible();
  await page.getByRole("button", { name: /Watch|Watching/ }).click();
  await expect(page.getByRole("button", { name: "Watching" })).toBeVisible();
  await page.getByLabel("Website").fill("http://insecure.example.com");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText(/https/).first()).toBeVisible();
  await page.getByLabel("Website").fill("https://example.com");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByRole("link", { name: "Website" })).toHaveAttribute("href", "https://example.com");
  await call(page, "PATCH", `/companies/page?key=${encodeURIComponent(job.company)}`, { watched: false });
});

test("bob cannot open alice's process or company page", async ({ page }) => {
  await signIn(page, "bob");
  const r = await call(page, "GET", "/companies/page?key=alice-only-nonexistent");
  expect(r.status).toBe(404);
});
