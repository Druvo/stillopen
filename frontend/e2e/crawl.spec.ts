import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/**
 * Every screen of the app, opened for a person with data and for people with none, must render without a script error and without
 * the framework's "Application error" page. A crash on one screen for one kind of person is the failure this guards against.
 */

const PEOPLE = ["alice", "bob", "carol"]; // carol has no jobs and has not seen the welcome questions

async function ids(page: Page) {
  return page.evaluate(async () => {
    const get = async (path: string) => {
      try {
        const r = await fetch(`/api/v1${path}`, { credentials: "same-origin" });
        return r.ok ? await r.json() : null;
      } catch {
        return null;
      }
    };
    const dash = await get("/dashboard");
    const cvs = await get("/cv");
    const job = dash?.jobs?.[0]?.id ?? null;
    const cv = cvs?.masters?.[0]?.id ?? null;
    return { job, cv };
  });
}

function screens(job: number | null, cv: number | null): string[] {
  const list = [
    "/", "/postings", "/jobs/add", "/knowledge", "/cv", "/cv/new", "/interviews", "/contacts", "/companies", "/questions", "/offers", "/insights", "/prep", "/help",
    "/profile", "/profile/ai", "/profile/assistant", "/sources", "/welcome", "/stats",
  ];
  if (job) list.push(`/jobs/${job}/edit`, `/jobs/${job}/apply`, `/jobs/${job}/process`);
  if (cv) list.push(`/cv/${cv}`, `/cv/${cv}/diff`);
  return list;
}

for (const person of PEOPLE) {
  test(`no screen crashes for ${person}`, async ({ page }) => {
    test.setTimeout(180_000);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error" && !/Failed to load resource|favicon|net::ERR/.test(m.text())) errors.push(`console: ${m.text()}`);
    });
    await signIn(page, person);
    const { job, cv } = await ids(page);
    const crashed: string[] = [];
    for (const path of screens(job, cv)) {
      errors.length = 0;
      await page.goto(`/app${path === "/" ? "/" : path}`);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(400);
      const boundary = await page.getByText("Application error: a client-side exception has occurred").count();
      if (boundary > 0 || errors.length > 0) crashed.push(`${path}: ${boundary ? "error page; " : ""}${errors.slice(0, 2).join(" | ")}`);
    }
    expect(crashed, crashed.join("\n")).toEqual([]);
  });
}
