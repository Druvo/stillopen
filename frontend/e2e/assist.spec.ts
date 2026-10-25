import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/** alice's "Backend Engineer" job at Acme (it has a description) and her Initech job. alice has no AI key, so these are the free paths. */
async function jobId(page: Page, company: string): Promise<number> {
  return page.evaluate(async (name) => {
    const data = await (await fetch("/api/v1/dashboard")).json();
    return data.jobs.find((j: { company: string }) => j.company === name).id as number;
  }, company);
}

const PREP = {
  prep: {
    job: { id: 1, role: "Backend Engineer", company: "Acme" },
    generated_at: "2026-10-25T10:00:00Z",
    notice: "Written by AI, which can be wrong. Check it and put it in your own words.",
    outline_note: "",
    dropped_points: 1,
    groups: [
      { key: "role", title: "About the role and skills", questions: [{ id: "role-1", question: "How do you design a Django API?", testing: "Whether you can explain trade-offs.", outline: ["Describe the payments API you built."], flags: [] }] },
      { key: "behavioural", title: "Behavioural", questions: [{ id: "behavioural-1", question: "Tell me about leading a team.", testing: "Ownership.", outline: [], flags: [] }] },
    ],
  },
  ai: true,
};

/** Every request that would change something on the server, so a test can say "nothing was saved". */
function writes(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (r) => {
    if (["PUT", "PATCH", "DELETE"].includes(r.method()) && r.url().includes("/api/v1/")) seen.push(`${r.method()} ${new URL(r.url()).pathname}`);
  });
  return seen;
}

test("without an AI key the apply screen says how to add one, and the free message draft still works", async ({ page }) => {
  await signIn(page, "alice");
  const id = await jobId(page, "Acme");
  await page.goto(`/app/jobs/${id}/apply`);
  await expect(page.getByRole("heading", { name: "Prepare for interviews" })).toBeVisible();
  const lines = page.getByTestId("no-ai-key");
  await expect(lines).toHaveCount(2); // interview questions and application answers
  await expect(lines.first()).toContainText("Add your free Google AI Studio key in AI settings to use this.");
  await expect(lines.first().getByRole("link", { name: "AI settings" })).toHaveAttribute("href", "/app/profile/ai?preset=gemini");
  await expect(page.getByRole("button", { name: "Write my interview questions" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Polish it with AI" })).toHaveCount(0);

  await page.getByRole("button", { name: "Write a draft (free)" }).click();
  const draft = page.getByTestId("message-draft"); // the apply screen has another "Subject" (the application email)
  await expect(draft.getByLabel("Subject")).toHaveValue(/Following up: Backend Engineer/);
  await expect(draft.getByLabel("Message")).toHaveValue(/Acme/);
  await expect(draft.getByText("It is never sent for you.")).toBeVisible();
});

test("interview questions render from the API, copy to the clipboard, and nothing is saved by itself", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page, "alice");
  const id = await jobId(page, "Acme");
  const changed = writes(page);
  await page.route("**/api/v1/assist/status", (route) => route.fulfill({ json: { ai: true, settings_path: "/profile/ai?preset=gemini", message: "" } }));
  await page.route(`**/api/v1/jobs/${id}/interview-prep`, (route) => route.fulfill({ json: route.request().method() === "POST" ? PREP : { prep: null, ai: true } }));
  await page.goto(`/app/jobs/${id}/apply`);
  await page.getByRole("button", { name: "Write my interview questions" }).click();
  await expect(page.getByText("How do you design a Django API?")).toBeVisible();
  await expect(page.getByText("What they are really testing: Whether you can explain trade-offs.")).toBeVisible();
  await expect(page.getByText("Describe the payments API you built.")).toBeVisible();
  await expect(page.getByText(/We left out 1 outline point/)).toBeVisible();
  await expect(page.getByText(/Written by AI, which can be wrong/).first()).toBeVisible();

  await page.getByRole("button", { name: "Copy" }).first().click();
  await expect(page.getByText("Copied.")).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("How do you design a Django API?");
  expect(copied).toContain("- Describe the payments API you built.");
  expect(changed).toEqual([]);
});

test("practising an answer shows feedback; an application answer shows what could not be matched and can be copied", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page, "alice");
  const id = await jobId(page, "Acme");
  const changed = writes(page);
  await page.route("**/api/v1/assist/status", (route) => route.fulfill({ json: { ai: true, settings_path: "/profile/ai?preset=gemini", message: "" } }));
  await page.route(`**/api/v1/jobs/${id}/interview-prep`, (route) => route.fulfill({ json: PREP }));
  await page.route(`**/api/v1/jobs/${id}/interview-prep/feedback`, (route) =>
    route.fulfill({
      json: { feedback: { summary: "A clear start that needs a result.", works: ["You name what you built."], vague: [], add: ["Say how many people used it."], star: { situation: true, task: false, action: true, result: false }, length: { words: 12, note: "Quite short." }, notice: "Written by AI, which can be wrong." } },
    }),
  );
  await page.route(`**/api/v1/jobs/${id}/application-answer`, (route) =>
    route.fulfill({ json: { answer: "I enjoy backend work and built a payments API at Initech.", words: 11, flagged: [{ kind: "name", text: "Initech", line: 1 }], flagged_count: 1, notice: "Written by AI, which can be wrong." } }),
  );
  await page.goto(`/app/jobs/${id}/apply`);

  const practise = page.locator("details").filter({ hasText: "Practise this answer" }).first(); // every question has one
  await practise.getByText("Practise this answer").click();
  await practise.getByLabel(/Your answer, written the way you would say it/).fill("I built a payments API in Django and led the work with my team.");
  await practise.getByRole("button", { name: "Get feedback" }).click();
  const feedback = page.getByTestId("answer-feedback");
  await expect(feedback).toContainText("A clear start that needs a result.");
  await expect(feedback).toContainText("not clear yet: your task, the result.");
  await expect(feedback).toContainText("Quite short.");

  await page.getByLabel("The question from the application form").fill("Why do you want this role?");
  await page.getByRole("button", { name: "Draft an answer" }).click();
  await expect(page.getByLabel(/Your draft/)).toHaveValue(/payments API at Initech/);
  await expect(page.getByText(/We could not match these to your own material: Initech/)).toBeVisible();
  await page.getByRole("button", { name: "Copy the answer" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("payments API at Initech");
  expect(changed).toEqual([]);
});

test("suggested roles are chips that only fill the box; nothing is saved until the form is saved", async ({ page }) => {
  await signIn(page, "alice", "/app/profile");
  const changed = writes(page);
  await page.route("**/api/v1/profile/suggest", (route) => route.fulfill({ json: { roles: ["Data Engineer", "Backend Engineer"], places: [], method: "rules", notice: "" } }));
  const box = page.getByLabel("The roles you want");
  await expect(box).toBeVisible();
  await page.getByRole("button", { name: "Suggest roles from my CV" }).click();
  await page.getByRole("button", { name: "+ Data Engineer" }).click();
  await expect(box).toHaveValue(/Data Engineer/);
  await expect(page.getByRole("button", { name: "✓ Data Engineer" })).toBeDisabled();
  expect(changed).toEqual([]);
  const saved = await page.evaluate(async () => (await (await fetch("/api/v1/profile")).json()).profile.target_roles as string);
  expect(saved).not.toContain("Data Engineer");
});

test("the free reading of a posting is never empty and says it is not AI", async ({ page }) => {
  await signIn(page, "alice");
  const id = await jobId(page, "Acme");
  await page.goto(`/app/jobs/${id}/edit`);
  await expect(page.getByRole("heading", { name: "What this role really needs" })).toBeVisible();
  await expect(page.getByText(/add your free Google AI Studio key in/i)).toBeVisible();
  await page.getByRole("button", { name: "Read this posting" }).click();
  const summary = page.getByTestId("posting-summary");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("Red flags");
  await expect(summary).toContainText("A quick read by simple rules, not by AI.");
});

test("Insights starts with the week in plain words", async ({ page }) => {
  await signIn(page, "alice", "/app/insights");
  const text = page.getByTestId("week-summary");
  await expect(text).toBeVisible();
  await expect(text).toContainText(/added \d+ jobs? and applied to \d+|have not added a job/);
});
