// API calls for CVs, cover letters and documents (worker C). Types mirror frontend/src/features/cv/api.ts.
import { api } from "./client";
import type { Imported } from "../screens/cv/logic/importlogic";
import type { DiffRow, Finding } from "../screens/cv/logic/logic";
import type { BuilderAnswers } from "../screens/cv/logic/quality";

const V = "/api/v1";

export type JobRef = { id: number; role: string; company: string };
export type CvSummary = {
  id: number; label: string; kind: "master" | "tailored"; kind_label: string; source: string; source_label: string; provider: string; created_at: string;
  job: JobRef | null; flagged: boolean; flagged_count: number; approved: boolean; exportable: boolean; current?: boolean; ats_readiness?: number;
};
export type CvList = { masters: CvSummary[]; tailored: CvSummary[] };
export type CvDownloads = { docx: string; md: string; print: string };
export type CvDetail = CvSummary & {
  content: string; check_report: Finding[]; approved_at: string | null; job_snapshot: string; parent: { id: number; label: string } | null; children: number; downloads: CvDownloads | null;
};
export type CvDiff = { version: { id: number; label: string }; other: { id: number; label: string } | null; rows: DiffRow[]; choices: { id: number; label: string }[] };
export type Made = { id: number; flagged: boolean; flagged_count: number; tone?: string };
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
export type Suggestion = { id: number; kind: "bullet" | "summary" | "heading" | "keyword"; original: string; replacement: string; reason: string };
export type Improved = { suggestions: Suggestion[]; dropped: number; message: string };
export type Built = { id: number; content: string; polished: number; kept_as_written: number; readiness: number; label: string };

export type RefineMessage = { id: number; role: "user" | "assistant"; text: string; flagged_count: number; result_id: number | null; created_at: string };
export type RefineState = { ai: AiInfo; messages: RefineMessage[]; undo_to?: number | null; can_undo?: boolean };
export type CvRefined = { id: number; summary: string; flagged: boolean; flagged_count: number; check_report: Finding[]; exportable: boolean; messages: RefineMessage[]; undo_to: number | null };
export type CoverRefined = { summary: string; letter: Cover; messages: RefineMessage[]; can_undo: boolean };

export type TailorMode = "auto" | "ai" | "keywords";
export type CoverTone = "warm" | "direct" | "formal";

export type DocumentRow = { id: number; title: string; kind: string; kind_label: string; enabled: boolean; characters: number; passages: number; updated: string };
export type Documents = {
  sources: DocumentRow[];
  cv: { present: boolean; characters: number };
  limits: { max_documents: number; max_file_bytes: number; max_text_characters: number };
  kinds: { value: string; label: string }[];
  can_push_to_paperless: boolean;
};

export type JobDocuments = { ready: boolean; url: string | null; reason: string; has_cv?: boolean; has_cover?: boolean };

export type PickedFile = { uri: string; name: string; mimeType?: string | null };

/** React Native's FormData takes a { uri, name, type } object for a file. */
export function fileForm(file: PickedFile, fieldName = "file", fields: Record<string, string> = {}): FormData {
  const form = new FormData();
  form.append(fieldName, { uri: file.uri, name: file.name, type: file.mimeType || "application/octet-stream" } as unknown as Blob);
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  return form;
}

export const cvApi = {
  list: () => api.get<CvList>(`${V}/cv`),
  get: (id: number) => api.get<CvDetail>(`${V}/cv/${id}`),
  edit: (id: number, content: string, label: string) => api.post<{ id: number; changed: boolean }>(`${V}/cv/${id}/edit`, { content, label }),
  diff: (id: number, against?: number) => api.get<CvDiff>(`${V}/cv/${id}/diff${against ? `?against=${against}` : ""}`),
  approve: (id: number) => api.post<{ ok: true; exportable: boolean }>(`${V}/cv/${id}/approve`),
  restore: (id: number) => api.post<{ id: number }>(`${V}/cv/${id}/restore`),
  remove: (id: number) => api.delete<{ ok: true }>(`${V}/cv/${id}`),
  tailor: (jobId: number, mode: TailorMode) => api.post<Made>(`${V}/jobs/${jobId}/tailor`, { mode }),
  writingCheck: (id: number) => api.post<WritingCheckResult>(`${V}/cv/${id}/writing-check`),
  refineState: (id: number) => api.get<RefineState>(`${V}/cv/${id}/refine`),
  refine: (id: number, message: string) => api.post<CvRefined>(`${V}/cv/${id}/refine`, { message }),
  refineUndo: (id: number) => api.post<{ id: number }>(`${V}/cv/${id}/refine/undo`),
  ats: (id: number, jobId?: number | null) => api.get<AtsReport>(`${V}/cv/${id}/ats${jobId ? `?job=${jobId}` : ""}`),
  improve: (id: number, jobId?: number | null) => api.post<Improved>(`${V}/cv/${id}/improve`, { job_id: jobId ?? null }),
  jobChoices: () => api.get<JobChoices>(`${V}/cv/job-choices`),
  build: (answers: BuilderAnswers, polish: boolean) => api.post<Built>(`${V}/cv/builder`, { answers, polish }),
  documents: (jobId: number) => api.get<JobDocuments>(`${V}/jobs/${jobId}/documents`),
  importFile: (file: PickedFile, useAi: boolean) => api.upload<Imported>(`${V}/cv/import`, fileForm(file, "file", useAi ? { use_ai: "1" } : {})),
};

export const coverApi = {
  get: (id: number) => api.get<Cover>(`${V}/cover/${id}`),
  save: (id: number, content: string) => api.post<Cover>(`${V}/cover/${id}/save`, { content }),
  approve: (id: number) => api.post<{ ok: true; exportable: boolean }>(`${V}/cover/${id}/approve`),
  remove: (id: number) => api.delete<{ ok: true }>(`${V}/cover/${id}`),
  write: (jobId: number, mode: TailorMode, tone?: CoverTone) => api.post<Made>(`${V}/jobs/${jobId}/cover-letter`, tone ? { mode, tone } : { mode }),
  writingCheck: (id: number) => api.post<WritingCheckResult>(`${V}/cover/${id}/writing-check`),
  refineState: (id: number) => api.get<RefineState>(`${V}/cover/${id}/refine`),
  refine: (id: number, message: string) => api.post<CoverRefined>(`${V}/cover/${id}/refine`, { message }),
  refineUndo: (id: number) => api.post<CoverRefined>(`${V}/cover/${id}/refine/undo`),
};

export const documentsApi = {
  list: () => api.get<Documents>(`${V}/documents`),
  addText: (title: string, kind: string, text: string) => api.post<DocumentRow>(`${V}/documents`, { title, kind, text }),
  addFile: (title: string, kind: string, text: string, file: PickedFile) => api.upload<DocumentRow>(`${V}/documents`, fileForm(file, "file", { title, kind, text })),
  toggle: (id: number) => api.post<{ ok: true; enabled: boolean }>(`${V}/documents/${id}/toggle`),
  remove: (id: number) => api.delete<{ ok: true }>(`${V}/documents/${id}`),
};

/** What the account says about the things these screens switch on (writing check) and the person's saved cover tone. */
export const settingsApi = {
  writingCheckEnabled: async () => (await api.get<{ writing_check_enabled?: boolean }>(`${V}/me`)).writing_check_enabled === true,
  coverTone: async (): Promise<CoverTone> => {
    const p = await api.get<{ cover_tone?: string }>(`${V}/preferences`);
    return p.cover_tone === "direct" || p.cover_tone === "formal" ? p.cover_tone : "warm";
  },
};
