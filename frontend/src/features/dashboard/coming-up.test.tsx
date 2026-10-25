import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ComingUpItem } from "@/lib/types";

vi.mock("./api", () => ({ dashboardApi: {}, useMe: vi.fn() }));

import { comingUpAllLinks, comingUpItems, comingUpText, comingUpTo, comingUpWhen } from "./coming-up";
import { ComingUpBody } from "./panels";

afterEach(cleanup);

const interview: ComingUpItem = { kind: "interview", date: "2026-10-27", when: new Date(2026, 9, 27, 14, 30).toISOString(), label: "Phone screen", company: "Acme", role: "Backend Engineer", job_id: 4 };
const deadline: ComingUpItem = { kind: "deadline", date: "2026-10-29", when: "2026-10-29", label: "Apply by", company: "Beta", role: "Data Analyst", job_id: 5 };
const offer: ComingUpItem = { kind: "offer", date: "2026-11-02", when: "2026-11-02", label: "Reply to the offer by", company: "Gamma", role: "SRE", job_id: 6 };

describe("coming up helpers", () => {
  it("lead each item to the right screen", () => {
    expect(comingUpTo(interview)).toBe("/interviews");
    expect(comingUpTo(deadline)).toBe("/jobs/5/apply");
    expect(comingUpTo(offer)).toBe("/offers");
  });
  it("say a plain word and a day or time for each kind", () => {
    expect(comingUpText(interview)).toBe("Interview · Tue 27 Oct, 14:30 · Phone screen: Acme, Backend Engineer");
    expect(comingUpText(deadline)).toBe("Apply by · 29 Oct: Beta, Data Analyst");
    expect(comingUpText(offer)).toBe("Reply to offer · 2 Nov: Gamma, SRE");
    expect(comingUpWhen(deadline)).toBe("29 Oct");
  });
  it("turn an answer that only has interviews into the same shape", () => {
    const items = comingUpItems({ upcoming_interviews: [{ id: 1, when: interview.when, kind: "Phone screen", company: "Acme", role: "Backend Engineer", job_id: 4 }] });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ kind: "interview", label: "Phone screen", job_id: 4 });
    expect(comingUpItems({ coming_up: [deadline], upcoming_interviews: [] })).toEqual([deadline]);
  });
  it("offer the all-interviews and all-offers links only when such items are there", () => {
    expect(comingUpAllLinks([deadline])).toEqual([]);
    expect(comingUpAllLinks([interview, offer]).map((l) => l.to)).toEqual(["/interviews", "/offers"]);
  });
});

describe("ComingUpBody", () => {
  it("lists the mixed items in order, each as a link to where it belongs", () => {
    render(<ComingUpBody items={[interview, deadline, offer]} />);
    const list = screen.getAllByRole("listitem");
    expect(list).toHaveLength(3);
    const hrefs = list.map((li) => within(li).getByRole("link").getAttribute("href"));
    expect(hrefs).toEqual(["/app/interviews", "/app/jobs/5/apply", "/app/offers"]);
    expect(within(list[1]).getByRole("link").textContent).toContain("Apply by");
    expect(screen.getByRole("link", { name: "All interviews" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "All offers" })).toBeTruthy();
  });
  it("shows no all-interviews link when there is only a deadline", () => {
    render(<ComingUpBody items={[deadline]} />);
    expect(screen.queryByRole("link", { name: "All interviews" })).toBeNull();
  });
});
