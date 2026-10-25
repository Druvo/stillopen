import type { Feedback, Finding, InterviewPrep, MessageDraftResult, PostingSummary, PrepQuestion } from "./api";

export const AI_SETTINGS_PATH = "/profile/ai?preset=gemini";
export const NO_KEY_LINE = "Add your free Google AI Studio key in AI settings to use this.";

/** The roles box with `role` added as a new line, unless it is already there (ignoring case). Nothing is saved by this. */
export function addRole(current: string, role: string): string {
  const wanted = role.trim();
  if (!wanted || hasRole(current, wanted)) return current;
  const base = current.replace(/\s+$/, "");
  return base ? `${base}\n${wanted}` : wanted;
}

export function hasRole(current: string, role: string): boolean {
  const wanted = role.trim().toLowerCase();
  return current.split("\n").some((line) => line.trim().toLowerCase() === wanted);
}

/** A question with what it tests and its outline, as plain text for copying. */
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

export function messageText(m: Pick<MessageDraftResult, "subject" | "body">): string {
  return `Subject: ${m.subject}\n\n${m.body}`;
}

/** Which STAR parts the answer is missing, in plain words. */
export function starMissing(star: Feedback["star"]): string[] {
  const names: Record<keyof Feedback["star"], string> = { situation: "the situation", task: "your task", action: "what you did", result: "the result" };
  return (Object.keys(names) as (keyof typeof names)[]).filter((k) => !star[k]).map((k) => names[k]);
}

export function findingsText(findings: Finding[]): string {
  const unique = [...new Set(findings.map((f) => f.text))];
  return unique.join(", ");
}

/** The statements of a posting reading that say something, labelled, in a fixed order. */
export function statements(s: PostingSummary): { label: string; text: string }[] {
  const rows: [string, string][] = [
    ["Level", s.seniority],
    ["Pay", s.pay],
    ["Visa", s.visa],
    ["Relocation", s.relocation],
    ["Where", s.remote],
    ["Deadline", s.deadline],
  ];
  return rows.filter(([, text]) => text.trim()).map(([label, text]) => ({ label, text }));
}

export function canAsk(text: string, minWords: number): boolean {
  return text.trim().split(/\s+/).filter(Boolean).length >= minWords;
}
