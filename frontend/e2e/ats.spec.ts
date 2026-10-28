import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/** The id of the person's current CV, read from the same API the page uses. */
async function currentCvId(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const r = await fetch("/api/v1/cv", { credentials: "same-origin" });
    const data = (await r.json()) as { masters: { id: number }[] };
    return data.masters[0].id;
  });
}

test("a CV shows its ATS check, grouped, with how to fix each point", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  await page.goto(`/app/cv/${await currentCvId(page)}`);
  await expect(page.getByRole("heading", { name: "ATS check" })).toBeVisible();
  await expect(page.getByText(/out of 100/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Needs fixing/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Looks good/ })).toBeVisible();
  // alice's CV has no email address: that check is expandable and says how to fix it
  const check = page.locator("details", { hasText: "No email address found" });
  await check.locator("summary").click();
  await expect(check.getByText(/How to fix it/)).toBeVisible();
  await expect(page.getByText(/not a score from any real applicant tracking system/)).toBeVisible();
});

test("checking against a job shows which of its words the CV has, and a missing key is explained", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  await page.goto(`/app/cv/${await currentCvId(page)}`);
  await page.getByLabel("Check against a job").selectOption({ label: "Acme - Backend Engineer" });
  await expect(page.getByRole("heading", { name: /Words from Acme/ })).toBeVisible();
  await expect(page.getByText(/do not add these unless they are true/)).toBeVisible();
  // alice has no AI key: the note says what to do and links to the settings, and there is no button that could fail
  await expect(page.getByText("Add your free Google AI Studio key in AI settings to use this.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open AI settings" })).toHaveAttribute("href", /\/profile\/ai\?preset=gemini/);
  await expect(page.getByRole("button", { name: "Improve with AI" })).toHaveCount(0);
});

test("the CV list shows a readiness number per version and offers the builder", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  await expect(page.getByText(/ATS check \d+\/100/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Build a CV step by step" })).toBeVisible();
});

test("the builder checks each step, keeps answers when the page reloads, and builds a CV that opens with its ATS check", async ({ page }) => {
  await signIn(page, "frank", "/app/cv/new");
  await expect(page.getByRole("heading", { name: "Build your CV" })).toBeVisible();
  await expect(page.getByText("Step 1 of 8: Contact")).toBeVisible();

  // plain validation first
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Add your name.")).toBeVisible();
  await expect(page.getByText(/Add an email address employers can reach you on/)).toBeVisible();

  await page.getByLabel("Your name").fill("Frank Builder");
  await page.getByLabel("Email", { exact: true }).fill("frank@example.com");
  await page.getByLabel("City and country (optional)").fill("Penang, Malaysia");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Step 2 of 8: Summary")).toBeVisible();
  await page.getByLabel(/One or two sentences about you/).fill("Support engineer who likes fixing things.");

  // the answers are kept in this tab: a reload comes back to the same step with the same words
  await page.reload();
  await expect(page.getByText("Step 2 of 8: Summary")).toBeVisible();
  await expect(page.getByLabel(/One or two sentences about you/)).toHaveValue("Support engineer who likes fixing things.");
  await page.getByRole("button", { name: "Next" }).click();

  // a job that was started needs its title, company and date
  await page.getByLabel("Job title").fill("Support Engineer");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Add the company.")).toBeVisible();
  await expect(page.getByText(/Add when you started/)).toBeVisible();
  await page.getByLabel("Company").fill("Initech");
  await page.getByLabel("Started", { exact: true }).fill("last spring");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Write the date like Jan 2022 or 2022.")).toBeVisible();
  await page.getByLabel("Started", { exact: true }).fill("Jan 2022");
  await page.getByLabel("What you did, point 1").fill("Answered 40 tickets a day.");
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Step 4 of 8: Education")).toBeVisible();
  await page.getByLabel("School or university").fill("State University");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Skills in Tools").fill("Zendesk, SQL, Excel");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click(); // projects are optional
  await page.getByRole("button", { name: "Next" }).click(); // so are publications and references
  await expect(page.getByText("Step 8 of 8: Languages and certificates")).toBeVisible();
  await expect(page.getByText("Add your free Google AI Studio key in AI settings to use this.")).toBeVisible();

  await page.getByRole("button", { name: "Build my CV" }).click();
  await page.waitForURL(/\/app\/cv\/\d+$/);
  await expect(page.getByRole("heading", { name: "ATS check" })).toBeVisible();
  await expect(page.getByText("Frank Builder").first()).toBeVisible();
  // the draft is gone once the CV is built
  await page.goto("/app/cv/new");
  await expect(page.getByText("Step 1 of 8: Contact")).toBeVisible();
  await expect(page.getByLabel("Your name")).toHaveValue("");
});
