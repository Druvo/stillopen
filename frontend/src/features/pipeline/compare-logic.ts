export const MAX_COMPARE = 4;
export const MIN_COMPARE = 2;

/** The ticked offers after one more tick or untick; a fifth tick is ignored (the screen says why). */
export function toggleOffer(selected: number[], id: number): number[] {
  if (selected.includes(id)) return selected.filter((x) => x !== id);
  return selected.length >= MAX_COMPARE ? selected : [...selected, id];
}

export function canCompare(selected: number[]): boolean {
  return selected.length >= MIN_COMPARE && selected.length <= MAX_COMPARE;
}

/** One plain line about what is ticked, so the person knows what to do next. */
export function compareHint(count: number): string {
  if (count === 0) return "Tick two to four offers to read the differences in words.";
  if (count === 1) return "Tick one more offer to compare.";
  if (count >= MAX_COMPARE) return `That is the most we can compare at once (${MAX_COMPARE}).`;
  return `${count} offers ticked.`;
}
