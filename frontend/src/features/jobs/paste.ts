import type { ParsedFields } from "@/features/assist/extras-api";

const LABELS: Record<keyof ParsedFields, string> = { company: "the company", role: "the role", location: "the place", pay: "the pay", deadline: "the apply-by date", link: "the link" };

/**
 * The Add job form with what was read from pasted text laid over it. Only EMPTY fields are filled, so nothing the person typed is replaced.
 * The form has no place or pay box, so those two go into the notes (only when the notes are empty). Returns the plain-words list of what changed.
 */
export function fillFromParsed(values: Record<string, string>, fields: ParsedFields): { values: Record<string, string>; filled: string[] } {
  const next = { ...values };
  const filled: string[] = [];
  const put = (key: string, value: string, label: keyof ParsedFields) => {
    if (value && !(next[key] ?? "").trim()) {
      next[key] = value;
      filled.push(LABELS[label]);
    }
  };
  put("company", fields.company, "company");
  put("role", fields.role, "role");
  put("url", fields.link, "link");
  put("deadline", fields.deadline, "deadline");
  const extra = [fields.location && `Place: ${fields.location}`, fields.pay && `Pay: ${fields.pay}`].filter(Boolean).join(". ");
  if (extra && !(next.notes ?? "").trim()) {
    next.notes = extra;
    if (fields.location) filled.push(LABELS.location);
    if (fields.pay) filled.push(LABELS.pay);
  }
  return { values: next, filled };
}

/** "We filled in the company, the role and the pay." / what to do when nothing was found. */
export function filledMessage(filled: string[], aiNotice = ""): string {
  if (filled.length === 0) return "We found nothing new to fill in. Either the form already has those details, or the text is short on them. Type them in, or paste more of the posting.";
  const list = filled.length === 1 ? filled[0] : `${filled.slice(0, -1).join(", ")} and ${filled[filled.length - 1]}`;
  return `We filled in ${list}. Please check each one before you save.${aiNotice ? ` ${aiNotice}` : ""}`;
}
