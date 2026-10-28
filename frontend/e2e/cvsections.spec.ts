import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("the builder adds publications and a references line, and the CV shows them as plain lines", async ({ page }) => {
  await signIn(page, "frank", "/app/cv/new");
  await page.evaluate(() => window.sessionStorage.clear());
  await page.reload();
  await page.getByLabel("Your name").fill("Pia Writer");
  await page.getByLabel("Email", { exact: true }).fill("pia@example.com");
  for (let i = 0; i < 2; i += 1) await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Job title").fill("Editor");
  await page.getByLabel("Company").fill("Paper Co");
  await page.getByLabel("Started", { exact: true }).fill("Jan 2021");
  await page.getByRole("button", { name: "Next" }).click();
  for (let i = 0; i < 3; i += 1) await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Step 7 of 8: Publications and references")).toBeVisible();

  await page.getByLabel("Title", { exact: true }).fill("Why plain CVs win");
  await page.getByLabel("Journal, publisher or event (optional)").fill("Hiring Review");
  await page.getByLabel("Year (optional)").fill("soon");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Write the year with four digits, like 2023.")).toBeVisible();
  await page.getByLabel("Year (optional)").fill("2023");
  await page.getByLabel("How publications are written").selectOption("apa");
  await expect(page.getByText(/Most employers only ask for references later/)).toBeVisible();
  await page.getByLabel("References on your CV").selectOption("on_request");
  await page.getByRole("button", { name: "Next" }).click();

  await page.getByRole("button", { name: "Build my CV" }).click();
  await page.waitForURL(/\/app\/cv\/\d+$/);
  const content = await page.locator("textarea").first().inputValue();
  expect(content).toContain("## Publications");
  expect(content).toContain("(2023). Why plain CVs win. Hiring Review.");
  expect(content).toContain("References available on request.");
});

test("the download look picker offers the extra plain looks", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  const first = await page.evaluate(async () => (await (await fetch("/api/v1/cv")).json()).masters[0]?.id);
  await page.goto(`/app/cv/${first}`);
  await expect(page.locator("#cv-template")).toBeVisible();
  const options = await page.locator("#cv-template option").allTextContents();
  expect(options).toEqual(["Classic", "Modern", "Compact", "Serif", "Forest", "Slate"]);
});

test("the data card previews an export file before adding anything", async ({ page }) => {
  await signIn(page, "alice", "/app/profile");
  const exported = await page.evaluate(async () => (await fetch("/profile/export/")).text());
  await page.locator('input[type=file][accept*=json]').setInputFiles({ name: "export.json", mimeType: "application/json", buffer: Buffer.from(exported) });
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText(/nothing|to add|already have/i).first()).toBeVisible();
  // a file from nobody's export is refused in plain words
  await page.locator('input[type=file][accept*=json]').setInputFiles({ name: "bad.json", mimeType: "application/json", buffer: Buffer.from("{}") });
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText(/not a StillOpen export/)).toBeVisible();
});
