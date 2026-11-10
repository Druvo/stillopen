/** The sentences shown after a tailored CV or cover letter has been made, worded as the classic pages did. */
export type Said = { text: string; tone: "success" | "error" };

export function tailoredSaid(made: { flagged: boolean; flagged_count: number }): Said {
  if (made.flagged) {
    return { text: `Tailored CV saved, but ${made.flagged_count} claim(s) are not in your own material. Review them before using it.`, tone: "error" };
  }
  return { text: "Your tailored CV is ready. Everything in it comes from your own material, so read it over and approve it when you are happy.", tone: "success" };
}

export function letterSaid(made: { flagged: boolean; flagged_count: number }): Said {
  if (made.flagged) {
    return { text: `Letter saved, but ${made.flagged_count} claim(s) are not in your own material. Review them before using it.`, tone: "error" };
  }
  return { text: "Your cover letter is ready. Read it over and make it sound like you.", tone: "success" };
}
