import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

const CV = `Priya Rahman
Dhaka, Bangladesh | priya.import@example.com | +880 1712 345678

SUMMARY
Backend engineer who builds reliable services and likes clear code that other people can read and change.

EXPERIENCE
Senior Software Engineer, Acme Corp
Jan 2021 - Present
- Built the billing service for 2 million requests a day
- Led a team of three

EDUCATION
BSc in Computer Science, University of Dhaka, 2014 - 2018

SKILLS
Languages: Python, Go

AWARDS
Best employee
`;

test("an existing CV is read into review cards, fills the builder, and previews in a locked frame", async ({ page }) => {
  await signIn(page, "frank", "/app/cv/new");
  await page.evaluate(() => window.sessionStorage.clear());
  await page.reload();

  // a wrong file is refused in plain words
  await page.locator('input[type=file]').setInputFiles({ name: "cv.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await page.getByRole("button", { name: "Read my CV" }).click();
  await expect(page.getByText(/Upload a PDF, a Word document/)).toBeVisible();

  await page.locator('input[type=file]').setInputFiles({ name: "cv.md", mimeType: "text/markdown", buffer: Buffer.from(CV) });
  await page.getByRole("button", { name: "Read my CV" }).click();
  const experience = page.getByRole("listitem", { name: "Work experience" });
  await expect(experience.getByText(/Senior Software Engineer at Acme Corp/)).toBeVisible();
  await expect(page.getByRole("listitem", { name: "Certificates" }).getByText("We did not find this in your file")).toBeVisible();
  await expect(page.getByText(/awards or interests/)).toBeVisible();

  // nothing can be filled until every found section is decided
  await expect(page.getByRole("button", { name: "Fill the questions" })).toBeDisabled();
  await page.getByRole("button", { name: "Accept all" }).click();
  await experience.getByRole("button", { name: "Skip" }).click();
  await experience.getByRole("button", { name: "Edit" }).click();
  await page.getByRole("button", { name: "Fill the questions" }).click();

  // "Edit" opened the questions at Work, filled
  await expect(page.getByText("Step 3 of 8: Work")).toBeVisible();
  await expect(page.getByLabel("Job title").first()).toHaveValue("Senior Software Engineer");
  await expect(page.getByLabel("Company").first()).toHaveValue("Acme Corp");
  expect(await page.evaluate(async () => (await (await fetch("/api/v1/cv")).json()).masters.length)).toBeGreaterThanOrEqual(0);

  // the preview: the exact print page, in a frame with no permissions, and it follows the look
  const preview = page.getByRole("button", { name: "Preview" });
  await preview.click();
  const dialog = page.getByRole("dialog", { name: "CV preview" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("iframe")).toHaveAttribute("sandbox", "");
  const frame = page.frameLocator("iframe[name=cv-preview-frame]");
  await expect(frame.getByRole("heading", { name: "Priya Rahman" })).toBeVisible();
  await expect(frame.locator("body")).toContainText("Acme Corp");
  await dialog.getByLabel("Look").selectOption("forest");
  await expect.poll(async () => frame.locator("body").evaluate((el) => getComputedStyle(el).fontFamily)).toContain("Verdana");
  // keyboard: Escape closes, and the focus goes back to the button that opened it
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(preview).toBeFocused();

  // finishing the builder is what saves; the imported answers build as usual
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Your name")).toHaveValue("Priya Rahman");
});
