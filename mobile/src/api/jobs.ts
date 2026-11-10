// Everything the job screens (detail, add, edit, apply, postings, saved searches, sources) ask the server. Mirrors
// frontend/src/features/jobs/api.ts and frontend/src/features/account/api.ts; paths are the website's own JSON API.
import { API_BASE, ApiError, api, getToken, setToken } from "./client";

const V1 = "/api/v1";

export type Option = { value: string; label: string };
export type Check = { level: "ok" | "warn" | "info"; text: string };
export type Duplicate = { id: number; company: string; role: string; status: string };

export type StatusInfo = { id: number; name: string; label: string; bucket_key: string; color: string; counts_as_applied: boolean };
export type BucketInfo = { key: string; label: string; description: string; is_closed: boolean };

export type TechSkill = { name: string; have: boolean; hot?: boolean };
export type JobFull = {
  id: number;
  company: string;
  role: string;
  url: string;
  status_id: number;
  bucket_key: string;
  percent: number | null;
  band: { label: string; color: string } | null;
  decision: string;
  risk: string;
  summary: string;
  next_action: string;
  notes: string;
  source: string;
  advertised_pay: string;
  location: string;
  country_name: string;
  arrangement: string;
  found_date: string;
  applied_date: string | null;
  applied_channel: string;
  applied_cv: { id: number; label: string } | null;
  follow_up_date: string | null;
  counts_as_applied: boolean;
  deadline: string | null;
  days_left: number | null;
  urgent: boolean;
  overdue: boolean;
  live_state: string;
  live_detail: string;
  strengths: string[];
  gaps: string[];
  fit_level: string;
  fit_text: string;
  has_cv: boolean;
  cv: { id: number; label: string; flagged: boolean; approved: boolean } | null;
  repost: { distinct_urls: number; distinct_dates: number } | null;
  apply_address: string;
  skill_matched: boolean;
  credit: { label: string; url: string } | null;
  tech_skills: TechSkill[];
  evaluated: boolean;
  ai_evaluated: boolean;
  ai_method: string;
  has_description: boolean;
  prep: { id: number; percent: number } | null;
  documents: { id: number; kind: string; title: string }[];
};
export type ArchivedJob = { id: number; company: string; role: string; status: string; archived_at: string | null; url: string };
export type DashboardForJobs = { statuses: StatusInfo[]; buckets: BucketInfo[]; jobs: JobFull[]; archived: ArchivedJob[] };

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

export type HistoryItem = { id: number; at: string; date: string; kind: string; kind_label: string; text: string };
export type HistoryData = { items: HistoryItem[]; capped: boolean };

export type MatchRow = {
  id: string;
  text: string;
  kind: string;
  state: "covered" | "gap" | "unchecked";
  source: { label: string; title: string; kind: string } | null;
  snippet: string;
  hint: string;
};
export type MatchCardData = {
  job_id: number;
  requirements: MatchRow[];
  covered: number;
  total: number;
  summary: string;
  has_material: boolean;
  method: "keywords" | "ai";
  can_ai: boolean;
  excerpt: boolean;
  empty: "" | "no_description" | "no_requirements" | "no_material";
};

export type PostingSummary = {
  method: "ai" | "rules";
  must_have: string[];
  nice_to_have: string[];
  seniority: string;
  pay: string;
  visa: string;
  relocation: string;
  remote: string;
  deadline: string;
  red_flags: { flag: string; quote: string }[];
  notice?: string;
};

export type CvChoice = { id: number; label: string; kind: string; kind_label: string; created: string; flagged: boolean };
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
  google: { available: boolean; connected: boolean; suggested_to: string; thread: boolean };
};
export type RecordInput = { cv: number | null; channel: string; note: string; days: number | null; applied_on: string | null; confirm_closed: boolean };

export type Prefilled = {
  ok: true;
  url: string;
  role: string;
  company: string;
  description: string;
  duplicate?: Duplicate | null;
  blocked_host?: string;
  message?: string;
};
export type ParsedFields = { company: string; role: string; location: string; pay: string; deadline: string; link: string };
export type ParsedPosting = { fields: ParsedFields; found: (keyof ParsedFields)[]; method: "rules" | "ai"; notice: string; message: string };

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
export type FitCheck = { match_percent: number; verdict: string; summary: string };
export type RemovePreview = { counts: Record<string, number>; text: string; keeps: string };

export type SourceHealth = { state: "ok" | "error" | "unknown"; checked_at: string | null; last_ok_at: string | null; error: string; since: string | null };
export type OwnSource = { id: number; name: string; connector: string; connector_label: string; board_token: string; enabled: boolean; host?: string; health?: SourceHealth };
export type SourcesData = {
  mine: OwnSource[];
  shared: string[];
  shared_health?: { name: string; health: SourceHealth }[];
  trouble?: { total: number; trouble: number } | null;
  limit: number;
  connectors: Option[];
  help: Record<string, string>;
};
export type AddSourceResult = { source: OwnSource | null; openings: number; message: string; info: string };
export type SavedSearch = { id: number; name: string; target_roles: string; enabled: boolean };

export type CoverageSearch = { name: string; connector: string; connector_label: string; ready: boolean; reason: "" | "needs_key" | "needs_roles" };
export type CoverageArea = {
  id: number;
  place: string;
  label: string;
  known: boolean;
  postings: number;
  boards: number;
  searches: CoverageSearch[];
  searches_ready: number;
  searches_waiting: number;
  level: "none" | "thin" | "ok" | "unknown";
  tip: string;
};
export type Coverage = { days: number; areas: CoverageArea[]; has_areas: boolean; empty_areas: number; keys: { jooble: boolean; adzuna: boolean } };

export type Progress = { running: boolean; done: number; total: number; error: string };

/**
 * A POST that may answer 409 "you already track this" with the job in the body. The shared client drops that body, so this one keeps it.
 * Any other failure throws the same `ApiError` the shared client does.
 */
async function postAllowingDuplicate<T>(path: string, body: unknown): Promise<{ ok: true; data: T } | { ok: false; duplicate: Duplicate }> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${V1}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await response.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (response.status === 409 && data?.duplicate && typeof data.duplicate.id === "number") {
    const d = data.duplicate;
    return { ok: false, duplicate: { id: d.id, company: String(d.company ?? ""), role: String(d.role ?? ""), status: String(d.status ?? "") } };
  }
  if (!response.ok) {
    if (response.status === 401) await setToken(null);
    throw new ApiError(response.status, (data && data.error) || `Request failed (${response.status})`, data && data.fields);
  }
  return { ok: true, data: data as T };
}

export const jobsApi = {
  dashboard: () => api.get<DashboardForJobs>(`${V1}/dashboard`),
  me: () => api.get<{ translate_enabled?: boolean; prep_enabled?: boolean }>(`${V1}/me`),
  setStatus: (id: number, statusId: number, note = "") =>
    api.patch<{ ok: boolean; changed: boolean; status_id: number; label: string; bucket_key: string }>(`${V1}/jobs/${id}/status`, { status: statusId, note }),
  undoStatus: (id: number) => api.post<{ ok: true; status: { id: number; label: string } }>(`${V1}/jobs/${id}/status/undo`),
  evaluate: (id: number) => api.post<{ ok: boolean; match_percent: number | null; method: string }>(`${V1}/jobs/${id}/evaluate`),
  details: (id: number) => api.get<JobDetails>(`${V1}/jobs/${id}/details`),
  saveDetails: (id: number, values: Record<string, string>) => api.put<JobDetails>(`${V1}/jobs/${id}/details`, values),
  redetect: (id: number) => api.post<JobDetails & { changed: string[] }>(`${V1}/jobs/${id}/redetect`),
  translate: (id: number) => api.post<{ translated: string }>(`${V1}/jobs/${id}/translate`),
  history: (id: number) => api.get<HistoryData>(`${V1}/jobs/${id}/history`),
  matchCard: (id: number) => api.get<MatchCardData>(`${V1}/jobs/${id}/match-card`),
  matchCardAi: (id: number) => api.post<MatchCardData>(`${V1}/jobs/${id}/match-card/ai`),
  addFact: (id: number, text: string) => api.post<{ added: boolean; message: string; card: MatchCardData }>(`${V1}/jobs/${id}/match-card/fact`, { text }),
  getSummary: (id: number) => api.get<{ summary: PostingSummary | null; ai: boolean }>(`${V1}/jobs/${id}/summary`),
  summarise: (id: number) => api.post<{ summary: PostingSummary; ai: boolean }>(`${V1}/jobs/${id}/summarise`),
  archive: (id: number) => api.post<{ ok: true }>(`${V1}/jobs/${id}/archive`),
  restore: (id: number) => api.post<{ ok: true }>(`${V1}/jobs/${id}/restore`),
  removePreview: (id: number) => api.get<RemovePreview>(`${V1}/jobs/${id}/remove-preview`),
  removeJob: (id: number) => api.delete<{ ok: true; removed: number }>(`${V1}/jobs/${id}`),
  followupDone: (id: number) => api.post<{ ok: true }>(`${V1}/jobs/${id}/followup/done`),
  followupSnooze: (id: number, days = 3) => api.post<{ ok: true; follow_up_date: string }>(`${V1}/jobs/${id}/followup/snooze`, { days }),
  startLiveness: () => api.post<Progress>(`${V1}/liveness`),
  livenessStatus: () => api.get<Progress>(`${V1}/liveness/status`),

  quickAdd: (url: string) => api.post<Prefilled>(`${V1}/quickadd`, { url }),
  parseText: (text: string) => api.post<ParsedPosting>(`${V1}/jobs/parse-text`, { text }),
  addJob: (values: Record<string, string>, allowDuplicate = false) =>
    postAllowingDuplicate<{ id: number; company: string; role: string }>("/jobs", allowDuplicate ? { ...values, allow_duplicate: true } : values),

  apply: (id: number) => api.get<ApplyData>(`${V1}/jobs/${id}/apply`),
  record: (id: number, input: RecordInput) => api.post<{ ok: true; follow_up_date: string }>(`${V1}/jobs/${id}/applied`, input),
  tailorCv: (id: number) => api.post<{ id: number }>(`${V1}/jobs/${id}/tailor`, { mode: "auto" }),
  writeCover: (id: number, tone?: string) => api.post<{ id: number }>(`${V1}/jobs/${id}/cover-letter`, tone ? { mode: "auto", tone } : { mode: "auto" }),

  postings: (query: string) => api.get<PostingPage>(`${V1}/postings${query}`),
  addPosting: (id: number, allowDuplicate = false) =>
    postAllowingDuplicate<{ id: number; created: boolean; company: string; role: string }>(`/postings/${id}/add`, allowDuplicate ? { allow_duplicate: true } : {}),
  checkPostingFit: (id: number) => api.post<FitCheck>(`${V1}/postings/${id}/fit-check`),
};

export const sourcesApi = {
  sources: () => api.get<SourcesData>(`${V1}/sources`),
  coverage: () => api.get<Coverage>(`${V1}/sources/coverage`),
  add: (values: { connector: string; board_token: string; name: string }) => api.post<AddSourceResult>(`${V1}/sources`, values),
  addCareerPage: (values: { url: string; name: string }) => api.post<AddSourceResult>(`${V1}/sources/careers-page`, values),
  toggle: (id: number) => api.post<{ source: OwnSource }>(`${V1}/sources/${id}/toggle`),
  remove: (id: number) => api.delete<{ ok: true }>(`${V1}/sources/${id}`),
  savedSearches: () => api.get<{ saved_searches: SavedSearch[] }>(`${V1}/saved-searches`),
  addSavedSearch: (values: { name: string; target_roles: string }) => api.post<SavedSearch>(`${V1}/saved-searches`, values),
  toggleSavedSearch: (id: number, enabled: boolean) => api.patch<SavedSearch>(`${V1}/saved-searches/${id}`, { enabled }),
  removeSavedSearch: (id: number) => api.delete<{ ok: true }>(`${V1}/saved-searches/${id}`),
};
