import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Stats } from "./api";

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), request: vi.fn() }));

import { request } from "@/lib/api";
import { WeeklyChart } from "./charts";
import { anyChecked, averageText, barPercent, cardTiles, count, dayShort, marketText, maxOf, prepText, strongShareText, waitingText, weekEnd, weekLabel, weeklyHasData, weekTiles, workLabel } from "./logic";
import { YourNumbers } from "./numbers";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const stats = (over: Partial<Stats> = {}): Stats => ({
  as_of: "2026-10-25",
  has_jobs: true,
  week: { found: 4, checked: 2, applied: 1, interviews_soon: 1, followups_due: 2, closing_soon: 0, went_cold: 1 },
  weekly: ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"].map((start, i) => ({ start, found: i, checked: 0, applied: i === 7 ? 1 : 0 })),
  match: { bands: [{ label: "Strong", color: "#0a0", count: 2 }, { label: "A stretch", color: "#a00", count: 1 }], not_checked: 3, average: 71, average_applied: 80, top_band: "Strong", strong_share_applied: 50 },
  applied: { count: 2, reply_rate: 50 },
  sources: [{ label: "Acme Careers", found: 5, applied: 2, interviews: 1 }],
  work: [{ kind: "remote", count: 3 }, { kind: "unknown", count: 1 }],
  countries: [{ name: "Malaysia", count: 2 }],
  waiting: { count: 2, median_days: 9, longest: [{ id: 7, company: "Initech", role: "API Developer", days: 12 }], after_days: 7 },
  skills: { gaps: [{ term: "kubernetes", jobs: 3 }], strengths: [{ term: "python", jobs: 4 }] },
  prep: { active_plans: 1, lessons_done: 3, lessons_total: 10, streak: 2 },
  market: { this_week: 12, last_week: 9, roles: ["Backend Engineer"] },
  ...over,
});

const show = (s: Stats) => {
  vi.mocked(request).mockResolvedValue(s);
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <YourNumbers />
    </QueryClientProvider>,
  );
};

describe("bars and words", () => {
  it("scales bars, with a sliver for a small real value and nothing for zero", () => {
    expect(barPercent(0, 10)).toBe(0);
    expect(barPercent(10, 10)).toBe(100);
    expect(barPercent(5, 10)).toBe(50);
    expect(barPercent(1, 100)).toBe(4);
    expect(barPercent(3, 0)).toBe(0);
    expect(maxOf([])).toBe(1);
    expect(maxOf([0, 0])).toBe(1);
    expect(maxOf([3, 7])).toBe(7);
  });

  it("writes weeks and days", () => {
    expect(dayShort("2026-10-05")).toBe("5 Oct");
    expect(weekEnd("2026-10-27")).toBe("2026-11-02");
    expect(weekLabel("2026-10-19")).toBe("19 Oct to 25 Oct");
    expect(weeklyHasData([{ start: "x", found: 0, checked: 0, applied: 0 }])).toBe(false);
    expect(weeklyHasData([{ start: "x", found: 0, checked: 0, applied: 1 }])).toBe(true);
  });

  it("counts with the right word", () => {
    expect(count(1, "day")).toBe("1 day");
    expect(count(2, "day")).toBe("2 days");
    expect(count(1, "application is", "applications are")).toBe("1 application is");
  });

  it("labels the week tiles and links follow-ups to the dashboard, only when there are some", () => {
    const tiles = weekTiles({ found: 4, checked: 2, applied: 1, interviews_soon: 0, followups_due: 2, closing_soon: 0, went_cold: 1 });
    expect(tiles.map((t) => t.label)).toEqual(["New jobs found", "Fits checked", "Applications sent", "Interviews coming up", "Follow-ups due", "Closing soon", "Postings that closed"]);
    expect(tiles.find((t) => t.key === "followups")).toMatchObject({ value: 2, to: "/" });
    expect(tiles.find((t) => t.key === "interviews")?.to).toBeUndefined();
    expect(weekTiles({ found: 0, checked: 0, applied: 0, interviews_soon: 0, followups_due: 0, closing_soon: 0, went_cold: 0 }).every((t) => !t.to)).toBe(true);
  });

  it("words the averages and the strong-match share, including when they cannot be said", () => {
    expect(averageText(71, 80)).toEqual({ all: "Average fit across your jobs: 71%", applied: "Average fit of the jobs you applied to: 80%" });
    expect(averageText(null, null).all).toMatch(/nothing checked yet/);
    expect(strongShareText({ strong_share_applied: 40, top_band: "Strong" })).toBe("40% of your applications were to a strong match (Strong).");
    expect(strongShareText({ strong_share_applied: 0, top_band: "" })).toBe("0% of your applications were to a strong match.");
    expect(strongShareText({ strong_share_applied: null, top_band: "Strong" })).toMatch(/^Once you have applied/);
    expect(anyChecked({ bands: [{ label: "a", color: "", count: 0 }] })).toBe(false);
  });

  it("words waiting, work kinds, the market, prep and the dashboard card", () => {
    expect(waitingText({ count: 0, median_days: null, longest: [], after_days: 7 })).toBe("Nothing is waiting for a reply right now.");
    expect(waitingText({ count: 3, median_days: 9, longest: [], after_days: 7 })).toBe("3 applications are waiting for a reply, typically for 9 days.");
    expect(waitingText({ count: 1, median_days: 1, longest: [], after_days: 7 })).toBe("1 application is waiting for a reply, typically for 1 day.");
    expect(workLabel("onsite")).toBe("On-site");
    expect(workLabel("unknown")).toBe("Not stated");
    expect(marketText({ this_week: 1, last_week: 0, roles: ["A", "B"] })).toBe("1 new posting matched A, B this week, and 0 last week.");
    expect(prepText({ active_plans: 2, lessons_done: 3, lessons_total: 10, streak: 0 })).toEqual({ plans: "2 active prep plans", lessons: "3 of 10 lessons done", streak: "No streak yet. A short lesson today starts one." });
    expect(cardTiles({ week: stats().week, waiting: stats().waiting }).map((t) => [t.label, t.value])).toEqual([["New jobs", 4], ["Fits checked", 2], ["Applied", 1], ["Waiting for a reply", 2]]);
  });
});

describe("the weekly chart", () => {
  it("is a figure with a caption, drawn for the eye only, and a table with the same numbers for everyone", () => {
    const { container } = render(<WeeklyChart weekly={stats().weekly} />);
    expect(container.querySelector("figure figcaption")?.textContent).toMatch(/week by week/);
    expect(container.querySelector("[aria-hidden]")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Weekly numbers" });
    expect(within(table).getAllByRole("row")).toHaveLength(9);
    expect(within(table).getByRole("columnheader", { name: "Fit checked" })).toBeTruthy();
  });
});

describe("Your numbers", () => {
  it("shows every section, in order, with the numbers", async () => {
    show(stats());
    await screen.findByRole("heading", { name: "Your numbers" });
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(["This week", "Last 8 weeks", "Goals and streak", "Calendar", "Match quality", "Waiting for a reply", "Where jobs come from", "Kinds of work and countries", "Skills that keep coming up", "Prep", "Roles on the boards"]);
    expect(screen.getByRole("link", { name: "See them on your dashboard" }).getAttribute("href")).toBe("/app/");
    expect(screen.getByText("50% of your applications were to a strong match (Strong).")).toBeTruthy();
    expect(screen.getByText("2 applications are waiting for a reply, typically for 9 days.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open" }).getAttribute("href")).toBe("/app/jobs/7/apply");
    expect(screen.getByText("Acme Careers")).toBeTruthy();
    expect(screen.getByText("kubernetes")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Prep plans" }).getAttribute("href")).toBe("/app/prep");
    expect(screen.getByText("12 new postings matched Backend Engineer this week, and 9 last week.")).toBeTruthy();
  });

  it("hides Prep when it is off, and says what to do when the roles are not set", async () => {
    show(stats({ prep: null, market: null }));
    await screen.findByRole("heading", { name: "Your numbers" });
    expect(screen.queryByRole("heading", { name: "Prep" })).toBeNull();
    expect(screen.getByText(/Add the roles you want in/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Prep plans" })).toBeNull();
  });

  it("says what to do in every empty section", async () => {
    show(
      stats({
        weekly: stats().weekly.map((w) => ({ ...w, found: 0, applied: 0 })),
        match: { bands: [{ label: "Strong", color: "#0a0", count: 0 }], not_checked: 4, average: null, average_applied: null, top_band: "Strong", strong_share_applied: null },
        waiting: { count: 0, median_days: null, longest: [], after_days: 7 },
        skills: { gaps: [], strengths: [] },
        sources: [],
        work: [],
        countries: [],
      }),
    );
    await screen.findByRole("heading", { name: "Your numbers" });
    expect(screen.getByText(/Nothing in the last 8 weeks yet/)).toBeTruthy();
    expect(screen.getByText(/None of your jobs has been checked yet/)).toBeTruthy();
    expect(screen.getByText("Nothing is waiting for a reply right now.")).toBeTruthy();
    expect(screen.getByText(/Check how well a few jobs fit you and the skills that keep coming up will appear here/)).toBeTruthy();
    expect(screen.getByText(/Once you have jobs, this shows where they came from/)).toBeTruthy();
    expect(screen.getByText(/Once your jobs say whether they are remote/)).toBeTruthy();
  });

  it("for someone with no jobs, shows one empty state with a way forward", async () => {
    show(stats({ has_jobs: false }));
    await screen.findByText(/You are not tracking any jobs yet/);
    expect(screen.getByRole("link", { name: "Go to my dashboard" }).getAttribute("href")).toBe("/app/");
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  });
});
