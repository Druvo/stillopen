import { request } from "@/lib/api";

export type Prefill = { ok: true; url: string; role: string; company: string; description: string };
export type Check = { level: "ok" | "warn" | "info"; text: string };
export type Option = { value: string; label: string };

export type JobDetails = {
  id: number;
  company: string;
  role: string;
  values: Record<string, string>;
  details_source: "" | "detected" | "manual";
  options: Record<"arrangement" | "sponsorship" | "relocation" | "employment_type" | "seniority", Option[]>;
  fit: Check[];
};

export type PostingRow = {
  id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  source: { id: number; name: string; connector: string };
  first_seen: string;
  last_seen: string;
  repost: { distinct_urls: number; distinct_dates: number } | null;
  apply_address: string;
  tracked: boolean;
  job_id: number | null;
};
export type PostingPage = {
  total: number;
  page: number;
  pages: number;
  sources: { id: number; name: string; connector: string }[];
  limit_message: string;
  postings: PostingRow[];
};

export type DocumentRow = { id: number; title: string; kind: string; kind_label: string; enabled: boolean; characters: number; passages: number; updated: string };
export type Documents = {
  sources: DocumentRow[];
  cv: { present: boolean; characters: number };
  limits: { max_documents: number; max_file_bytes: number; max_text_characters: number };
  kinds: Option[];
  can_push_to_paperless: boolean;
};

export type CvChoice = { id: number; label: string; kind: string; kind_label: string; created: string; flagged: boolean; docx_url: string; print_url: string };
export type ApplyData = {
  job: { id: number; company: string; role: string; url: string; closed: boolean; applied: boolean; applied_date: string; channel: string; note: string; follow_up_date: string };
  checks: Check[];
  versions: CvChoice[];
  selected: number | null;
  has_flagged: boolean;
  cover_letters: { id: number; created: string; needs_review: boolean }[];
  draft: { subject: string; body: string };
  channels: Option[];
  followup_days: number;
  max_followup_days: number;
};
export type RecordInput = { cv: number | null; channel: string; note: string; days: number | null; applied_on: string | null; confirm_closed: boolean };

export const jobsApi = {
  quickAdd: (url: string) => request<Prefill>("POST", "/quickadd", { url }),
  addJob: (values: Record<string, string>) => request<{ id: number; company: string; role: string }>("POST", "/jobs", values),
  details: (id: number) => request<JobDetails>("GET", `/jobs/${id}/details`),
  saveDetails: (id: number, values: Record<string, string>) => request<JobDetails>("PUT", `/jobs/${id}/details`, values),
  redetect: (id: number) => request<JobDetails & { changed: string[] }>("POST", `/jobs/${id}/redetect`),
  translate: (id: number) => request<{ translated: string }>("POST", `/jobs/${id}/translate`),
  postings: (query: string) => request<PostingPage>("GET", `/postings${query}`),
  addPosting: (id: number) => request<{ id: number; created: boolean; company: string; role: string }>("POST", `/postings/${id}/add`),
  documents: () => request<Documents>("GET", "/documents"),
  addDocument: (form: FormData) => request<DocumentRow>("POST", "/documents", form),
  toggleDocument: (id: number) => request<{ ok: true; enabled: boolean }>("POST", `/documents/${id}/toggle`),
  deleteDocument: (id: number) => request<{ ok: true }>("DELETE", `/documents/${id}`),
  apply: (id: number) => request<ApplyData>("GET", `/jobs/${id}/apply`),
  record: (id: number, input: RecordInput) => request<{ ok: true; follow_up_date: string }>("POST", `/jobs/${id}/applied`, input),
};
