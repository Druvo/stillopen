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

/**
 * A search run: progress plus the plain note. `phase` is "reading" while sources are read, "sorting" at the end, then "done".
 * The per-source log is not part of it (it can be long): `entries_count` says how many sources there were, and `ScanLog` is fetched on demand.
 */
export type ScanStatus = Progress & {
  found: number;
  added: number;
  note: string;
  started_at: string | null;
  finished_at: string | null;
  phase: "reading" | "sorting" | "done";
  entries_count: number;
};

/** `GET /scan/status?log=1`: the run plus what each source gave. */
export type ScanLog = ScanStatus & { entries: ScanEntry[] };

export type Followup = { id: number; company: string; role: string; follow_up_date: string; applied_date: string | null };

export type UpcomingInterview = { id: number; when: string; kind: string; company: string; role: string; job_id: number };

/** What drives the matches, for the dashboard's "Your search" card. */
export type SearchSummary = {
  roles: string[];
  places: { place: string; mode: string }[];
  remote: string;
  /** The person's own words ("100,000 BDT/month"), or "" when not set. */
  salary_floor: string;
  alerts_on: boolean;
  alerts_available: boolean;
  has_cv: boolean;
  /** "keyword" or a readable provider name. */
  ai: string;
};

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
  search_summary: SearchSummary;
  /** Show the card asking, first of all, for a Google AI Studio key (nothing but the free keyword check is set up, and not dismissed). */
  ai_prompt: { show: boolean };
};

// ---- per-person preferences, saved on the server (GET/PUT /preferences, also inside /me) ----------------------------------

export type ViewMode = "list" | "board";
export type SortKey = "best" | "newest" | "oldest" | "company" | "deadline";
export type TextSize = "normal" | "large" | "larger";
export type Density = "comfortable" | "compact";
export type Theme = "light" | "dark";

/** The six saved filters; "" is "any". */
export type PrefFilters = { fit: string; match: string; work: string; country: string; posting: string; found: string };

export type Preferences = {
  view: ViewMode;
  /** "all" or a stage (bucket) key. */
  tab: string;
  sort: SortKey;
  filters_open: boolean;
  /** The person said "not now" to the card asking for a Google AI Studio key. */
  ai_prompt_dismissed: boolean;
  filters: PrefFilters;
  sidebar: "expanded" | "collapsed";
  theme: Theme;
  text_size: TextSize;
  density: Density;
};

/** Any subset; `filters` is replaced as a whole. */
export type PreferencePatch = Partial<Preferences>;

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
  writing_check_enabled: boolean;
  translate_enabled: boolean;
  email_unverified_signups: boolean;
  legal_has_blanks: boolean;
  jooble_sources_dormant: boolean;
  preferences: Preferences;
  usajobs_sources_dormant: boolean;
};
