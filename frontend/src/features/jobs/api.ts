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
  credit?: { label: string; url: string } | null;
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
  credit?: { label: string; url: string } | null;
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

/** A job the person already tracks that matches one they are adding. */
export type Duplicate = { id: number; company: string; role: string; status: string };
export type Prefilled = Prefill & {
  duplicate?: Duplicate | null;
  /** Set when the link is on a site that does not let other apps read its pages ("linkedin", "indeed", "glassdoor"...): nothing was fetched. */
  blocked_host?: string;
  message?: string;
};

export type RemovePreview = { counts: Record<string, number>; text: string; keeps: string; company?: string; role?: string };
export type HistoryItem = { id: number; at: string; date: string; kind: string; kind_label: string; text: string };
export type HistoryData = { items: HistoryItem[]; capped: boolean };
export type StatusChoice = { id: number; name: string; label: string; bucket_key: string };

export type ImportRow = { row: number; file?: string; company: string; role: string; link: string; status: string };
export type ImportFile = { name: string; kind: "saved" | "applied"; label: string; found: number; new: number; duplicates: number; unreadable: number };

export type EmailRow = {
  index: number;
  title: string;
  company: string;
  location: string;
  salary: string;
  url: string;
  problems: string[];
  duplicate: Duplicate | null;
  importable: boolean;
};
export type EmailPreview = { preview: true; found: number; will_add: number; rows: EmailRow[]; problems: string[] };
export type EmailDone = {
  preview: false;
  added: number;
  skipped_count: number;
  skipped: { title: string; company: string; reason: string }[];
  stopped: string;
  found: number;
  problems: string[];
};
export type EmailInput = { text: string; file: File | null };
export type ImportReport = {
  preview: boolean;
  columns: string[];
  rows_read: number;
  will_add: number;
  added?: number;
  skipped_count: number;
  problem_count: number;
  skipped: { row: number; company: string; role: string; reason: string }[];
  problems: { row: number; message: string }[];
  warnings: string[];
  stopped: string;
  rows: ImportRow[];
  /** Only for LinkedIn's own data export: counts per file, how many other files were ignored, and the privacy line. */
  source?: "linkedin";
  files?: ImportFile[];
  ignored_files?: number;
  privacy?: string;
};

export type ReplySuggestion = { status: StatusChoice; confidence: "clear" | "probably" | "unsure"; quotes: string[]; mixed: boolean; already: boolean };
export type ReplyReading = { suggestion: ReplySuggestion | null; truncated: boolean; message: string };

/** What an interview or an offer that was just saved suggests: the status the job could move to (never moved by itself). */
export type SuggestedStatus = { id: number; name: string; label: string } | null;

export const jobsApi = {
  quickAdd: (url: string) => request<Prefilled>("POST", "/quickadd", { url }),
  addJob: (values: Record<string, string>, allowDuplicate = false) =>
    request<{ id: number; company: string; role: string }>("POST", "/jobs", allowDuplicate ? { ...values, allow_duplicate: true } : values),
  details: (id: number) => request<JobDetails>("GET", `/jobs/${id}/details`),
  saveDetails: (id: number, values: Record<string, string>) => request<JobDetails>("PUT", `/jobs/${id}/details`, values),
  redetect: (id: number) => request<JobDetails & { changed: string[] }>("POST", `/jobs/${id}/redetect`),
  translate: (id: number) => request<{ translated: string }>("POST", `/jobs/${id}/translate`),
  postings: (query: string) => request<PostingPage>("GET", `/postings${query}`),
  addPosting: (id: number, allowDuplicate = false) =>
    request<{ id: number; created: boolean; company: string; role: string }>("POST", `/postings/${id}/add`, allowDuplicate ? { allow_duplicate: true } : {}),
  documents: () => request<Documents>("GET", "/documents"),
  addDocument: (form: FormData) => request<DocumentRow>("POST", "/documents", form),
  toggleDocument: (id: number) => request<{ ok: true; enabled: boolean }>("POST", `/documents/${id}/toggle`),
  deleteDocument: (id: number) => request<{ ok: true }>("DELETE", `/documents/${id}`),
  apply: (id: number) => request<ApplyData>("GET", `/jobs/${id}/apply`),
  removePreview: (id: number) => request<RemovePreview>("GET", `/jobs/${id}/remove-preview`),
  removeJob: (id: number) => request<{ ok: true; removed: number }>("DELETE", `/jobs/${id}`),
  bulkPreview: (ids: number[]) => request<RemovePreview>("POST", "/jobs/bulk", { ids, action: "preview" }),
  bulkRemove: (ids: number[]) => request<{ ok: true; removed: number }>("POST", "/jobs/bulk", { ids, action: "remove" }),
  bulkStatus: (ids: number[], statusId: number) =>
    request<{ ok: true; changed: number[]; status: StatusChoice }>("POST", "/jobs/bulk", { ids, action: "status", status_id: statusId }),
  bulkUndo: (ids: number[]) => request<{ ok: true; undone: number[] }>("POST", "/jobs/bulk", { ids, action: "undo" }),
  undoStatus: (id: number) => request<{ ok: true; status: StatusChoice }>("POST", `/jobs/${id}/status/undo`),
  history: (id: number) => request<HistoryData>("GET", `/jobs/${id}/history`),
  importCsv: (file: File, preview: boolean) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportReport>("POST", `/jobs/import${preview ? "?preview=1" : ""}`, form);
  },
  importEmail: <T extends EmailPreview | EmailDone>(input: EmailInput, preview: boolean, selected?: number[]) => {
    const query = preview ? "?preview=1" : "";
    if (input.file) {
      const form = new FormData();
      form.append("file", input.file);
      if (selected) form.append("selected", selected.join(","));
      return request<T>("POST", `/jobs/import-email${query}`, form);
    }
    return request<T>("POST", `/jobs/import-email${query}`, selected ? { text: input.text, selected } : { text: input.text });
  },
  replyParse: (id: number, text: string) => request<ReplyReading>("POST", `/jobs/${id}/reply-parse`, { text }),
  record: (id: number, input: RecordInput) => request<{ ok: true; follow_up_date: string }>("POST", `/jobs/${id}/applied`, input),
};
