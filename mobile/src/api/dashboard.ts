// The Home tab's API calls and shapes (mirrors frontend/src/lib/types.ts and features/dashboard/api.ts).
import { api } from "./client";

export type Bucket = { key: string; label: string; description: string; is_closed: boolean };
export type StatusInfo = { id: number; name: string; label?: string; bucket_key: string; color: string; counts_as_applied: boolean };
export type Repost = { distinct_urls: number; distinct_dates: number; first_seen: string; last_seen: string };
export type CvBadge = { id: number; label: string; flagged: boolean; approved: boolean };
export type TechSkill = { name: string; hot: boolean; have: boolean };
export type JobDocument = { id: number; kind: string; title: string; paperless_id: number | null; paperless_error: string };

export type Job = {
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
  country: string;
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
  live_state: "unknown" | "active" | "expired" | "uncertain";
  live_detail: string;
  strengths: string[];
  gaps: string[];
  fit_level: string;
  fit_text: string;
  fit_badge: "fits" | "check" | "unknown" | null;
  has_cv: boolean;
  cv: CvBadge | null;
  repost: Repost | null;
  apply_address: string;
  skill_matched: boolean;
  credit?: { label: string; url: string } | null;
  tech_skills: TechSkill[];
  evaluated: boolean;
  ai_evaluated: boolean;
  ai_method: string;
  has_description: boolean;
  documents: JobDocument[];
  prep?: { id: number; percent: number } | null;
};

export type ArchivedJob = { id: number; company: string; role: string; status: string; archived_at: string | null; url: string };
export type NextStep = { headline: string; body: string; label: string; url: string };
export type Progress = { running: boolean; done: number; total: number; error: string; found?: number; added?: number };
export type ScanEntry = { source: string; connector: string; found: number; matched: number; added: number; duplicates: number; outside: number; error: string };
export type ScanStatus = Progress & {
  found: number;
  added: number;
  note: string;
  started_at: string | null;
  finished_at: string | null;
  phase: "reading" | "sorting" | "done";
  entries_count: number;
};
export type ScanLog = ScanStatus & { entries: ScanEntry[] };
export type Followup = { id: number; company: string; role: string; follow_up_date: string; applied_date: string | null };
export type WorthItem = { kind: "interview" | "offer" | "followup" | "draft" | "quiet"; job_id: number; label: string; reason: string; version_id?: number };
export type ComingUpItem = { kind: "interview" | "deadline" | "offer"; date: string; when: string; label: string; company: string; role: string; job_id: number };
export type UpcomingInterview = { id: number; when: string; kind: string; company: string; role: string; job_id: number };
export type DraftWaiting = { id: number; job_id: number; company: string; role: string; flagged_count: number; created_at: string | null };
export type SearchSummary = {
  roles: string[];
  places: { place: string; mode: string }[];
  remote: string;
  salary_floor: string;
  alerts_on: boolean;
  alerts_available: boolean;
  has_cv: boolean;
  ai: string;
};

export type Dashboard = {
  greeting: string;
  buckets: Bucket[];
  statuses: StatusInfo[];
  band_labels: string[];
  jobs: Job[];
  archived?: ArchivedJob[];
  stats: { total: number; submitted: number; average_match: number | null; urgent: number };
  followups: Followup[];
  upcoming_interviews: UpcomingInterview[];
  coming_up?: ComingUpItem[];
  worth_a_look?: WorthItem[];
  drafts?: DraftWaiting[];
  next_step: NextStep | null;
  can_scan: boolean;
  checked_at: string | null;
  has_areas: boolean;
  urgent_days: number;
  prep_enabled: boolean;
  judge_label: string;
  scan: ScanStatus | null;
  search_summary: SearchSummary;
  ai_prompt: { show: boolean };
  source_trouble?: { total: number; trouble: number } | null;
};

export type ViewMode = "list" | "board";
export type SortKey = "best" | "newest" | "oldest" | "company" | "deadline";
export type PrefFilters = { fit: string; match: string; work: string; country: string; posting: string; found: string };
export type Preferences = {
  view: ViewMode;
  tab: string;
  sort: SortKey;
  filters_open: boolean;
  ai_prompt_dismissed: boolean;
  tz_prompt_dismissed: boolean;
  checklist_dismissed: boolean;
  hide_weak: boolean;
  filters: PrefFilters;
  goal_daily: number;
  goal_weekly: number;
  [key: string]: unknown;
};
export type PreferencePatch = Partial<Preferences>;

export const DEFAULT_PREFS: Preferences = {
  view: "list",
  tab: "all",
  sort: "best",
  filters_open: false,
  ai_prompt_dismissed: false,
  tz_prompt_dismissed: false,
  checklist_dismissed: false,
  hide_weak: false,
  filters: { fit: "", match: "", work: "", country: "", posting: "", found: "" },
  goal_daily: 0,
  goal_weekly: 0,
};

export type ZoneInfo = { timezone: string; site_timezone: string };
export type Goals = { daily_target: number; weekly_target: number; today: number; week: number; current_streak: number; best_streak: number; explain?: string };
export type FunnelStage = { key: string; label: string; count: number };
export type DashStats = {
  has_jobs?: boolean;
  goals?: Goals | null;
  funnel?: Record<"30" | "90" | "all", { since: string | null; stages: FunnelStage[] }>;
  week?: { found: number; checked: number; applied: number };
  waiting?: { count: number };
  summary_text?: string;
};
export type StatusChoice = { id: number; name: string; label: string; bucket_key: string };
export type RemovePreview = { counts: Record<string, number>; text: string; keeps: string };

export const getDashboard = () => api.get<Dashboard>("/api/v1/dashboard");
export const getPreferences = () => api.get<Preferences>("/api/v1/preferences");
export const putPreferences = (patch: PreferencePatch) => api.put<Preferences>("/api/v1/preferences", patch);
export const getZones = () => api.get<ZoneInfo>("/api/v1/me");
export const saveTimezone = (timezone: string) => api.put<unknown>("/api/v1/profile", { timezone });
export const getDashStats = () => api.get<DashStats>("/api/v1/stats");

export const scanStatus = () => api.get<ScanStatus>("/api/v1/scan/status");
export const scanLog = () => api.get<ScanLog>("/api/v1/scan/status?log=1");
export const startScan = () => api.post<ScanStatus>("/api/v1/scan");
export const livenessStatus = () => api.get<Progress>("/api/v1/liveness/status");
export const startLiveness = () => api.post<Progress>("/api/v1/liveness");

export const followupDone = (jobId: number) => api.post<{ ok: true }>(`/api/v1/jobs/${jobId}/followup/done`);
export const followupSnooze = (jobId: number, days = 3) => api.post<{ ok: true; follow_up_date: string }>(`/api/v1/jobs/${jobId}/followup/snooze`, { days });
export const discardDraft = (cvId: number) => api.delete<{ ok: true }>(`/api/v1/cv/${cvId}`);

export const setStatus = (jobId: number, statusId: number, note = "") =>
  api.patch<{ ok: boolean; changed: boolean; status_id: number; status: string; label: string; bucket_key: string }>(`/api/v1/jobs/${jobId}/status`, { status: statusId, note });
export const undoStatus = (id: number) => api.post<{ ok: true; status: StatusChoice }>(`/api/v1/jobs/${id}/status/undo`);
export const evaluate = (jobId: number) => api.post<{ ok: true; match_percent: number | null; method: string }>(`/api/v1/jobs/${jobId}/evaluate`);
export const tailorCv = (jobId: number) => api.post<{ id: number }>(`/api/v1/jobs/${jobId}/tailor`, { mode: "auto" });
export const createPrep = (jobId: number) => api.post<{ id: number; existing: boolean }>(`/api/v1/jobs/${jobId}/prep`, {});

export const archiveJob = (id: number) => api.post<{ ok: true; archived: number[] }>(`/api/v1/jobs/${id}/archive`);
export const restoreJob = (id: number) => api.post<{ ok: true; restored: number[] }>(`/api/v1/jobs/${id}/restore`);
export const bulkArchive = (ids: number[]) => api.post<{ ok: true; archived: number[] }>("/api/v1/jobs/bulk", { ids, action: "archive" });
export const bulkStatus = (ids: number[], statusId: number) =>
  api.post<{ ok: true; changed: number[]; status: StatusChoice }>("/api/v1/jobs/bulk", { ids, action: "status", status_id: statusId });
export const bulkUndo = (ids: number[]) => api.post<{ ok: true; undone: number[] }>("/api/v1/jobs/bulk", { ids, action: "undo" });
export const removePreview = (id: number) => api.get<RemovePreview>(`/api/v1/jobs/${id}/remove-preview`);
export const bulkPreview = (ids: number[]) => api.post<RemovePreview>("/api/v1/jobs/bulk", { ids, action: "preview" });
export const removeJob = (id: number) => api.delete<{ ok: true; removed: number }>(`/api/v1/jobs/${id}`);
export const bulkRemove = (ids: number[]) => api.post<{ ok: true; removed: number }>("/api/v1/jobs/bulk", { ids, action: "remove" });
