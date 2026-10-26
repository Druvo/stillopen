import { request } from "@/lib/api";
import type { DiffRow, Finding } from "./logic";

export type JobRef = { id: number; role: string; company: string };
export type CvSummary = {
  id: number; label: string; kind: "master" | "tailored"; kind_label: string; source: string; source_label: string; provider: string; created_at: string;
  job: JobRef | null; flagged: boolean; flagged_count: number; approved: boolean; exportable: boolean; current?: boolean;
};
export type CvList = { masters: CvSummary[]; tailored: CvSummary[] };
export type CvDownloads = { docx: string; md: string; print: string };
export type CvDetail = CvSummary & {
  content: string; check_report: Finding[]; approved_at: string | null; job_snapshot: string; parent: { id: number; label: string } | null; children: number; downloads: CvDownloads | null;
};
export type CvDiff = { version: { id: number; label: string }; other: { id: number; label: string } | null; rows: DiffRow[]; choices: { id: number; label: string }[] };
export type Made = { id: number; flagged: boolean; flagged_count: number };
export type ExperienceIn = { company: string; role: string; start: string; end: string; bullets: string[] };
export type EducationIn = { school: string; degree: string; start: string; end: string };
export type ProjectIn = { name: string; description: string };
export type BuildCvIn = {
  full_name: string; email: string; phone: string; location: string; links: string[]; summary: string; skills: string[];
  experience: ExperienceIn[]; education: EducationIn[]; projects: ProjectIn[]; certifications: string[];
};
export type BuiltCv = { id: number; content: string };
export type Cover = {
  id: number; content: string; source: string; source_label: string; provider: string; updated_at: string; job: JobRef; flagged: boolean; flagged_count: number;
  check_report: Finding[]; approved: boolean; approved_at: string | null; exportable: boolean; downloads: { docx: string; txt: string } | null;
};
export type WritingMatch = { message: string; short_message: string; context: string; offset: number; length: number; category: string; suggestions: string[] };
export type WritingCheckResult = { matches: WritingMatch[] };

export const cvApi = {
  list: () => request<CvList>("GET", "/cv"),
  get: (id: number) => request<CvDetail>("GET", `/cv/${id}`),
  edit: (id: number, content: string, label: string) => request<{ id: number; changed: boolean }>("POST", `/cv/${id}/edit`, { content, label }),
  diff: (id: number, against?: number) => request<CvDiff>("GET", `/cv/${id}/diff${against ? `?against=${against}` : ""}`),
  approve: (id: number) => request<{ ok: true; exportable: boolean }>("POST", `/cv/${id}/approve`),
  restore: (id: number) => request<{ id: number }>("POST", `/cv/${id}/restore`),
  remove: (id: number) => request<{ ok: true }>("DELETE", `/cv/${id}`),
  tailor: (jobId: number) => request<Made>("POST", `/jobs/${jobId}/tailor`, { mode: "auto" }),
  build: (payload: BuildCvIn) => request<BuiltCv>("POST", "/cv/build", payload),
  writingCheck: (id: number) => request<WritingCheckResult>("POST", `/cv/${id}/writing-check`),
};

export const coverApi = {
  get: (id: number) => request<Cover>("GET", `/cover/${id}`),
  save: (id: number, content: string) => request<Cover>("POST", `/cover/${id}/save`, { content }),
  approve: (id: number) => request<{ ok: true; exportable: boolean }>("POST", `/cover/${id}/approve`),
  remove: (id: number) => request<{ ok: true }>("DELETE", `/cover/${id}`),
  write: (jobId: number) => request<Made>("POST", `/jobs/${jobId}/cover-letter`, { mode: "auto" }),
  writingCheck: (id: number) => request<WritingCheckResult>("POST", `/cover/${id}/writing-check`),
};
