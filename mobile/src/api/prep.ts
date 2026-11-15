import { api } from "./client";

export type Source = { title: string; url: string; checked?: boolean | null };
export type Question = { id: number; prompt: string; kind: string; kind_label: string; choices: string[]; correct: number[]; explanation: string; sources: Source[] };
export type Lesson = { id: number; title: string; topics: string[]; gap: string; sources: Source[]; done: boolean; questions?: Question[] };
export type Milestone = { id: number; kind: string; kind_label: string; text: string; done: boolean };
export type Week = { id: number; order: number; title: string; goal: string; hours: number; lessons: Lesson[]; milestones: Milestone[] };
export type PlanSummary = {
  id: number;
  title: string;
  status: "generating" | "failed" | "draft" | "active" | "done";
  status_label: string;
  job: { id: number; role: string; company: string } | null;
  lessons_total: number;
  lessons_done: number;
};
export type Plan = PlanSummary & {
  summary: string;
  progress: string;
  error: string;
  hours_per_week: number;
  generator: string;
  percent: number;
  question_count: number;
  streak: number;
  weak_topics: { slug: string; title: string }[];
  done_today: boolean;
  unchecked_links: number;
  weeks: Week[];
  gap_skills: { skill: string; why: string; cv_evidence: string }[];
};
export type PracticeRow = {
  id: number;
  topic: string;
  prompt: string;
  kind: string;
  choices: string[];
  review: boolean;
  chosen?: number[];
  right?: boolean | null;
  correct?: number[];
  explanation?: string;
  sources?: Source[];
};
export type Practice = {
  plan: { id: number; title: string };
  finished: boolean;
  rows: PracticeRow[];
  right: number;
  total: number;
  streak: number;
  weak_topics: { slug: string; title: string }[];
};
export type Tally = { total: number; came_up: number; ticked: (number | string)[]; text: string };

const B = "/api/v1";
export const prepApi = {
  list: () => api.get<{ plans: PlanSummary[] }>(`${B}/prep/plans`),
  plan: (id: number) => api.get<Plan>(`${B}/prep/plans/${id}`),
  create: (jobId: number) => api.post<{ id: number; existing: boolean }>(`${B}/jobs/${jobId}/prep`, {}),
  start: (id: number) => api.post<{ ok: true }>(`${B}/prep/plans/${id}/start`),
  discard: (id: number) => api.delete<{ ok: true }>(`${B}/prep/plans/${id}`),
  removeLesson: (id: number) => api.delete<{ ok: true }>(`${B}/prep/lessons/${id}`),
  removeQuestion: (id: number) => api.delete<{ ok: true }>(`${B}/prep/questions/${id}`),
  tickLesson: (id: number) => api.post<{ ok: true; done: boolean }>(`${B}/prep/lessons/${id}/tick`),
  tickMilestone: (id: number) => api.post<{ ok: true; done: boolean }>(`${B}/prep/milestones/${id}/tick`),
  today: (id: number) => api.get<Practice>(`${B}/prep/plans/${id}/today`),
  answer: (id: number, answers: Record<string, number[]>) => api.post<{ ok: true; right: number; total: number }>(`${B}/prep/plans/${id}/answers`, { answers }),
  planTally: (planId: number) => api.get<Tally>(`${B}/prep/plans/${planId}/came-up`),
  setPlanCameUp: (questionId: number, value: boolean) => api.post<Tally>(`${B}/prep/questions/${questionId}/came-up`, { value }),
};
