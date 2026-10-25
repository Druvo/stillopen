import type { Page } from "@playwright/test";

export const PASSWORD = "e2e-pass-12345"; // the throwaway e2e people made by `manage.py e2e_seed`

/** What a person starts with (the server's defaults). */
export const DEFAULT_PREFS = {
  view: "list",
  tab: "all",
  sort: "best",
  filters_open: false,
  ai_prompt_dismissed: false,
  filters: { fit: "", match: "", work: "", country: "", posting: "", found: "" },
  sidebar: "expanded",
  theme: "light",
  text_size: "normal",
  density: "comfortable",
};

export async function apiPut(page: Page, path: string, body: unknown): Promise<number> {
  return page.evaluate(
    async ([p, b]) => {
      const token = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
      const r = await fetch(`/api/v1${p as string}`, { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify(b) });
      return r.status;
    },
    [path, body] as const,
  );
}

/**
 * Signs in and starts from the default preferences. Choices are saved on the person's account, so a test that changed the view or the
 * filters would otherwise leave them for the next test that signs in as the same person.
 */
export async function signIn(page: Page, name: string, next = "/app/") {
  await page.goto(`/accounts/login/?next=${encodeURIComponent(next)}`);
  await page.locator("input[name=login]").fill(name);
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
  await apiPut(page, "/preferences", DEFAULT_PREFS);
  await page.evaluate(() => sessionStorage.clear()); // the page already cached the old choices
  await page.goto(next);
}

/** Waits for the next save of preferences to be answered, around the action that causes it. */
export async function savedPreferences(page: Page, action: () => Promise<unknown>) {
  const [response] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/api/v1/preferences") && r.request().method() === "PUT"), action()]);
  return response;
}
