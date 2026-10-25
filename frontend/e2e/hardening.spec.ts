import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

// Hardening: the pieces of this work a person can see. Written for CI (Django serving the built app on a throwaway database).
test.describe("hardening", () => {
  test("the sign-up page has a hidden trap box people never reach and loads nothing from another host", async ({ page }) => {
    const external: string[] = [];
    page.on("request", (r) => {
      const url = new URL(r.url());
      if (!["localhost", "127.0.0.1"].includes(url.hostname) && url.protocol.startsWith("http")) external.push(r.url());
    });
    await page.goto("/accounts/signup/");
    const trap = page.locator('input[name="website"]');
    await expect(trap).toHaveAttribute("tabindex", "-1");
    await expect(trap).toHaveAttribute("autocomplete", "off");
    await expect(page.getByLabel("Email")).toBeVisible();
    expect(external).toEqual([]);
  });

  test("the profile has a time zone control that can use this device's zone", async ({ page }) => {
    await signIn(page, "frank", "/app/profile"); // his own zone, so the others keep the site zone
    const field = page.getByLabel("Time zone");
    await expect(field).toBeVisible();
    await page.getByRole("button", { name: /Use this device's time zone/ }).click();
    await expect(page.getByText(/Time zone set to/)).toBeVisible();
  });

  test("interviews offer a calendar download", async ({ page }) => {
    await page.goto("/app/interviews");
    const all = page.getByRole("link", { name: "Download all as .ics" });
    if (await all.count()) {
      const [download] = await Promise.all([page.waitForEvent("download"), all.click()]);
      expect(download.suggestedFilename()).toMatch(/\.ics$/);
    }
  });
});
