import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

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
export type Suggestions = { roles: string[]; places: string[]; method: "ai" | "rules"; notice: string };
export type MessageKind = "follow_up" | "thank_you" | "withdraw" | "accept" | "decline";
export type MessageDraftResult = { subject: string; body: string; method: "template" | "ai"; flagged: Finding[]; flagged_count: number; notice: string };
export type AssistStatus = { ai: boolean; settings_path: string; message: string };

export const assistApi = {
  status: () => request<AssistStatus>("GET", "/assist/status"),
  getPrep: (jobId: number) => request<{ prep: InterviewPrep | null; ai: boolean }>("GET", `/jobs/${jobId}/interview-prep`),
  makePrep: (jobId: number) => request<{ prep: InterviewPrep; ai: boolean }>("POST", `/jobs/${jobId}/interview-prep`),
  feedback: (jobId: number, question: string, answer: string) =>
    request<{ feedback: Feedback }>("POST", `/jobs/${jobId}/interview-prep/feedback`, { question, answer }),
  answer: (jobId: number, question: string) => request<AnswerDraft>("POST", `/jobs/${jobId}/application-answer`, { question }),
  getSummary: (jobId: number) => request<{ summary: PostingSummary | null; ai: boolean }>("GET", `/jobs/${jobId}/summary`),
  summarise: (jobId: number) => request<{ summary: PostingSummary; ai: boolean }>("POST", `/jobs/${jobId}/summarise`),
  suggest: (cv?: string) => request<Suggestions>("POST", "/profile/suggest", cv && cv.trim() ? { cv } : {}),
  message: (jobId: number, body: { kind: MessageKind; note?: string; interview_id?: number | null; polish?: boolean }) =>
    request<MessageDraftResult>("POST", `/jobs/${jobId}/message-draft`, body),
};

/** Whether the person has an AI set up for the optional helpers (one small call, shared by every helper on the screen). */
export function useAssistStatus() {
  return useQuery({ queryKey: ["assist", "status"], queryFn: assistApi.status, staleTime: 60_000 });
}
