import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiPut, DEFAULT_PREFS, signIn } from "./helpers";

/**
 * Accessibility, kept permanently: axe (WCAG 2.2 A and AA) on every main screen at desktop and phone width in the light and dark theme,
 * plus the things axe cannot see: a title for every screen, focus that follows a screen change, the phone drawer as a real dialog,
 * the user menu, and messages that are read out. A screen that is not in the build yet (the not-found page shows instead) is skipped.
 */

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];
const NOT_FOUND = "We could not find that page";

/** The first id found in a JSON answer (a list of CVs, of prep plans ...), or null. */
async function firstId(page: Page, api: string, key?: string): Promise<number | null> {
  return page.evaluate(
    async ([path, k]) => {
      const response = await fetch(`/api/v1${path}`);
      if (!response.ok) return null;
      const data = await response.json();
      const list = (k ? data[k] : Object.values(data).find((v) => Array.isArray(v))) as { id: number }[] | undefined;
      return list?.[0]?.id ?? null;
    },
    [api, key ?? ""] as const,
  );
}

async function jobIdOf(page: Page): Promise<number | null> {
  return page.evaluate(async () => (await (await fetch("/api/v1/dashboard")).json()).jobs?.[0]?.id ?? null);
}

async function screens(page: Page): Promise<{ name: string; path: string }[]> {
  const job = await jobIdOf(page);
  const cv = await firstId(page, "/cv");
  const plan = await firstId(page, "/prep/plans", "plans");
  const list: { name: string; path: string }[] = [
    { name: "dashboard", path: "/app/" },
    { name: "add-job", path: "/app/jobs/add" },
    { name: "postings", path: "/app/postings" },
    { name: "knowledge", path: "/app/knowledge" },
    { name: "interviews", path: "/app/interviews" },
    { name: "contacts", path: "/app/contacts" },
    { name: "offers", path: "/app/offers" },
    { name: "insights", path: "/app/insights" },
    { name: "cv-list", path: "/app/cv" },
    { name: "cv-new", path: "/app/cv/new" },
    { name: "profile", path: "/app/profile" },
    { name: "ai-settings", path: "/app/profile/ai" },
    { name: "assistant", path: "/app/profile/assistant" },
    { name: "sources", path: "/app/sources" },
    { name: "prep-list", path: "/app/prep" },
    { name: "help", path: "/app/help" },
  ];
  if (job) list.push({ name: "edit-job", path: `/app/jobs/${job}/edit` }, { name: "apply", path: `/app/jobs/${job}/apply` });
  if (cv) list.push({ name: "cv-detail", path: `/app/cv/${cv}` });
  if (plan) list.push({ name: "prep-plan", path: `/app/prep/${plan}` });
  return list;
}

async function settled(page: Page) {
  await page.locator("main h1").first().waitFor({ timeout: 15_000 });
  await page.locator("main [aria-busy=true]").first().waitFor({ state: "detached", timeout: 15_000 }).catch(() => undefined);
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

for (const width of [1280, 375]) {
  for (const theme of ["light", "dark"] as const) {
    test.describe(`axe at ${width}px, ${theme} theme`, () => {
      test.use({ viewport: { width, height: width === 375 ? 812 : 900 } });

      test("no serious or critical violation on any main screen", async ({ page }) => {
        test.setTimeout(240_000);
        await signIn(page, "alice");
        if (theme === "dark") {
          await apiPut(page, "/preferences", { ...DEFAULT_PREFS, theme: "dark" });
          await page.evaluate(() => sessionStorage.clear());
        }
        const problems: string[] = [];
        for (const screen of await screens(page)) {
          await page.goto(screen.path);
          await settled(page);
          if ((await page.locator("main h1").first().textContent())?.includes(NOT_FOUND)) continue; // not built yet
          if (theme === "dark") await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
          const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
          for (const v of result.violations.filter((x) => x.impact === "serious" || x.impact === "critical")) {
            problems.push(`${screen.name}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
          }
        }
        expect(problems, problems.join("\n")).toEqual([]);
      });
    });
  }
}

test.describe("titles, focus and messages", () => {
  test("every screen has its own title, and it changes with each move", async ({ page }) => {
    await signIn(page, "alice");
    await expect(page).toHaveTitle(/^Dashboard - .+/);
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Add job" }).click();
    const shown = page.locator("main h1:visible").first(); // the old screen's heading stays in the page, hidden, while the new one loads
    await expect(shown).not.toHaveText(/^Good (morning|afternoon|evening)/);
    const heading = (await shown.textContent())!.trim();
    await expect(page).toHaveTitle(new RegExp(`^${heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} - .+`));
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Contacts" }).click();
    await expect(page).toHaveTitle(/^Contacts and referrals - .+/);
  });

  test("a screen opened directly from its address has its own title too, not only after a move", async ({ page }) => {
    await signIn(page, "alice", "/app/contacts");
    await expect(page).toHaveTitle(/^Contacts and referrals - .+/);
    await page.reload();
    await expect(page).toHaveTitle(/^Contacts and referrals - .+/);
  });

  test("the title of a page that does not exist says so", async ({ page }) => {
    await signIn(page, "alice", "/app/nothing-here");
    await expect(page).toHaveTitle(/^We could not find that page - /);
  });

  test("focus lands in the main area after a move, and is left alone on the first load and when only the query changes", async ({ page }) => {
    await signIn(page, "alice");
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Insights" }).click();
    await expect.poll(() => page.evaluate(() => !!document.getElementById("main")?.contains(document.activeElement))).toBe(true);
    await expect(page.getByTestId("announcer")).toContainText(/\S/);

    const theme = page.getByRole("button", { name: "Switch between light and dark" });
    await theme.focus();
    await page.evaluate(() => history.pushState(null, "", "/app/insights?x=1"));
    await page.waitForTimeout(400);
    await expect(theme).toBeFocused();
  });

  test("the live regions are on the page before any message, and an error is read out inside the alert region", async ({ page }) => {
    await signIn(page, "alice");
    await expect(page.getByTestId("toasts-polite")).toHaveAttribute("aria-live", "polite");
    await expect(page.getByTestId("toasts-alert")).toHaveText("");
    // The same event the app's own notify() sends: no screen has a button that raises an error on demand any more.
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("so-toast", { detail: { id: 9001, text: "Something went wrong", tone: "error" } })));
    await expect(page.getByTestId("toasts-alert")).toContainText("Something went wrong");
  });

  test("a refused form says how many problems it has and moves to the first one", async ({ page }) => {
    await signIn(page, "alice", "/app/sources");
    await page.getByLabel(/The company's name in that address/).fill("not a valid name!");
    await page.locator("form").filter({ hasText: "Which hiring system" }).getByRole("button", { name: "Check and add" }).click(); // the page has a second form, for careers pages
    await expect(page.getByRole("alert").filter({ hasText: /\S/ }).first()).toBeVisible();
    if ((await page.locator("[aria-invalid=true]").count()) > 0) {
      await expect(page.getByTestId("announcer")).toContainText(/problems? to fix/);
      await expect(page.locator("[aria-invalid=true]").first()).toBeFocused();
    }
  });

  test("the account menu is a disclosure: Enter opens it onto its first entry, Escape closes it and returns to the button", async ({ page }) => {
    await signIn(page, "alice");
    const button = page.getByRole("button", { name: "Your account" });
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(button).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("link", { name: "Your profile" })).toBeFocused();
    expect(await page.getByRole("menu").count()).toBe(0);
    await page.keyboard.press("Escape");
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect(button).toBeFocused();
    await button.click();
    await page.getByRole("heading", { level: 1 }).click();
    await expect(button).toHaveAttribute("aria-expanded", "false"); // a click outside closes it
  });
});

test.describe("the sidebar on a wide screen", () => {
  test.use({ viewport: { width: 1280, height: 900 } });
  test("is a plain landmark: no dialog, nothing shut off", async ({ page }) => {
    await signIn(page, "alice");
    await expect(page.getByRole("complementary", { name: "Sidebar" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await page.locator("header[inert], main[inert]").count()).toBe(0);
  });
});

test.describe("the menu drawer on a phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("is a real dialog: focus goes in and stays in, the page behind is shut off, Escape closes it and returns to the button", async ({ page }) => {
    await signIn(page, "alice");
    const opener = page.getByRole("button", { name: "Open the menu" });
    await opener.click();
    const dialog = page.getByRole("dialog", { name: "Menu" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    const inside = () => page.evaluate(() => !!document.querySelector('[role="dialog"]')?.contains(document.activeElement));
    await expect.poll(inside).toBe(true);
    expect(await page.evaluate(() => document.activeElement?.tagName)).toBe("A"); // the first link
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press("Tab");
      expect(await inside()).toBe(true);
    }
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Shift+Tab");
      expect(await inside()).toBe(true);
    }
    expect(await page.locator("header[inert]").count()).toBe(1);
    expect(await page.locator("main[inert]").count()).toBe(1);
    expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    expect(await page.locator("header[inert], main[inert]").count()).toBe(0);
    expect(await page.evaluate(() => document.body.style.overflow)).toBe("");
  });

  test("the backdrop and the close button close it, and a link in it moves to that screen with the page awake again", async ({ page }) => {
    await signIn(page, "alice");
    await page.getByRole("button", { name: "Open the menu" }).click();
    await page.getByRole("button", { name: "Close the menu" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Open the menu" }).click();
    await page.mouse.click(360, 400); // on the backdrop, right of the drawer
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Open the menu" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Insights" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => !!document.getElementById("main")?.contains(document.activeElement))).toBe(true);
  });

  test("the buttons in the header are at least 44 px", async ({ page }) => {
    await signIn(page, "alice");
    for (const name of ["Open the menu", "Switch between light and dark", "Your account"]) {
      const box = (await page.getByRole("button", { name }).boundingBox())!;
      expect(box.width, name).toBeGreaterThanOrEqual(44);
      expect(box.height, name).toBeGreaterThanOrEqual(44);
    }
  });
});
