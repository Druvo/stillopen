import { api } from "./client";
import type { Tally } from "./prep";

export type Star = { situation: boolean; task: boolean; action: boolean; result: boolean };
export type PrepQuestion = { id: string; question: string; testing: string; outline: string[]; flags: string[] };
export type PrepGroup = { key: string; title: string; questions: PrepQuestion[] };
export type InterviewPrep = {
  job: { id: number; role: string; company: string };
  generated_at: string;
  notice: string;
  outline_note: string;
  dropped_points: number;
  groups: PrepGroup[];
};
export type Feedback = {
  summary: string;
  works: string[];
  vague: string[];
  add: string[];
  star: Star;
  length: { words: number; note: string };
  notice: string;
};
export type Finding = { kind: "number" | "name" | "job-term"; text: string; line: number };
export type AnswerDraft = { answer: string; words: number; flagged: Finding[]; flagged_count: number; notice: string };
export type PostingSummary = {
  method: "ai" | "rules";
  created_at: string;
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
export type MessageKind = "follow_up" | "thank_you" | "withdraw" | "accept" | "decline";
export type MessageDraftResult = { subject: string; body: string; method: "template" | "ai"; flagged: Finding[]; flagged_count: number; notice: string };
export type AssistStatus = { ai: boolean; settings_path: string; message: string };

const B = "/api/v1";
export const assistApi = {
  status: () => api.get<AssistStatus>(`${B}/assist/status`),
  getPrep: (jobId: number) => api.get<{ prep: InterviewPrep | null; ai: boolean }>(`${B}/jobs/${jobId}/interview-prep`),
  makePrep: (jobId: number) => api.post<{ prep: InterviewPrep; ai: boolean }>(`${B}/jobs/${jobId}/interview-prep`),
  feedback: (jobId: number, question: string, answer: string) => api.post<{ feedback: Feedback }>(`${B}/jobs/${jobId}/interview-prep/feedback`, { question, answer }),
  answer: (jobId: number, question: string) => api.post<AnswerDraft>(`${B}/jobs/${jobId}/application-answer`, { question }),
  getSummary: (jobId: number) => api.get<{ summary: PostingSummary | null; ai: boolean }>(`${B}/jobs/${jobId}/summary`),
  summarise: (jobId: number) => api.post<{ summary: PostingSummary; ai: boolean }>(`${B}/jobs/${jobId}/summarise`),
  message: (jobId: number, body: { kind: MessageKind; note?: string; interview_id?: number | null; polish?: boolean }) =>
    api.post<MessageDraftResult>(`${B}/jobs/${jobId}/message-draft`, body),
  jobTally: (jobId: number) => api.get<Tally>(`${B}/jobs/${jobId}/came-up`),
  saveToBank: (question: string, jobId: number) =>
    api.post<unknown>(`${B}/bank`, { question: question.slice(0, 400), answer: "", tags: [], job_ids: [jobId], interview_ids: [] }),
  setJobCameUp: (jobId: number, key: string, value: boolean) => api.post<Tally>(`${B}/jobs/${jobId}/came-up`, { key, value }),
};

export const KINDS: { value: MessageKind; label: string }[] = [
  { value: "follow_up", label: "Following up" },
  { value: "thank_you", label: "Thank you" },
  { value: "withdraw", label: "Withdrawing" },
  { value: "accept", label: "Accepting an offer" },
  { value: "decline", label: "Declining an offer" },
];

export function questionText(q: PrepQuestion): string {
  const lines = [q.question, `What they are really testing: ${q.testing}`];
  if (q.outline.length) lines.push("Outline to rewrite in your own words:", ...q.outline.map((p) => `- ${p}`));
  return lines.join("\n");
}
export function prepText(prep: InterviewPrep): string {
  return prep.groups
    .filter((g) => g.questions.length)
    .map((g) => `${g.title}\n\n${g.questions.map(questionText).join("\n\n")}`)
    .join("\n\n");
}
export function starMissing(star: Star): string[] {
  const names: Record<keyof Star, string> = { situation: "the situation", task: "your task", action: "what you did", result: "the result" };
  return (Object.keys(names) as (keyof Star)[]).filter((k) => !star[k]).map((k) => names[k]);
}
export function findingsText(findings: Finding[]): string {
  return [...new Set(findings.map((f) => f.text))].join(", ");
}
export function statements(s: PostingSummary): { label: string; text: string }[] {
  const rows: [string, string][] = [["Level", s.seniority], ["Pay", s.pay], ["Visa", s.visa], ["Relocation", s.relocation], ["Where", s.remote], ["Deadline", s.deadline]];
  return rows.filter(([, t]) => t.trim()).map(([label, text]) => ({ label, text }));
}
export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}
