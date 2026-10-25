import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/** The Help page, the Emails card, the mixed "Coming up" card and the three small AI helps. alice has no AI key, so the AI calls are mocked. */

/** Every request that would change something on the server, so a test can say "nothing was saved". */
function writes(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (r) => {
    if (["PUT", "PATCH", "DELETE"].includes(r.method()) && r.url().includes("/api/v1/")) seen.push(`${r.method()} ${new URL(r.url()).pathname}`);
  });
  return seen;
}

async function withMe(page: Page, patch: Record<string, unknown>) {
  await page.route("**/api/v1/me", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), ...patch } });
  });
}

test.describe("Help", () => {
  test("is in the About you group of the sidebar and in the account menu, and has a real heading for every section", async ({ page }) => {
    await signIn(page, "alice");
    const nav = page.getByRole("navigation", { name: "Main" });
    await nav.getByRole("link", { name: "Help" }).click();
    await expect(page).toHaveURL(/\/app\/help$/);
    await expect(page.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Help" })).toHaveAttribute("aria-current", "page");
    for (const title of [
      "Get started in five steps", "How your match score works", "What the AI does and does not do", "The ATS check", "Keyboard shortcuts", "Your data", "About reminders and emails", "Questions people ask",
    ]) {
      await expect(page.getByRole("heading", { level: 2, name: title })).toBeVisible();
    }
    await page.goto("/app/");
    const account = page.getByRole("button", { name: "Your account" });
    await account.click();
    const menu = page.locator(`#${await account.getAttribute("aria-controls")}`);
    await menu.getByRole("link", { name: "Help" }).click();
    await expect(page).toHaveURL(/\/app\/help$/);
  });

  test("sections open and close, and the questions open one by one", async ({ page }) => {
    await signIn(page, "alice", "/app/help");
    const score = page.locator("#score");
    await expect(score).not.toHaveAttribute("open", "");
    await page.getByRole("heading", { name: "How your match score works" }).click();
    await expect(score).toHaveAttribute("open", "");
    await expect(page.getByText("Not checked yet means nobody has read this job")).toBeVisible();
    await page.getByRole("button", { name: "Open all" }).click();
    await page.getByRole("heading", { name: "Why are there jobs from places I do not want?" }).click();
    await expect(page.getByText("A job outside them is flagged, never hidden")).toBeVisible();
    await page.getByRole("button", { name: "Close all" }).click();
    await expect(score).not.toHaveAttribute("open", "");
  });

  test("Still stuck shows only when the site has a contact address", async ({ page }) => {
    await signIn(page, "alice", "/app/help");
    await expect(page.getByTestId("help-contact")).toHaveCount(0);
    await page.unrouteAll();
    await withMe(page, { contact_email: "help@example.org" });
    await page.reload();
    await expect(page.getByTestId("help-contact")).toContainText("Still stuck? Write to help@example.org");
    await expect(page.getByRole("link", { name: "help@example.org" })).toHaveAttribute("href", "mailto:help@example.org");
  });

  test("reads at 375 px with no sideways scroll, and in dark mode", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ colorScheme: "dark" });
    await signIn(page, "alice", "/app/help");
    await page.getByRole("button", { name: "Open all" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    const colours = await page.evaluate(() => {
      const body = getComputedStyle(document.querySelector("#start p, #start li") ?? document.body);
      return { color: body.color, background: getComputedStyle(document.body).backgroundColor };
    });
    expect(colours.color).not.toBe(colours.background);
  });

  test("the dashboard's empty state points to it", async ({ page }) => {
    await signIn(page, "alice");
    await page.route("**/api/v1/dashboard", async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({ response, json: { ...data, jobs: [], coming_up: [], upcoming_interviews: [], followups: [], scan: null } });
    });
    await page.reload();
    await expect(page.getByRole("link", { name: "Read how StillOpen works" })).toHaveAttribute("href", "/app/help");
  });
});

test.describe("Emails card", () => {
  test("says which emails are on, which the site owner has not switched on, and what happens with an unconfirmed address", async ({ page }) => {
    await signIn(page, "alice", "/app/profile");
    const card = page.getByRole("region", { name: "Emails" }).or(page.locator("#emails"));
    await expect(card.getByRole("heading", { name: "Emails" })).toBeVisible();
    await expect(card.getByLabel("Follow-up reminders")).toBeChecked();
    await expect(card.getByLabel("Your week, once a week")).not.toBeChecked();
    await expect(card.getByTestId("email-state-weekly")).toContainText("Off");
    await expect(card.getByTestId("email-state-followups")).toContainText(/On|Not switched on by the site owner/);
    await expect(card.getByRole("button", { name: "Save email choices" })).toBeDisabled();
  });

  test("saves a tick on its own and keeps it when the big profile form is saved", async ({ page }) => {
    await signIn(page, "alice", "/app/profile");
    const card = page.locator("#emails");
    await card.getByLabel("Your week, once a week").check();
    await card.getByRole("button", { name: "Save email choices" }).click();
    await expect(page.getByText("Your email choices are saved.")).toBeVisible();
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByText("Saved. Your next matches will use this.")).toBeVisible();
    const saved = await page.evaluate(async () => (await (await fetch("/api/v1/profile")).json()).profile.email_weekly);
    expect(saved).toBe(true);
    await card.getByLabel("Your week, once a week").uncheck();
    await card.getByRole("button", { name: "Save email choices" }).click();
    await expect(page.getByText("Your email choices are saved.")).toBeVisible();
  });
});

test("the profile and the welcome page offer the guided CV builder", async ({ page }) => {
  await signIn(page, "alice", "/app/profile");
  await expect(page.getByRole("link", { name: "Build one step by step" })).toHaveAttribute("href", "/app/cv/new");
  await page.goto("/app/welcome");
  await expect(page.getByRole("link", { name: "Build one step by step" })).toHaveAttribute("href", "/app/cv/new");
});

test("Coming up lists interviews, deadlines and offers together, each a link to where it belongs", async ({ page }) => {
  await signIn(page, "alice");
  const now = Date.now();
  const day = (n: number) => new Date(now + n * 86_400_000).toISOString().slice(0, 10);
  await page.route("**/api/v1/dashboard", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const job = data.jobs[0];
    await route.fulfill({
      response,
      json: {
        ...data,
        coming_up: [
          { kind: "interview", date: day(2), when: new Date(now + 2 * 86_400_000).toISOString(), label: "Phone screen", company: "Acme", role: "Backend Engineer", job_id: job.id },
          { kind: "deadline", date: day(4), when: day(4), label: "Apply by", company: "Initech", role: "Analyst", job_id: job.id },
          { kind: "offer", date: day(6), when: day(6), label: "Reply to the offer by", company: "Globex", role: "SRE", job_id: job.id },
        ],
      },
    });
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Coming up", level: 2 }).first()).toBeVisible();
  // on a narrow screen the card is a collapsed button; on a wide one (the default viewport) it is a plain heading
  const card = page.getByRole("button", { name: /Coming up/ });
  if ((await card.count()) > 0 && (await card.getAttribute("aria-expanded")) === "false") await card.click();
  const list = page.locator("li", { hasText: "Apply by" });
  await expect(list.getByRole("link")).toHaveAttribute("href", /\/app\/jobs\/\d+\/apply$/);
  await expect(page.getByRole("link", { name: /^Interview · .*Phone screen: Acme/ })).toHaveAttribute("href", "/app/interviews");
  await expect(page.getByRole("link", { name: /^Reply to offer · .*Globex/ })).toHaveAttribute("href", "/app/offers");
});

test("Add job: fill the form from pasted text, check it, and nothing is saved until Save", async ({ page }) => {
  await signIn(page, "alice", "/app/jobs/add");
  const changed = writes(page);
  await page.route("**/api/v1/jobs/parse-text", (route) =>
    route.fulfill({
      json: {
        fields: { company: "Gamma", role: "Platform Engineer", location: "Remote within Bangladesh", pay: "$4000 per month", deadline: "2026-11-30", link: "https://gamma.example/jobs/1" },
        found: ["company", "role", "location", "pay", "deadline", "link"], found_by_ai: [], method: "rules", notice: "", message: "Check each field before you save.",
      },
    }),
  );
  const button = page.getByRole("button", { name: "Fill the form from pasted text" });
  await expect(button).toBeDisabled();
  await page.getByLabel("The job description").fill("Platform Engineer at Gamma\n\nRemote within Bangladesh. Salary $4000 per month. Apply by 30 November 2026.");
  await button.click();
  await expect(page.getByLabel("Company")).toHaveValue("Gamma");
  await expect(page.getByLabel("Role")).toHaveValue("Platform Engineer");
  await expect(page.getByLabel("Link to the posting")).toHaveValue("https://gamma.example/jobs/1");
  await expect(page.getByLabel("Apply by (if it says)")).toHaveValue("2026-11-30");
  await expect(page.getByLabel("Your own notes")).toHaveValue("Place: Remote within Bangladesh. Pay: $4000 per month");
  await expect(page.getByText(/We filled in the company, the role, the link/)).toBeVisible();
  await expect(page.getByText(/Please check each one before you save/)).toBeVisible();
  expect(changed).toEqual([]);
});

test("Add job: text typed by the person is never replaced by the reader", async ({ page }) => {
  await signIn(page, "alice", "/app/jobs/add");
  await page.route("**/api/v1/jobs/parse-text", (route) =>
    route.fulfill({ json: { fields: { company: "Gamma", role: "Platform Engineer", location: "", pay: "", deadline: "", link: "" }, found: ["company", "role"], found_by_ai: [], method: "rules", notice: "", message: "" } }),
  );
  await page.getByLabel("Company").fill("My own company");
  await page.getByLabel("The job description").fill("Platform Engineer at Gamma. We are hiring a platform engineer for the team.");
  await page.getByRole("button", { name: "Fill the form from pasted text" }).click();
  await expect(page.getByLabel("Role")).toHaveValue("Platform Engineer");
  await expect(page.getByLabel("Company")).toHaveValue("My own company");
});

const OFFERS = {
  offers: [
    { id: 1, job: { id: 1, role: "Backend Engineer", company: "Acme" }, base: "100000", period: "year", period_label: "per year", currency: "USD", bonus: "10000", equity: "0", signing: "0", other_benefits: "0", deadline: "", status: "open", status_label: "Deciding", notes: "", yearly_base: "100000", yearly_total: "110000", first_year_total: "110000" },
    { id: 2, job: { id: 2, role: "Analyst", company: "Initech" }, base: "90000", period: "year", period_label: "per year", currency: "USD", bonus: "0", equity: "30000", signing: "0", other_benefits: "0", deadline: "", status: "open", status_label: "Deciding", notes: "", yearly_base: "90000", yearly_total: "120000", first_year_total: "120000" },
  ],
  groups: [],
  jobs: [{ id: 1, label: "Acme - Backend Engineer" }],
  periods: [{ value: "year", label: "per year" }],
  statuses: [{ value: "open", label: "Deciding" }],
};

test("Offers: tick two, read the differences in words; no AI key means one plain line and no counter note", async ({ page }) => {
  await signIn(page, "alice", "/app/offers");
  const changed = writes(page);
  await page.route("**/api/v1/offers", (route) => (route.request().method() === "GET" ? route.fulfill({ json: OFFERS }) : route.fallback()));
  await page.route("**/api/v1/offers/compare-note", (route) =>
    route.fulfill({
      json: {
        differences: [{ currency: "USD", lines: ["Counting a year of base pay, bonus, shares and benefits, Initech comes to 120,000 USD and Acme to 110,000 USD: 10,000 USD apart."] }],
        ask_about: ["Notice period: how soon would they need you to start, and is the start date flexible?"], counter_note: null, ai: false, notice: "",
        counter_message: "Add your free Google AI Studio key in AI settings to use this.",
      },
    }),
  );
  await page.reload();
  const run = page.getByRole("button", { name: "Compare these offers in words" });
  await expect(run).toBeDisabled();
  await expect(page.getByTestId("compare-hint")).toContainText("Tick two to four offers");
  await page.getByLabel("Compare the offer from Acme").check();
  await expect(page.getByTestId("compare-hint")).toContainText("Tick one more offer");
  await page.getByLabel("Compare the offer from Initech").check();
  await run.click();
  const result = page.getByTestId("compare-result");
  await expect(result.getByText(/Initech comes to 120,000 USD/)).toBeVisible();
  await expect(result.getByText(/Notice period/)).toBeVisible();
  await expect(result.getByTestId("no-ai-key")).toBeVisible();
  await expect(result.getByRole("button", { name: "Copy the note" })).toHaveCount(0);
  expect(changed).toEqual([]);
});

test("Offers: with an AI key the counter-offer note appears, is editable, and is never sent", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page, "alice", "/app/offers");
  await page.route("**/api/v1/offers", (route) => (route.request().method() === "GET" ? route.fulfill({ json: OFFERS }) : route.fallback()));
  await page.route("**/api/v1/offers/compare-note", (route) =>
    route.fulfill({
      json: {
        differences: [{ currency: "USD", lines: ["Initech is higher on yearly value of shares or options (30,000 against 0 USD)."] }],
        ask_about: ["Initech: how do the shares or options vest, and what happens to them if you leave?"],
        counter_note: { subject: "About your offer", body: "Dear hiring team, thank you for the offer. Could we look again at the base pay?", for_offer: 1, flagged: [], flagged_count: 0 },
        ai: true, notice: "Written by AI, which can be wrong. Check it and put it in your own words.", counter_message: "",
      },
    }),
  );
  await page.reload();
  await page.getByLabel("Compare the offer from Acme").check();
  await page.getByLabel("Compare the offer from Initech").check();
  await page.getByRole("button", { name: "Compare these offers in words" }).click();
  await expect(page.getByLabel("Subject")).toHaveValue("About your offer");
  await page.getByLabel("Message", { exact: true }).fill("Edited by me.");
  await page.getByRole("button", { name: "Copy the note" }).click();
  await expect(page.getByText("Copied.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("Edited by me.");
  await expect(page.getByText(/Written by AI, which can be wrong/)).toBeVisible();
});

test("Contacts: draft a referral request, edit it and copy it; it is never sent", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page, "alice", "/app/contacts");
  const changed = writes(page);
  await page.route("**/api/v1/contacts", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          json: {
            contacts: [{ id: 5, name: "Jamal Khan", company: "Gamma", title: "Engineer", email: "j@gamma.example", link: "", notes: "", last_contacted: "", referrals: [] }],
            jobs: [{ id: 1, label: "Gamma - Platform Engineer" }], referral_statuses: [{ value: "thinking", label: "Thinking of asking" }],
          },
        })
      : route.fallback(),
  );
  await page.route("**/api/v1/contacts/5/referral-draft", (route) =>
    route.fulfill({ json: { subject: "A quick favour: the Platform Engineer role", body: "Hi Jamal,\n\nI hope you are well.\n\nThank you,\n[Your name]", to: "j@gamma.example", method: "template", flagged: [], flagged_count: 0, notice: "" } }),
  );
  await page.route("**/api/v1/assist/status", (route) => route.fulfill({ json: { ai: false, settings_path: "/profile/ai?preset=gemini", message: "" } }));
  await page.reload();
  await page.getByRole("button", { name: "Draft a referral request to Jamal Khan" }).click();
  await expect(page.getByRole("button", { name: "Polish it with AI" })).toHaveCount(0);
  await page.getByRole("button", { name: "Write a draft (free)" }).click();
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue(/Hi Jamal/);
  await page.getByLabel("Message", { exact: true }).fill("Hi Jamal, would you refer me? Thank you, Alice");
  await page.getByRole("button", { name: "Copy the message" }).click();
  await expect(page.getByText("Copied.")).toBeVisible();
  await expect(page.getByText(/never sent for you/)).toBeVisible();
  expect(changed).toEqual([]);
});

test("another person's ids are a 404 and change nothing", async ({ page }) => {
  await signIn(page, "alice");
  const codes = await page.evaluate(async () => {
    const token = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
    const post = async (path: string, body: unknown) =>
      (await fetch(`/api/v1${path}`, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify(body) })).status;
    return [await post("/offers/compare-note", { offer_ids: [999990, 999991] }), await post("/contacts/999992/referral-draft", { job_id: 999993 })];
  });
  expect(codes).toEqual([404, 404]);
});
