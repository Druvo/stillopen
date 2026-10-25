/** Pure helpers for the ATS check card, applying a suggestion to the editor text, and the CV builder wizard. No React, no network. */

// --- ATS check ----------------------------------------------------------------------------------------------------------------------

export type CheckLike = { id: string; status: "pass" | "warn" | "fail"; weight: number; lines: number[] };

export const GROUP_LABELS = { fail: "Needs fixing", warn: "Worth a look", pass: "Looks good" } as const;

/** The checks in the three groups people read them in; the heaviest first inside a group, so the fix that matters most is at the top. */
export function groupChecks<T extends CheckLike>(checks: T[]): { status: "fail" | "warn" | "pass"; label: string; items: T[] }[] {
  return (["fail", "warn", "pass"] as const)
    .map((status) => ({ status, label: GROUP_LABELS[status], items: checks.filter((c) => c.status === status).sort((a, b) => b.weight - a.weight) }))
    .filter((g) => g.items.length > 0);
}

/** "line 4", "lines 4, 7" or an empty string. */
export function lineLabel(lines: number[]): string {
  if (lines.length === 0) return "";
  return `${lines.length === 1 ? "line" : "lines"} ${lines.join(", ")}`;
}

/** The number with its words, so the meaning never depends on a colour. */
export function readinessText(readiness: number, label: string): string {
  return `${readiness} out of 100: ${label}`;
}

export function countsText(counts: { fail: number; warn: number; pass: number }): string {
  return `${counts.fail} to fix, ${counts.warn} worth a look, ${counts.pass} fine`;
}

/** Colour is only a second signal next to the words; this picks it from the number. */
export function readinessTone(readiness: number): "good" | "warn" | "bad" {
  return readiness >= 85 ? "good" : readiness >= 55 ? "warn" : "bad";
}

// --- applying a suggestion to the editor's text -------------------------------------------------------------------------------------

export type SuggestionLike = { original: string; replacement: string };

/**
 * Puts one suggestion into the text. Replaces the first line that matches `original` (exactly, then ignoring spaces at the ends). With an empty
 * `original` (a missing summary) it adds a Summary section under the name. Returns the text unchanged and `applied: false` when the line is gone.
 */
export function applySuggestion(text: string, s: SuggestionLike): { text: string; applied: boolean } {
  const lines = text.split("\n");
  if (!s.original.trim()) {
    const at = lines.findIndex((l) => /^#\s/.test(l));
    const insertAt = at < 0 ? 0 : at + 1;
    const block = at < 0 ? ["## Summary", s.replacement, ""] : ["", "## Summary", s.replacement];
    return { text: [...lines.slice(0, insertAt), ...block, ...lines.slice(insertAt)].join("\n"), applied: true };
  }
  let index = lines.findIndex((l) => l === s.original);
  if (index < 0) index = lines.findIndex((l) => l.trim() === s.original.trim());
  if (index < 0) return { text, applied: false };
  const next = [...lines];
  next[index] = s.replacement;
  return { text: next.join("\n"), applied: true };
}

export const KIND_LABELS: Record<string, string> = { bullet: "Clearer bullet", summary: "Summary", heading: "Standard heading", keyword: "Skill from your own material" };

// --- the CV builder -----------------------------------------------------------------------------------------------------------------

export type BuilderRole = { title: string; company: string; location: string; start: string; end: string; bullets: string[] };
export type BuilderEdu = { school: string; degree: string; start: string; end: string };
export type BuilderGroup = { group: string; items: string };
export type BuilderProject = { name: string; description: string; link: string };
export type BuilderAnswers = {
  name: string; email: string; phone: string; location: string; links: string[]; summary: string;
  roles: BuilderRole[]; education: BuilderEdu[]; skills: BuilderGroup[]; projects: BuilderProject[]; languages: string; certificates: string;
};

export const STEPS = ["Contact", "Summary", "Work", "Education", "Skills", "Projects", "Languages and certificates"] as const;
export const DRAFT_KEY = "stillopen-cv-builder-draft";
export const MAX_ROLES = 4;

export const emptyRole = (): BuilderRole => ({ title: "", company: "", location: "", start: "", end: "", bullets: ["", "", ""] });

export function emptyAnswers(): BuilderAnswers {
  return {
    name: "", email: "", phone: "", location: "", links: [""], summary: "",
    roles: [emptyRole()], education: [{ school: "", degree: "", start: "", end: "" }],
    skills: [{ group: "Tools", items: "" }, { group: "Languages", items: "" }],
    projects: [{ name: "", description: "", link: "" }], languages: "", certificates: "",
  };
}

const DATE = /^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{1,2}[/.]\d{4}|\d{4}-(?:0[1-9]|1[0-2])|\d{4})$/i;
const EMAIL = /^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$/;
export const isDate = (s: string) => DATE.test(s.trim());
const filled = (s: string) => s.trim().length > 0;

/** Plain messages for one step, keyed by the field they belong to (`roles.0.title`). Empty object = fine to go on. */
export function validateStep(step: number, a: BuilderAnswers): Record<string, string> {
  const errors: Record<string, string> = {};
  if (step === 0) {
    if (!filled(a.name)) errors.name = "Add your name.";
    if (!EMAIL.test(a.email.trim())) errors.email = "Add an email address employers can reach you on, such as name@example.com.";
  }
  if (step === 2) {
    a.roles.forEach((r, i) => {
      if (![r.title, r.company, r.start, r.end, ...r.bullets].some(filled)) return;
      if (!filled(r.title)) errors[`roles.${i}.title`] = "Add the job title.";
      if (!filled(r.company)) errors[`roles.${i}.company`] = "Add the company.";
      if (!filled(r.start)) errors[`roles.${i}.start`] = "Add when you started, like Jan 2022 or 2022.";
      else if (!isDate(r.start)) errors[`roles.${i}.start`] = "Write the date like Jan 2022 or 2022.";
      if (filled(r.end) && !/^(present|now|current)$/i.test(r.end.trim()) && !isDate(r.end)) {
        errors[`roles.${i}.end`] = "Write the date like Mar 2024 or 2024, or leave it empty if you still work there.";
      }
    });
  }
  if (step === 3) {
    a.education.forEach((e, i) => {
      if (![e.school, e.degree, e.start, e.end].some(filled)) return;
      if (!filled(e.school)) errors[`education.${i}.school`] = "Add the school or university.";
      for (const key of ["start", "end"] as const) {
        if (filled(e[key]) && !isDate(e[key])) errors[`education.${i}.${key}`] = "Write the year like 2021.";
      }
    });
  }
  if (step === STEPS.length - 1) {
    const hasWork = a.roles.some((r) => filled(r.title) && filled(r.company));
    const hasEdu = a.education.some((e) => filled(e.school));
    const hasProject = a.projects.some((p) => filled(p.name));
    if (!hasWork && !hasEdu && !hasProject) errors.form = "Add at least one job, a school or a project (go back to those steps), so the CV has something to say.";
  }
  return errors;
}

/** What the server is sent: empty rows and spaces removed, at most the number of rows the server keeps. */
export function toApiAnswers(a: BuilderAnswers): BuilderAnswers {
  const t = (s: string) => s.trim();
  return {
    ...a, name: t(a.name), email: t(a.email), phone: t(a.phone), location: t(a.location), summary: t(a.summary),
    links: a.links.map(t).filter(Boolean).slice(0, 3),
    roles: a.roles
      .filter((r) => [r.title, r.company, r.start, r.end, ...r.bullets].some(filled))
      .slice(0, MAX_ROLES)
      .map((r) => ({ ...r, title: t(r.title), company: t(r.company), location: t(r.location), start: t(r.start), end: t(r.end), bullets: r.bullets.map(t).filter(Boolean).slice(0, 5) })),
    education: a.education.filter((e) => [e.school, e.degree, e.start, e.end].some(filled)).slice(0, 3),
    skills: a.skills.filter((g) => filled(g.items)).slice(0, 6),
    projects: a.projects.filter((p) => filled(p.name)).slice(0, 3),
    languages: t(a.languages), certificates: t(a.certificates),
  };
}

/** Reads a saved draft; anything that is not the expected shape (an old version, hand-edited, broken JSON) is ignored. */
export function parseDraft(raw: string | null): { step: number; answers: BuilderAnswers } | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as { step?: unknown; answers?: Record<string, unknown> };
    if (!data || typeof data.step !== "number" || !data.answers || typeof data.answers !== "object") return null;
    const base = emptyAnswers() as unknown as Record<string, unknown>;
    const merged: Record<string, unknown> = { ...base };
    for (const [key, value] of Object.entries(data.answers)) {
      if (key in base && typeof value === typeof base[key] && Array.isArray(value) === Array.isArray(base[key])) merged[key] = value;
    }
    for (const key of ["roles", "links", "education", "skills", "projects"]) {
      const list = merged[key];
      if (!Array.isArray(list) || list.length === 0) merged[key] = base[key];
    }
    return { step: Math.min(Math.max(Math.trunc(data.step), 0), STEPS.length - 1), answers: merged as unknown as BuilderAnswers };
  } catch {
    return null;
  }
}

/** "Step 2 of 7: Summary" and its percentage for the progress bar. */
export function stepProgress(step: number): { label: string; percent: number } {
  return { label: `Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`, percent: Math.round(((step + 1) / STEPS.length) * 100) };
}
