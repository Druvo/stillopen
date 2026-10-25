import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job, ScanStatus } from "@/lib/types";
import { FilterBar } from "./filters";
import { DEFAULT_FILTERS } from "./logic";
import { NextStepCard, ScanCard, StatTiles } from "./panels";

afterEach(cleanup);

const scan = (over: Partial<ScanStatus>): ScanStatus => ({
  running: false, done: 0, total: 0, error: "", found: 0, added: 0, note: "", started_at: null, finished_at: null, phase: "done", entries: [], ...over,
});

describe("the search card", () => {
  it("shows progress, the hint and the source log while a search runs", () => {
    render(
      <ScanCard
        starting={false}
        scan={scan({
          running: true, phase: "reading", done: 2, total: 5, note: "Only the best were added",
          entries: [
            { source: "Acme", connector: "Greenhouse", found: 5, matched: 3, added: 2, duplicates: 1, outside: 1, error: "" },
            { source: "Broken", connector: "Lever", found: 0, matched: 0, added: 0, duplicates: 0, outside: 0, error: "HTTP 500" },
          ],
        })}
      />,
    );
    expect(screen.getByText("Reading job sources… 2/5")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Search progress" }).getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByText(/Usually about a minute/)).toBeTruthy();
    expect(screen.getByText("Only the best were added")).toBeTruthy();
    expect(screen.getByText("5 found, 3 matched, 2 new, 1 already tracked, 1 outside your areas")).toBeTruthy();
    expect(screen.getByText("HTTP 500").className).toContain("text-bad");
  });

  it("shows only the last result, without a bar, once it is done", () => {
    render(<ScanCard starting={false} scan={scan({ found: 10, added: 2, started_at: new Date().toISOString() })} />);
    expect(screen.getByText(/looked through 10 openings, 2 new for you/)).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("No sources checked yet.")).toBeTruthy();
  });

  it("is not there before any search, and appears the moment one is started", () => {
    const { container, rerender } = render(<ScanCard starting={false} scan={null} />);
    expect(container.textContent).toBe("");
    rerender(<ScanCard starting scan={null} />);
    expect(screen.getByText("Starting the search…")).toBeTruthy();
  });
});

describe("the next step", () => {
  it("scrolls to a card instead of leaving the page", () => {
    const onCard = vi.fn();
    render(<NextStepCard step={{ headline: "See how well Acme fits you", body: "Press it.", label: "Take me there", url: "#job-4" }} onCard={onCard} />);
    expect(screen.getByText("YOUR NEXT STEP")).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "Take me there" }));
    expect(onCard).toHaveBeenCalledWith("job-4");
  });

  it("uses the app's own address for a link into the app", () => {
    render(<NextStepCard step={{ headline: "h", body: "b", label: "Add places", url: "/app/profile#areas" }} onCard={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Add places" }).getAttribute("href")).toBe("/app/profile#areas");
  });

  it("has no button when there is nothing to press", () => {
    render(<NextStepCard step={{ headline: "We are searching", body: "b", label: "", url: "" }} onCard={vi.fn()} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("the tiles", () => {
  it("says what to do when there is no average yet, and names the urgent window", () => {
    render(<StatTiles data={{ stats: { total: 3, submitted: 1, average_match: null, urgent: 2 }, urgent_days: 5 }} />);
    expect(screen.getByText("Average fit (check a job first)")).toBeTruthy();
    expect(screen.getByText("Closing within 5 days")).toBeTruthy();
  });

  it("shows nothing for an empty tracker", () => {
    const { container } = render(<StatTiles data={{ stats: { total: 0, submitted: 0, average_match: null, urgent: 0 }, urgent_days: 5 }} />);
    expect(container.textContent).toBe("");
  });
});

describe("the filter bar", () => {
  const jobs = [{ id: 1, bucket_key: "new", country: "MY", country_name: "Malaysia" }, { id: 2, bucket_key: "active", country: "", country_name: "" }] as Job[];
  const buckets = [
    { key: "new", label: "New", description: "Just found", is_closed: false },
    { key: "active", label: "Active", description: "", is_closed: false },
  ];

  it("has every classic control, the chips with counts, and the count line", () => {
    render(<FilterBar filters={DEFAULT_FILTERS} set={vi.fn()} reset={vi.fn()} jobs={jobs} buckets={buckets} bandLabels={["Strong", "A stretch"]} shown={2} />);
    expect(screen.getByRole("button", { name: "All (2)" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "New (1)" })).toBeTruthy();
    for (const label of ["Search", "Fits your places", "How well you match", "Work", "Country", "Posting", "Found", "Sort by"]) expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.getByText("Showing all 2")).toBeTruthy();
    expect(screen.queryByText("Clear filters")).toBeNull();
    expect(screen.getByRole("option", { name: "Not checked yet" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Malaysia" })).toBeTruthy();
  });

  it("reports changes, and offers to clear them once something is set", () => {
    const set = vi.fn();
    const reset = vi.fn();
    render(<FilterBar filters={{ ...DEFAULT_FILTERS, stage: "new" }} set={set} reset={reset} jobs={jobs} buckets={buckets} bandLabels={[]} shown={1} />);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Active (1)" }));
    expect(set).toHaveBeenCalledWith({ stage: "active" });
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "oldest" } });
    expect(set).toHaveBeenCalledWith({ sort: "oldest" });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(reset).toHaveBeenCalled();
  });
});
