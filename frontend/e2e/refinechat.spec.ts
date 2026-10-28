import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { signIn } from "./helpers";

// The AI answer is stubbed at the page (no real network, and alice has no AI key); the server side is covered by tracker/tests_refine.py.
const AI = { available: true, settings_link: "/profile/ai?preset=gemini", missing_message: "Add your free Google AI Studio key in AI settings to use this." };

async function currentCvId(page: Page): Promise<number> {
  return page.evaluate(async () => (await (await fetch("/api/v1/cv")).json()).masters[0].id);
}

test("a CV: ask for a change, see the answer and what needs checking, open the new version, go back", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  const id = await currentCvId(page);
  const messages = [
    { id: 1, role: "user", text: "Make it shorter", flagged_count: 0, result_id: null, created_at: "2026-01-01T00:00:00Z" },
    { id: 2, role: "assistant", text: "Dropped two minor bullets.", flagged_count: 1, result_id: id, created_at: "2026-01-01T00:00:01Z" },
  ];
  let sent = "";
  await page.route(`**/api/v1/cv/${id}/refine`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: { ai: AI, messages: [], undo_to: null } });
    sent = (route.request().postDataJSON() as { message: string }).message;
    return route.fulfill({ json: { id, summary: "Dropped two minor bullets.", flagged: true, flagged_count: 1, check_report: [], exportable: false, messages, undo_to: id } });
  });
  await page.goto(`/app/cv/${id}`);
  const toggle = page.getByRole("button", { name: "Ask for changes" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText(/Tell the AI what you would like different/)).toBeVisible();

  await page.getByLabel("What would you like changed?").fill("Make it shorter");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => sent).toBe("Make it shorter");
  // the new version opens with the chat still open, showing the earlier turns
  await expect(page.getByRole("button", { name: "Ask for changes" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#refine-panel-cv").getByText("Dropped two minor bullets.")).toBeVisible();

  const results = await new AxeBuilder({ page }).include("#refine-panel-cv").analyze();
  expect(results.violations).toEqual([]);
});

test("a cover letter: the change shows here with its flagged lines, and Undo brings the old text back", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  // a made-up letter: writing a real one would try to fetch the job posting over the network
  const id = 999001;
  const letter = {
    id, content: "Dear hiring team,\n\nI build payment APIs.\n\nKind regards,\n[Your name]", source: "keywords", source_label: "Built from your CV (no AI)", provider: "",
    updated_at: "2026-01-01T00:00:00Z", job: { id: 1, role: "Backend Engineer", company: "Acme" }, flagged: false, flagged_count: 0, check_report: [] as { kind: string; text: string; line: number }[],
    approved: false, approved_at: null, exportable: true, downloads: null,
  };
  let current: Record<string, unknown> = letter;
  await page.route(`**/api/v1/cover/${id}`, (route) => route.fulfill({ json: current }));
  const changed = {
    ...letter, content: "Dear hiring team,\n\nI led 900 engineers at Initech.\n\nKind regards,\n[Your name]", source: "ai", source_label: "AI", flagged: true, flagged_count: 1,
    check_report: [{ kind: "number", text: "900", line: 3 }], approved: false, exportable: false, downloads: null,
  };
  const turns = [
    { id: 1, role: "user", text: "Mention big teams", flagged_count: 0, result_id: null, created_at: "2026-01-01T00:00:00Z" },
    { id: 2, role: "assistant", text: "Added a line about leading engineers.", flagged_count: 1, result_id: null, created_at: "2026-01-01T00:00:01Z" },
  ];
  let state = { ai: AI, messages: [] as typeof turns, can_undo: false };
  await page.route(`**/api/v1/cover/${id}/refine`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: state });
    state = { ai: AI, messages: turns, can_undo: true };
    current = changed;
    return route.fulfill({ json: { summary: "Added a line about leading engineers.", letter: changed, messages: turns, can_undo: true } });
  });
  await page.route(`**/api/v1/cover/${id}/refine/undo`, async (route) => {
    state = { ai: AI, messages: turns, can_undo: false };
    current = letter;
    return route.fulfill({ json: { summary: "Went back to the version before the last change.", letter, messages: turns, can_undo: false } });
  });
  await page.goto(`/app/cover/${id}`);
  await page.getByRole("button", { name: "Ask for changes" }).click();
  await page.getByLabel("What would you like changed?").fill("Mention big teams");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Added a line about leading engineers.").first()).toBeVisible();
  await expect(page.locator("#refine-panel-cover").getByText(/Number 900/)).toBeVisible();
  await page.getByRole("button", { name: "Undo the last change" }).click();
  await expect(page.getByRole("button", { name: "Undo the last change" })).toHaveCount(0);
  const results = await new AxeBuilder({ page }).include("#refine-panel-cover").analyze();
  expect(results.violations).toEqual([]);
});

test("without an AI key the chat says to set it up first", async ({ page }) => {
  await signIn(page, "alice", "/app/cv");
  const id = await currentCvId(page);
  await page.goto(`/app/cv/${id}`);
  await page.getByRole("button", { name: "Ask for changes" }).click();
  await expect(page.getByText("Add your free Google AI Studio key in AI settings to use this.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Set up AI first" })).toBeVisible();
});
