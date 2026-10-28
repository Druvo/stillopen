import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// Runs as alice with one job of its own ("MC Labs"), and removes the job and the fact it adds when done, so the other specs are not disturbed.
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

const DESCRIPTION = "About us\nWe build things.\n\nRequirements:\n- Fluent in Klingon poetry\n- Experience with Docker\n\nBenefits:\n- Free lunch\n";

async function cleanup(page: Page) {
  const dash = await call(page, "GET", "/dashboard");
  for (const j of [...dash.json.jobs, ...(dash.json.archived ?? [])]) if (j.company === "MC Labs") await call(page, "DELETE", `/jobs/${j.id}`);
  const docs = await call(page, "GET", "/documents");
  for (const d of docs.json.sources) if (d.title === "Facts I added from job matches") await call(page, "DELETE", `/documents/${d.id}`);
}

test.describe.configure({ mode: "serial" });

test("a job's How you match card ticks from the person's own notes and lets her add a fact to a gap", async ({ page }) => {
  await signIn(page, "alice");
  await cleanup(page);
  const made = await call(page, "POST", "/jobs", { company: "MC Labs", role: "Poet", description: DESCRIPTION, allow_duplicate: true });
  expect(made.status).toBe(200);
  await page.goto(`/app/jobs/${made.json.id}/edit`);
  const card = page.getByRole("region", { name: "How you match" });
  await expect(card.getByRole("status")).toContainText(/of 2 covered/);
  const gap = card.getByRole("listitem").filter({ hasText: "Fluent in Klingon poetry" });
  await expect(gap).toContainText("Not shown in your material");
  await expect(gap).toContainText("Nothing in your material says this yet");
  await gap.getByRole("button", { name: /Add to my profile/ }).click();
  // nothing is saved without her own words
  await gap.getByRole("button", { name: "Save to my notes" }).click();
  await expect(gap.getByRole("alert")).toContainText("own words");
  await gap.getByRole("textbox").fill("I write Klingon poetry in my spare time.");
  await gap.getByRole("button", { name: "Save to my notes" }).click();
  await expect(gap).toContainText("from a fact you added");
  await expect(gap).toContainText("Covered");
  await cleanup(page);
});

test("the card on the dashboard opens lazily, and archive hides a job until it is restored", async ({ page }) => {
  await signIn(page, "alice");
  await cleanup(page);
  const made = await call(page, "POST", "/jobs", { company: "MC Labs", role: "Poet", description: DESCRIPTION, allow_duplicate: true });
  let asked = false;
  page.on("request", (r) => {
    if (r.url().includes(`/jobs/${made.json.id}/match-card`)) asked = true;
  });
  await page.goto("/app/");
  const article = page.getByRole("article", { name: "Poet at MC Labs" });
  await expect(article).toBeVisible();
  expect(asked).toBe(false); // nothing is computed for a card nobody opened
  await article.getByText("How you match", { exact: true }).click();
  await expect(article.getByRole("region", { name: "How you match" })).toContainText("Fluent in Klingon poetry");

  await article.getByRole("button", { name: /More actions for Poet at MC Labs/ }).click();
  await page.getByRole("menuitem", { name: "Archive" }).click();
  await expect(page.getByRole("article", { name: "Poet at MC Labs" })).toHaveCount(0);
  const archived = page.locator("#archived");
  await expect(archived).toContainText("Archived (1)");
  await archived.getByText(/Archived \(1\)/).click();
  await archived.getByRole("button", { name: "Restore Poet at MC Labs" }).click();
  await expect(page.getByRole("article", { name: "Poet at MC Labs" })).toBeVisible();
  await cleanup(page);
});

test("profile strength is a meter with the most useful missing things as links", async ({ page }) => {
  await signIn(page, "carol", "/app/profile");
  const meter = page.getByRole("meter", { name: "Profile strength" });
  await expect(meter).toBeVisible();
  await expect(meter).toHaveAttribute("aria-valuenow", /^\d+$/);
  await expect(page.getByText("The most useful things to add next:")).toBeVisible();
});

test("the cover letter tone is chosen, used, and remembered", async ({ page }) => {
  await signIn(page, "alice");
  await cleanup(page);
  const made = await call(page, "POST", "/jobs", { company: "MC Labs", role: "Poet", description: DESCRIPTION, allow_duplicate: true });
  await page.goto(`/app/jobs/${made.json.id}/apply`);
  await page.getByLabel("Tone of the cover letter").selectOption("formal");
  await page.getByRole("button", { name: "Write a cover letter" }).click();
  await page.waitForURL(/\/app\/cover\/\d+/);
  await expect(page.getByRole("textbox").first()).toHaveValue(/^Dear Hiring Manager,/);
  await page.goto(`/app/jobs/${made.json.id}/apply`);
  await expect(page.getByLabel("Tone of the cover letter")).toHaveValue("formal");
  await call(page, "PUT", "/preferences", { cover_tone: "warm" });
  await cleanup(page);
});
