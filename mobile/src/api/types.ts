export interface Me {
  id: number;
  name: string;
  email: string;
  is_staff: boolean;
  greeting: string;
  site_title: string;
}

export interface Band {
  label: string;
  color: string;
}

export interface JobCard {
  id: number;
  company: string;
  role: string;
  url: string;
  status_id: number;
  bucket_key: string;
  percent: number | null;
  band: Band | null;
  location: string;
  country_name: string;
  arrangement: string;
  advertised_pay: string;
  applied_date: string | null;
  deadline: string | null;
  days_left: number | null;
  urgent: boolean;
  overdue: boolean;
  live_state: string;
  fit_level: string;
  fit_text: string;
  fit_badge: "check" | "fits" | "unknown" | null;
  has_cv: boolean;
  cv: { id: number; label: string; flagged: boolean; approved: boolean } | null;
  next_action: string;
  notes: string;
  ai_summary: string | null;
  has_description: boolean;
}

export interface Bucket {
  key: string;
  label: string;
  description: string;
  is_closed: boolean;
}

export interface JobStatus {
  id: number;
  name: string;
  label: string;
  bucket_key: string;
  color: string;
  counts_as_applied: boolean;
}

export interface WorthALookItem {
  kind: string;
  title: string;
  subtitle: string;
  job_id?: number;
}

export interface Dashboard {
  greeting: string;
  buckets: Bucket[];
  statuses: JobStatus[];
  jobs: JobCard[];
  stats: { total: number; submitted: number; average_match: number | null; urgent: number };
  worth_a_look: WorthALookItem[];
  next_step: { title: string; body: string; cta?: string } | null;
  has_areas: boolean;
}

export interface CvSummary {
  id: number;
  label: string;
  kind: "master" | "tailored";
  kind_label: string;
  source: string;
  source_label: string;
  created_at: string;
  job: { id: number; role: string; company: string } | null;
  flagged: boolean;
  flagged_count: number;
  approved: boolean;
  exportable: boolean;
  current?: boolean;
}

export interface CvDetail extends CvSummary {
  content: string;
  check_report: { kind: "number" | "name" | "job-term"; text: string; line: number }[];
  approved_at: string | null;
  downloads: { docx: string; md: string; print: string } | null;
}

export interface CvList {
  masters: CvSummary[];
  tailored: CvSummary[];
}
