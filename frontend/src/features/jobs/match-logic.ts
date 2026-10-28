import type { MatchRow } from "./api";

/** The mark shown in front of a requirement. The words are for screen readers: colour and the symbol are never the only clue. */
export function matchMark(state: MatchRow["state"]): { icon: string; words: string; tone: string } {
  if (state === "covered") return { icon: "✓", words: "Covered", tone: "text-good" };
  if (state === "gap") return { icon: "✗", words: "Not shown in your material", tone: "text-warn" };
  return { icon: "–", words: "Not checked yet", tone: "text-muted" };
}

/** What a strength meter says out loud. */
export function strengthText(percent: number): string {
  return `Your profile is ${percent}% ready for matching.`;
}

export const COVER_TONES = [
  { value: "warm", label: "Warm" },
  { value: "direct", label: "Direct" },
  { value: "formal", label: "Formal" },
] as const;
