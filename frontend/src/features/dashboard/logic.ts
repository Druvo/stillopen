import type { Bucket, Dashboard, Job, StatusInfo } from "@/lib/types";

/** The status a card gets when it is dropped on a column: the column's first status, in the order the admin set. */
export function statusForColumn(statuses: StatusInfo[], bucketKey: string): StatusInfo | undefined {
  return statuses.find((s) => s.bucket_key === bucketKey);
}

/** Move a job in a cached dashboard without waiting for the server (the caller rolls back if the server refuses). */
export function applyMove(data: Dashboard, jobId: number, status: StatusInfo): Dashboard {
  return {
    ...data,
    jobs: data.jobs.map((j) => (j.id === jobId ? { ...j, status_id: status.id, bucket_key: status.bucket_key } : j)),
  };
}

export type Sort = "best" | "newest" | "deadline" | "company";

export type Filters = { text: string; sort: Sort };

const SORTS: Record<Sort, (a: Job, b: Job) => number> = {
  best: (a, b) => Number(b.urgent) - Number(a.urgent) || (b.percent ?? -1) - (a.percent ?? -1),
  newest: (a, b) => b.found_date.localeCompare(a.found_date),
  deadline: (a, b) => (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999"),
  company: (a, b) => a.company.localeCompare(b.company),
};

export function visibleJobs(jobs: Job[], { text, sort }: Filters): Job[] {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (job: Job) => {
    const haystack = `${job.company} ${job.role} ${job.location} ${job.country_name} ${job.summary}`.toLowerCase();
    return words.every((w) => haystack.includes(w));
  };
  return jobs.filter(matches).sort(SORTS[sort]);
}

export function jobsByBucket(jobs: Job[], buckets: Bucket[]): Record<string, Job[]> {
  const out: Record<string, Job[]> = Object.fromEntries(buckets.map((b) => [b.key, []]));
  for (const job of jobs) (out[job.bucket_key] ??= []).push(job);
  return out;
}
