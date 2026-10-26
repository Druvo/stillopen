// Shapes returned by /api/v1/. Written by hand for now; the API returns plain dicts, so there is nothing to generate from yet.

export type Bucket = { key: string; label: string; description: string; is_closed: boolean };

export type StatusInfo = { id: number; name: string; bucket_key: string; color: string; counts_as_applied: boolean };

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
  skill_matched: boolean;
  tech_skills: TechSkill[];
  evaluated: boolean;
  ai_evaluated: boolean;
  ai_method: string;
  has_description: boolean;
  documents: JobDocument[];
};

export type NextStep = { headline: string; body: string; label: string; url: string };

export type ScanEntry = { source: string; connector: string; found: number; matched: number; added: number; duplicates: number; outside: number; error: string };

export type Progress = { running: boolean; done: number; total: number; error: string; found?: number; added?: number };

/** A search run: progress plus the plain note and what each source gave. `phase` is "reading" while sources are read, "sorting" at the end, then "done". */
export type ScanStatus = Progress & {
  found: number;
  added: number;
  note: string;
  started_at: string | null;
  finished_at: string | null;
  phase: "reading" | "sorting" | "done";
  entries: ScanEntry[];
};

export type Followup = { id: number; company: string; role: string; follow_up_date: string; applied_date: string | null };

export type UpcomingInterview = { id: number; when: string; kind: string; company: string; role: string; job_id: number };

export type Dashboard = {
  greeting: string;
  buckets: Bucket[];
  statuses: StatusInfo[];
  band_labels: string[];
  jobs: Job[];
  stats: { total: number; submitted: number; average_match: number | null; urgent: number };
  followups: Followup[];
  upcoming_interviews: UpcomingInterview[];
  next_step: NextStep | null;
  can_scan: boolean;
  checked_at: string | null;
  has_areas: boolean;
  urgent_days: number;
  prep_enabled: boolean;
  judge_label: string;
  paperless_on: boolean;
  paperless_url: string;
  can_import: boolean;
  scan: ScanStatus | null;
};

/** The signed-in person, from /me. The staff flags are false for everyone else. */
export type Me = {
  id: number;
  name: string;
  email: string;
  is_staff: boolean;
  greeting: string;
  site_title: string;
  prep_enabled: boolean;
  assistant_enabled: boolean;
  email_unverified_signups: boolean;
  legal_has_blanks: boolean;
  jooble_sources_dormant: boolean;
  usajobs_sources_dormant: boolean;
};
