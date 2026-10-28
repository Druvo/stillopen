import { request } from "@/lib/api";
import type { DiffRow, Finding } from "./logic";
import type { BuilderAnswers } from "./quality";

export type JobRef = { id: number; role: string; company: string };
export type CvSummary = {
  id: number; label: string; kind: "master" | "tailored"; kind_label: string; source: string; source_label: string; provider: string; created_at: string;
  job: JobRef | null; flagged: boolean; flagged_count: number; approved: boolean; exportable: boolean; current?: boolean;
  /** 0 to 100, from the free ATS check of this version's text. */
  ats_readiness?: number;
};
export type CvList = { masters: CvSummary[]; tailored: CvSummary[] };
export type CvDownloads = { docx: string; md: string; print: string };
export type CvDetail = CvSummary & {
  content: string; check_report: Finding[]; approved_at: string | null; job_snapshot: string; parent: { id: number; label: string } | null; children: number; downloads: CvDownloads | null;
};
export type CvDiff = { version: { id: number; label: string }; other: { id: number; label: string } | null; rows: DiffRow[]; choices: { id: number; label: string }[] };
export type Made = { id: number; flagged: boolean; flagged_count: number };
export type Cover = {
  id: number; content: string; source: string; source_label: string; provider: string; updated_at: string; job: JobRef; flagged: boolean; flagged_count: number;
  check_report: Finding[]; approved: boolean; approved_at: string | null; exportable: boolean; downloads: { docx: string; txt: string } | null;
};
export type WritingMatch = { message: string; short_message: string; context: string; offset: number; length: number; category: string; suggestions: string[] };
export type WritingCheckResult = { matches: WritingMatch[] };

export type AtsStatus = "pass" | "warn" | "fail";
export type AtsCheck = { id: string; group: string; status: AtsStatus; title: string; why: string; fix: string; weight: number; lines: number[] };
export type CoverageTerm = { term: string; required: boolean };
export type Coverage = { percent: number; wanted: number; found: CoverageTerm[]; in_material: CoverageTerm[]; not_in_material: CoverageTerm[]; note: string };
export type AiInfo = { available: boolean; settings_link: string; missing_message: string };
export type AtsReport = {
  readiness: number; label: string; caveat: string; checks: AtsCheck[]; counts: Record<AtsStatus, number>;
  stats: { words: number; pages: number; bullets?: number; numbers_share?: number };
  export: { summary: string; single_column: boolean; text_based: boolean; standard_font: string };
  notes: string[]; empty: boolean; version: { id: number; label: string }; ai: AiInfo; job: JobRef | null; coverage: Coverage | null;
};
export type JobChoices = { ai: AiInfo; jobs: (JobRef & { has_description: boolean })[] };
export type SuggestionKind = "bullet" | "summary" | "heading" | "keyword";
export type Suggestion = { id: number; kind: SuggestionKind; original: string; replacement: string; reason: string };
export type Improved = { suggestions: Suggestion[]; dropped: number; message: string };
export type Built = { id: number; content: string; polished: number; kept_as_written: number; readiness: number; label: string };

export type RefineMessage = { id: number; role: "user" | "assistant"; text: string; flagged_count: number; result_id: number | null; created_at: string };
export type RefineState = { ai: AiInfo; messages: RefineMessage[]; undo_to?: number | null; can_undo?: boolean };
export type CvRefined = { id: number; summary: string; flagged: boolean; flagged_count: number; check_report: Finding[]; exportable: boolean; messages: RefineMessage[]; undo_to: number | null };
export type CoverRefined = { summary: string; letter: Cover; messages: RefineMessage[]; can_undo: boolean };

export const cvApi = {
  refineState: (id: number) => request<RefineState>("GET", `/cv/${id}/refine`),
  refine: (id: number, message: string) => request<CvRefined>("POST", `/cv/${id}/refine`, { message }),
  refineUndo: (id: number) => request<{ id: number }>("POST", `/cv/${id}/refine/undo`),
  ats: (id: number, jobId?: number | null) => request<AtsReport>("GET", `/cv/${id}/ats${jobId ? `?job=${jobId}` : ""}`),
  improve: (id: number, jobId?: number | null) => request<Improved>("POST", `/cv/${id}/improve`, { job_id: jobId ?? null }),
  jobChoices: () => request<JobChoices>("GET", "/cv/job-choices"),
  build: (answers: BuilderAnswers, polish: boolean) => request<Built>("POST", "/cv/builder", { answers, polish }),
  list: () => request<CvList>("GET", "/cv"),
  get: (id: number) => request<CvDetail>("GET", `/cv/${id}`),
  edit: (id: number, content: string, label: string) => request<{ id: number; changed: boolean }>("POST", `/cv/${id}/edit`, { content, label }),
  diff: (id: number, against?: number) => request<CvDiff>("GET", `/cv/${id}/diff${against ? `?against=${against}` : ""}`),
  approve: (id: number) => request<{ ok: true; exportable: boolean }>("POST", `/cv/${id}/approve`),
  restore: (id: number) => request<{ id: number }>("POST", `/cv/${id}/restore`),
  remove: (id: number) => request<{ ok: true }>("DELETE", `/cv/${id}`),
  tailor: (jobId: number) => request<Made>("POST", `/jobs/${jobId}/tailor`, { mode: "auto" }),
  writingCheck: (id: number) => request<WritingCheckResult>("POST", `/cv/${id}/writing-check`),
};

export const coverApi = {
  refineState: (id: number) => request<RefineState>("GET", `/cover/${id}/refine`),
  refine: (id: number, message: string) => request<CoverRefined>("POST", `/cover/${id}/refine`, { message }),
  refineUndo: (id: number) => request<CoverRefined>("POST", `/cover/${id}/refine/undo`),
  get: (id: number) => request<Cover>("GET", `/cover/${id}`),
  save: (id: number, content: string) => request<Cover>("POST", `/cover/${id}/save`, { content }),
  approve: (id: number) => request<{ ok: true; exportable: boolean }>("POST", `/cover/${id}/approve`),
  remove: (id: number) => request<{ ok: true }>("DELETE", `/cover/${id}`),
  write: (jobId: number) => request<Made>("POST", `/jobs/${jobId}/cover-letter`, { mode: "auto" }),
  writingCheck: (id: number) => request<WritingCheckResult>("POST", `/cover/${id}/writing-check`),
};
