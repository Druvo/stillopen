import { test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { PASSWORD, apiPut, DEFAULT_PREFS } from "./helpers";

// Not a normal spec: `pnpm exec playwright test -c playwright.audit.config.ts` takes a screenshot of every signed-in screen of the demo
// person at 375/768/1440 px in light and dark and writes tiny facts per page (sideways overflow, small tap targets, unnamed controls) to
// <E2E_AUDIT_DIR>/facts.json. The pictures are for looking at; the facts are for the table in docs/design/ux-audit.md.
const out = process.env.E2E_AUDIT_DIR || "audit-out";
mkdirSync(out, { recursive: true });

async function screens(page: Page) {
  const ids = await page.evaluate(async () => {
    const get = async (p: string) => {
      const r = await fetch(`/api/v1${p}`, { credentials: "same-origin" });
      return r.ok ? r.json() : null;
    };
    const d = await get("/dashboard");
    const c = await get("/cv");
    return { job: d?.jobs?.[0]?.id ?? null, cv: c?.masters?.[0]?.id ?? null };
  });
  const list = ["/", "/postings", "/jobs/add", "/knowledge", "/cv", "/cv/new", "/interviews", "/contacts", "/companies", "/questions", "/offers", "/insights", "/prep", "/help", "/profile", "/profile/ai", "/profile/ai/usage", "/notifications", "/profile/assistant", "/sources", "/welcome", "/stats"];
  if (ids.job) list.push(`/jobs/${ids.job}/edit`, `/jobs/${ids.job}/apply`, `/jobs/${ids.job}/process`);
  if (ids.cv) list.push(`/cv/${ids.cv}`, `/cv/${ids.cv}/diff`);
  return list;
}

test("audit shots", async ({ page }) => {
  test.setTimeout(1_800_000);
  await page.goto("/accounts/login/?next=/app/");
  await page.locator("input[name=login]").fill("jane");
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForURL(/\/app\//);
  const facts: Record<string, unknown> = {};
  for (const [w, h] of [[375, 812], [768, 1024], [1440, 900]]) {
    for (const theme of ["light", "dark"] as const) {
      await page.setViewportSize({ width: w, height: h });
      await apiPut(page, "/preferences", { ...DEFAULT_PREFS, theme, ai_prompt_dismissed: true });
      await page.evaluate(() => sessionStorage.clear());
      for (const path of await screens(page)) {
        await page.goto(`/app${path}`);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(500);
        const name = `${path === "/" ? "home" : path.slice(1).replace(/\//g, "_")}-${w}-${theme}`;
        await page.screenshot({ path: join(out, `${name}.png`), fullPage: false });
        facts[name] = await page.evaluate(() => {
          const over = document.documentElement.scrollWidth - window.innerWidth;
          const small: string[] = [];
          document.querySelectorAll<HTMLElement>("a,button,input,select,textarea,[role=tab]").forEach((el) => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0 || el.closest("[hidden],[inert]")) return;
            if (r.height < 40 || r.width < 40) small.push(`${el.tagName.toLowerCase()}:${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 25)}:${Math.round(r.width)}x${Math.round(r.height)}`);
          });
          const unnamed: string[] = [];
          document.querySelectorAll<HTMLElement>("button,a,input,select").forEach((el) => {
            const name = el.getAttribute("aria-label") || el.textContent?.trim() || (el as HTMLInputElement).labels?.[0]?.textContent || el.getAttribute("title");
            if (!name && (el as HTMLInputElement).type !== "hidden") unnamed.push(el.outerHTML.slice(0, 80));
          });
          return { overflow: over, h1: document.querySelector("h1")?.textContent ?? null, small: small.slice(0, 8), smallCount: small.length, unnamed: unnamed.slice(0, 3) };
        });
      }
    }
  }
  writeFileSync(join(out, "facts.json"), JSON.stringify(facts, null, 1));
});
