/** Pure helpers for the "import an existing CV" review cards. No React, no network. */
import { emptyAnswers, type BuilderAnswers } from "./quality";

export type ImportCard = { key: string; label: string; step: number; found: boolean; preview: string[]; more: number; patch: Partial<BuilderAnswers> };
export type Imported = { method: "rules" | "ai"; chars: number; cards: ImportCard[]; notes: string[] };
export type Decision = "pending" | "accept" | "edit" | "skip";

/** What the person has still to decide: a section found in the file starts pending, one that is not there is skipped. */
export function initialDecisions(cards: ImportCard[]): Record<string, Decision> {
  return Object.fromEntries(cards.map((c) => [c.key, c.found ? "pending" : "skip"]));
}

export function acceptAll(cards: ImportCard[]): Record<string, Decision> {
  return Object.fromEntries(cards.map((c) => [c.key, c.found ? "accept" : "skip"]));
}

export const pendingCount = (decisions: Record<string, Decision>) => Object.values(decisions).filter((d) => d === "pending").length;

/** Filling the builder needs every found section decided and at least one taken. */
export function canFill(decisions: Record<string, Decision>): boolean {
  const values = Object.values(decisions);
  return !values.includes("pending") && values.some((d) => d === "accept" || d === "edit");
}

export function summaryText(decisions: Record<string, Decision>): string {
  const n = (d: Decision) => Object.values(decisions).filter((x) => x === d).length;
  const taken = n("accept") + n("edit");
  const left = n("pending");
  return left > 0 ? `${left} section${left === 1 ? "" : "s"} still to decide` : `${taken} section${taken === 1 ? "" : "s"} will fill the builder`;
}

/** The builder's answers with the taken sections put in. Lists the builder shows are never left empty, and a job always has room for three bullets. */
export function applyCards(base: BuilderAnswers, cards: ImportCard[], decisions: Record<string, Decision>): BuilderAnswers {
  const next: BuilderAnswers = { ...base };
  const blank = emptyAnswers();
  for (const card of cards) {
    if (card.found && (decisions[card.key] === "accept" || decisions[card.key] === "edit")) Object.assign(next, card.patch);
  }
  next.links = next.links.length ? next.links : blank.links;
  next.roles = (next.roles.length ? next.roles : blank.roles).map((r) => ({ ...r, bullets: [...r.bullets, "", "", ""].slice(0, Math.max(r.bullets.length, 3)) }));
  next.education = next.education.length ? next.education : blank.education;
  next.skills = next.skills.length ? next.skills : blank.skills;
  next.projects = next.projects.length ? next.projects : blank.projects;
  next.publications = next.publications.length ? next.publications : blank.publications;
  return next;
}

/** Where the builder opens: at the first section the person chose to edit, otherwise at the start. */
export function startStep(cards: ImportCard[], decisions: Record<string, Decision>): number {
  const steps = cards.filter((c) => decisions[c.key] === "edit").map((c) => c.step);
  return steps.length ? Math.min(...steps) : 0;
}
