// Shapes returned by /api/v1/. Written by hand for now; the API returns plain dicts, so there is nothing to generate from yet.

export type Bucket = { key: string; label: string; description: string; is_closed: boolean };

export type StatusInfo = { id: number; name: string; bucket_key: string; color: string; counts_as_applied: boolean };

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
  summary: string;
  location: string;
  country: string;
  country_name: string;
  arrangement: string;
  found_date: string;
  applied_date: string | null;
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
  has_cv: boolean;
  repost: boolean;
  skill_matched: boolean;
  evaluated: boolean;
  edit_url: string;
  apply_url: string;
  tailor_url: string;
  cover_url: string;
  prep_url: string;
};

export type NextStep = { headline: string; body: string; label: string; url: string };

export type Dashboard = {
  greeting: string;
  buckets: Bucket[];
  statuses: StatusInfo[];
  jobs: Job[];
  stats: { total: number; submitted: number; average_match: number | null; urgent: number };
  followups: { id: number; company: string; role: string; follow_up_date: string }[];
  next_step: NextStep | null;
  can_scan: boolean;
};

export type Progress = { running: boolean; done: number; total: number; error: string; found?: number; added?: number };
