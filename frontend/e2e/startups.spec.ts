import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-pass-12345"; // the throwaway e2e people made by `manage.py e2e_seed`

async function signIn(page: Page, name: string, next = "/app/") {
  await page.goto(`/accounts/login/?next=${encodeURIComponent(next)}`);
  await page.locator("input[name=login]").fill(name);
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
}

test("a startup post shows the address it publishes for applying, as a plain link", async ({ page }) => {
  await signIn(page, "alice", "/app/postings");
  const row = page.locator("li", { hasText: "Founding Backend Engineer" });
  await expect(row.getByText("Launchpad Labs")).toBeVisible();
  const link = row.getByRole("link", { name: "jobs@launchpad.example" });
  await expect(link).toHaveAttribute("href", "mailto:jobs@launchpad.example");
  await expect(row.getByText(/we never send anything for you/)).toBeVisible();

  // adding it to the tracker carries the address onto the job card
  await row.getByRole("button", { name: "Add to tracker" }).click();
  await expect(page.getByText("Added Launchpad Labs - Founding Backend Engineer.")).toBeVisible();
  await page.goto("/app/");
  const card = page.locator("article", { hasText: "Launchpad Labs" }).first();
  await expect(card.getByRole("link", { name: /Apply address: jobs@launchpad\.example/ })).toHaveAttribute("href", "mailto:jobs@launchpad.example");
});
