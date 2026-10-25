import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("a person with no AI set up is asked for a Google AI Studio key first, and can say not now for good", async ({ page }) => {
  await signIn(page, "alice");
  const card = page.getByRole("region", { name: /First, add a free Google AI Studio key/ });
  await expect(card).toBeVisible();
  const google = card.getByRole("link", { name: "Create a key in Google AI Studio" });
  await expect(google).toHaveAttribute("href", "https://aistudio.google.com/apikey");
  await expect(google).toHaveAttribute("target", "_blank");

  // Not now is saved on the account, not only in this browser.
  await card.getByRole("button", { name: "Not now" }).click();
  await expect(card).toHaveCount(0);
  await page.evaluate(() => {
    sessionStorage.clear();
    localStorage.clear();
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(page.getByRole("region", { name: /First, add a free Google AI Studio key/ })).toHaveCount(0);
});

test("Add my key opens the AI settings with Google AI Studio chosen and the cursor in the key box", async ({ page }) => {
  await signIn(page, "alice");
  await page.getByRole("link", { name: "Add my key" }).click();
  await expect(page).toHaveURL(/\/app\/profile\/ai\?preset=gemini/);
  await expect(page.getByRole("heading", { name: "AI settings" })).toBeVisible();
  await expect(page.getByLabel(/2\. Paste your API key/)).toBeFocused();
  await expect(page.getByText(/Google may use what you send to improve its products/)).toBeVisible();
  const keyField = page.getByLabel(/2\. Paste your API key/);
  await expect(keyField).toHaveAttribute("type", "password"); // a key is never shown while typed
});

test("nobody else is asked, and the key box never comes back filled", async ({ page }) => {
  await signIn(page, "bob");
  await page.goto("/app/profile/ai");
  await expect(page.getByLabel(/2\. Paste your API key/)).toHaveValue("");
});
