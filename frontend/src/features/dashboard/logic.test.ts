import { describe, expect, it } from "vitest";
import type { Dashboard, Job, StatusInfo } from "@/lib/types";
import { applyMove, jobsByBucket, statusForColumn, visibleJobs } from "./logic";

const statuses: StatusInfo[] = [
  { id: 1, name: "Saved", bucket_key: "new", color: "#000", counts_as_applied: false },
  { id: 2, name: "Evaluated", bucket_key: "new", color: "#000", counts_as_applied: false },
  { id: 3, name: "Applied", bucket_key: "active", color: "#000", counts_as_applied: true },
];

function job(over: Partial<Job>): Job {
  return {
    id: 1, company: "Acme", role: "Dev", url: "", status_id: 1, bucket_key: "new", percent: null, band: null, decision: "", summary: "",
    location: "", country: "", country_name: "", arrangement: "", found_date: "2026-10-01", applied_date: null, deadline: null,
    days_left: null, urgent: false, overdue: false, live_state: "unknown", live_detail: "", strengths: [], gaps: [], fit_level: "",
    fit_text: "", has_cv: false, repost: false, skill_matched: false, evaluated: false, edit_url: "", apply_url: "", tailor_url: "",
    cover_url: "", prep_url: "", ...over,
  };
}

describe("board logic", () => {
  it("drops a card on the first status of the column", () => {
    expect(statusForColumn(statuses, "new")?.name).toBe("Saved");
    expect(statusForColumn(statuses, "active")?.name).toBe("Applied");
    expect(statusForColumn(statuses, "nowhere")).toBeUndefined();
  });

  it("moves only the dragged job, without touching the original data", () => {
    const data = { jobs: [job({ id: 1 }), job({ id: 2 })] } as Dashboard;
    const moved = applyMove(data, 2, statuses[2]);
    expect(moved.jobs.map((j) => [j.id, j.status_id, j.bucket_key])).toEqual([
      [1, 1, "new"],
      [2, 3, "active"],
    ]);
    expect(data.jobs[1].bucket_key).toBe("new");
  });

  it("searches every word across company, role and place", () => {
    const jobs = [job({ id: 1, company: "Acme", role: "Backend Engineer", country_name: "Malaysia" }), job({ id: 2, company: "Zed", role: "Designer" })];
    expect(visibleJobs(jobs, { text: "engineer malaysia", sort: "best" }).map((j) => j.id)).toEqual([1]);
    expect(visibleJobs(jobs, { text: "", sort: "company" }).map((j) => j.id)).toEqual([1, 2]);
  });

  it("sorts urgent first, then best match", () => {
    const jobs = [job({ id: 1, percent: 90 }), job({ id: 2, percent: 40, urgent: true }), job({ id: 3, percent: 60 })];
    expect(visibleJobs(jobs, { text: "", sort: "best" }).map((j) => j.id)).toEqual([2, 1, 3]);
  });

  it("groups by column and keeps empty columns", () => {
    const grouped = jobsByBucket([job({ id: 1, bucket_key: "new" })], [
      { key: "new", label: "New", description: "", is_closed: false },
      { key: "active", label: "Active", description: "", is_closed: false },
    ]);
    expect(grouped.new).toHaveLength(1);
    expect(grouped.active).toEqual([]);
  });
});
