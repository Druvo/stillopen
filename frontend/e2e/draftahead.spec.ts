import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-pass-12345"; // the throwaway e2e people made by `manage.py e2e_seed`

async function signIn(page: Page, name: string, next = "/app/") {
  await page.goto(`/accounts/login/?next=${encodeURIComponent(next)}`);
  await page.locator("input[name=login]").fill(name);
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
}

test("a draft the scheduled search prepared waits on the dashboard, opens on the CV screen, and is never approved for me", async ({ page }) => {
  await signIn(page, "grace");
  await expect(page.getByText("Drafts waiting for you")).toBeVisible();
  await expect(page.getByText("Hooli — Backend Engineer").first()).toBeVisible();
  await expect(page.getByText("(flagged claims: 1)")).toBeVisible();

  await page.getByRole("link", { name: "Open draft" }).click();
  await expect(page).toHaveURL(/\/app\/cv\/\d+/);
  await expect(page.getByRole("button", { name: /Everything listed is true: approve/ })).toBeVisible(); // still waiting for me to approve
  await expect(page.getByText("Downloads unlock after you review the flagged items.")).toBeVisible();
});

test("discarding a draft removes it and leaves my own CV history alone", async ({ page }) => {
  await signIn(page, "grace");
  await expect(page.getByText("Drafts waiting for you")).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("Drafts waiting for you")).toHaveCount(0);

  await page.goto("/app/cv");
  await expect(page.getByText("Initial CV").first()).toBeVisible(); // the master history is still there
  await expect(page.getByText("Hooli - Backend Engineer")).toHaveCount(0);
});

test("other people see no drafts card", async ({ page }) => {
  await signIn(page, "alice");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByText("Drafts waiting for you")).toHaveCount(0);
});

test("the Job alerts section on the profile has the draft-ahead switch, off until turned on", async ({ page }) => {
  await signIn(page, "alice", "/app/profile");
  const box = page.getByLabel("Also prepare tailored CV drafts for my best new matches");
  await expect(box).not.toBeChecked();
  await box.check();
  await page.getByRole("button", { name: /^Save/ }).first().click();
  await page.reload();
  await expect(page.getByLabel("Also prepare tailored CV drafts for my best new matches")).toBeChecked();
});
