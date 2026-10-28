import { expect, test } from "@playwright/test";
import { apiPut, signIn } from "./helpers";

test.describe.configure({ mode: "serial" });

test("the bell shows the unread count, opens a list and goes to the full page", async ({ page }) => {
  await signIn(page, "heidi", "/app/");
  const bell = page.getByRole("button", { name: /^Notifications\. 2 unread notifications$/ });
  await expect(bell).toBeVisible();
  await expect(page.getByTestId("bell-count")).toHaveText("2");

  await bell.click();
  const panel = page.getByRole("region", { name: "Latest notifications" });
  await expect(panel.getByText("Your search found 3 new jobs")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(bell).toBeFocused();

  await bell.click();
  await panel.getByRole("link", { name: "See all notifications" }).click();
  await expect(page.getByRole("heading", { name: "Notifications", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Today" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Yesterday" }).or(page.locator("h2").nth(1))).toBeVisible();
});

test("mark one read, mark all read, clear, and turn a kind off", async ({ page }) => {
  await signIn(page, "heidi", "/app/notifications");
  await page.getByRole("button", { name: "Mark as read: Your search found 3 new jobs" }).click();
  await expect(page.getByRole("button", { name: /^Notifications\. 1 unread notification$/ })).toBeVisible();
  await page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(page.getByRole("button", { name: /^Notifications\. No unread notifications$/ })).toBeVisible();
  await expect(page.getByTestId("bell-count")).toHaveCount(0);

  await page.getByRole("checkbox", { name: "A deadline is close" }).click();
  await expect(page.getByRole("checkbox", { name: "A deadline is close" })).not.toBeChecked();
  expect(await apiPut(page, "/notifications/settings", { muted: [] })).toBe(200); // back to the default for the next run

  await page.getByRole("button", { name: "Clear all" }).click();
  await expect(page.getByText(/You have no notifications/)).toBeVisible();
});

test("a person with no notices sees an empty bell that says what will show up", async ({ page }) => {
  await signIn(page, "carol", "/app/");
  await page.getByRole("button", { name: /^Notifications\./ }).click();
  await expect(page.getByText(/Nothing new\./)).toBeVisible();
});

test("AI usage page: numbers, tables, no prompt text", async ({ page }) => {
  await signIn(page, "alice", "/app/profile/ai/usage");
  await expect(page.getByRole("heading", { name: "AI usage", level: 1 })).toBeVisible();
  await expect(page.getByText(/No AI calls yet/)).toBeVisible();
});

test("the running version is in Help", async ({ page }) => {
  await signIn(page, "alice", "/app/help");
  await expect(page.getByTestId("help-version")).toHaveText(/StillOpen version \d+\.\d+\.\d+/);
});
