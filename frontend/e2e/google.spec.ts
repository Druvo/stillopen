import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

// Only OUR api is stubbed (page.route): the browser never talks to Google, and the real server never does either.

type Status = { available: boolean; connected: boolean; email: string; connected_at: string | null; calendar_sync: boolean; problem: string; message: string };

async function jobId(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const r = await fetch("/api/v1/dashboard");
    return (await r.json()).jobs[0].id as number;
  });
}

test("Connections: connect, switch the calendar on, disconnect", async ({ page }) => {
  await signIn(page, "alice");
  let status: Status = { available: true, connected: false, email: "", connected_at: null, calendar_sync: false, problem: "", message: "" };
  await page.route("**/api/v1/google/status", (r) => r.fulfill({ json: status }));
  await page.route("**/api/v1/google/connect", (r) => {
    status = { ...status, connected: true, email: "me@gmail.example", connected_at: "2030-01-01T00:00:00Z" };
    return r.fulfill({ json: { url: "/app/profile/connections?back=1" } });
  });
  await page.route("**/api/v1/google/settings", (r) => {
    status = { ...status, calendar_sync: JSON.parse(r.request().postData() ?? "{}").calendar_sync };
    return r.fulfill({ json: status });
  });
  await page.route("**/api/v1/google/disconnect", (r) => {
    status = { ...status, connected: false, email: "", calendar_sync: false };
    return r.fulfill({ json: status });
  });
  await page.goto("/app/profile/connections");
  await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
  await expect(page.getByText("It never sends anything by itself")).toBeVisible();
  await page.getByRole("button", { name: "Connect my Google account" }).click();
  await expect(page.getByText("me@gmail.example")).toBeVisible();
  const sync = page.getByLabel(/Keep my Google Calendar in step/);
  await sync.click();
  await expect(sync).toBeChecked();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Disconnect Google" }).click();
  await expect(page.getByRole("button", { name: "Connect my Google account" })).toBeVisible();
});

test("Connections says so when the site has not set Google up", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/app/profile/connections");
  await expect(page.getByText(/Not set up on this site/)).toBeVisible();
});

test("Send from Gmail: nothing goes until the preview is confirmed, and an edit throws the preview away", async ({ page }) => {
  await signIn(page, "alice");
  const id = await jobId(page);
  const sent: unknown[] = [];
  await page.route(`**/api/v1/jobs/${id}/apply`, async (route) => {
    const real = await route.fetch();
    const data = await real.json();
    data.google = { available: true, connected: true, suggested_to: "jobs@acme.example", thread: true };
    await route.fulfill({ json: data });
  });
  await page.route(`**/api/v1/jobs/${id}/google/preview`, (r) => {
    const m = JSON.parse(r.request().postData() ?? "{}");
    return r.fulfill({ json: { ...m, from: "me@gmail.example", digest: "abc", attachments: [{ name: "CV-v1.docx", bytes: 20480 }] } });
  });
  await page.route(`**/api/v1/jobs/${id}/google/send`, (r) => {
    sent.push(JSON.parse(r.request().postData() ?? "{}"));
    return r.fulfill({ json: { ok: true, to: "jobs@acme.example", follow_up_date: "2030-02-01" } });
  });
  await page.route(`**/api/v1/jobs/${id}/google/messages`, (r) => r.fulfill({ json: { connected: true, linked: true, messages: [], checked_at: null } }));
  await page.route(`**/api/v1/jobs/${id}/google/check`, (r) => r.fulfill({ json: { new: 0, cached: true, messages: [], linked: true } }));
  await page.goto(`/app/jobs/${id}/apply`);
  const card = page.locator("div", { has: page.getByRole("heading", { name: "Send from my Gmail" }) }).last();
  await expect(card.getByLabel("Send to")).toHaveValue("jobs@acme.example");
  await expect(card.getByText(/the address the posting itself gives/)).toBeVisible();
  await expect(page.getByRole("button", { name: /^Send to / })).toHaveCount(0);
  await card.getByRole("button", { name: "Preview the email" }).click();
  const preview = page.getByRole("region", { name: "The email exactly as it will be sent" });
  await expect(preview.getByText("CV-v1.docx (20 KB)")).toBeVisible();
  await expect(preview.getByText("jobs@acme.example").first()).toBeVisible();
  // an edit withdraws the preview, so what is sent is always what was looked at
  await card.getByLabel("Subject").fill("Changed subject");
  await expect(preview).toHaveCount(0);
  expect(sent).toHaveLength(0);
  await card.getByRole("button", { name: "Preview the email" }).click();
  await page.getByRole("button", { name: "Send to jobs@acme.example" }).click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toMatchObject({ to: "jobs@acme.example", subject: "Changed subject", digest: "abc", confirm: true });
});

test("Replies: shown as plain text, a draft stays a draft, times can be pasted in", async ({ page }) => {
  await signIn(page, "alice");
  const id = await jobId(page);
  await page.route(`**/api/v1/jobs/${id}/apply`, async (route) => {
    const data = await (await route.fetch()).json();
    data.google = { available: true, connected: true, suggested_to: "", thread: true };
    await route.fulfill({ json: data });
  });
  const message = { id: 7, sender: "HR <hr@acme.example>", sent_at: "2030-01-02T10:00:00Z", snippet: "<img src=x onerror=alert(1)> We would like to talk", from_me: false };
  let checks = 0;
  await page.route(`**/api/v1/jobs/${id}/google/messages`, (r) => r.fulfill({ json: { connected: true, linked: true, messages: [message], checked_at: null } }));
  await page.route(`**/api/v1/jobs/${id}/google/check`, (r) => {
    checks += 1;
    return r.fulfill({ json: { new: 0, cached: false, messages: [message], linked: true } });
  });
  await page.route(`**/api/v1/jobs/${id}/google/draft`, (r) => r.fulfill({ json: { draft: "Dear HR, thank you.\n\nKind regards,\n[Your name]", flags: [], times: "" } }));
  await page.route(`**/api/v1/jobs/${id}/google/times`, (r) => r.fulfill({ json: { count: 3, text: "I am free at these times:\n- Monday 10:00" } }));
  await page.goto(`/app/jobs/${id}/apply`);
  await expect(page.getByText("<img src=x onerror=alert(1)> We would like to talk")).toBeVisible();
  await expect(page.locator("img[src='x']")).toHaveCount(0);
  await page.getByRole("button", { name: "Check for replies" }).click();
  await expect.poll(() => checks).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Draft a reply" }).click();
  const box = page.getByLabel(/Your reply/);
  await expect(box).toHaveValue(/Dear HR/);
  await expect(page.getByText(/It has not been sent/)).toBeVisible();
  await page.getByRole("button", { name: "Suggest interview times" }).click();
  await expect(box).toHaveValue(/Monday 10:00/);
});

test("Interviews: Sync now appears only when the calendar sync is on", async ({ page }) => {
  await signIn(page, "alice");
  let synced = 0;
  await page.route("**/api/v1/interviews", async (route) => {
    const data = await (await route.fetch()).json();
    data.google = { connected: true, sync: true };
    await route.fulfill({ json: data });
  });
  await page.route("**/api/v1/google/calendar/sync**", (r) => {
    synced += 1;
    return r.fulfill({ json: { changed: 0, checked: 1, cached: false, note: "" } });
  });
  await page.goto("/app/interviews");
  await expect.poll(() => synced).toBeGreaterThan(0); // once on opening
  const before = synced;
  await page.getByRole("button", { name: "Sync now with Google Calendar" }).click();
  await expect.poll(() => synced).toBeGreaterThan(before); // and again on the button
});
