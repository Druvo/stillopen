/** The pure part of the jump-to palette and the keyboard shortcuts: what can be reached, how a typed word narrows it, what "g then d" means. */

export type PaletteEntry = {
  id: string;
  label: string;
  /** Where it goes, inside the app (no /app prefix). */
  to?: string;
  /** A small thing it does instead of going anywhere. */
  action?: "scan" | "theme";
  group: "Go to" | "Do";
  /** Extra words that should also find it ("resume" finds "CVs"). */
  words?: string;
  needs?: "prep_enabled" | "assistant_enabled";
};

export const ENTRIES: PaletteEntry[] = [
  { id: "add", label: "Add job", to: "/jobs/add", group: "Do", words: "new paste link track" },
  { id: "scan", label: "Search for jobs now", action: "scan", group: "Do", words: "find run look scan" },
  { id: "theme", label: "Switch between light and dark", action: "theme", group: "Do", words: "theme mode night" },
  { id: "dashboard", label: "Dashboard", to: "/", group: "Go to", words: "home jobs" },
  { id: "postings", label: "All postings", to: "/postings", group: "Go to", words: "found every search" },
  { id: "cv", label: "CVs", to: "/cv", group: "Go to", words: "cv resume versions" },
  { id: "interviews", label: "Interviews", to: "/interviews", group: "Go to", words: "calendar" },
  { id: "contacts", label: "Contacts", to: "/contacts", group: "Go to", words: "people recruiters" },
  { id: "offers", label: "Offers", to: "/offers", group: "Go to", words: "pay compare" },
  { id: "insights", label: "Insights", to: "/insights", group: "Go to", words: "numbers funnel stats" },
  { id: "companies", label: "Companies", to: "/companies", group: "Go to" },
  { id: "questions", label: "Question bank", to: "/questions", group: "Go to", words: "interview answers" },
  { id: "prep", label: "Prep plans", to: "/prep", group: "Go to", words: "practice preparation", needs: "prep_enabled" },
  { id: "notifications", label: "Notifications", to: "/notifications", group: "Go to", words: "alerts bell" },
  { id: "documents", label: "Documents about you", to: "/knowledge", group: "Go to", words: "knowledge notes" },
  { id: "profile", label: "Your profile", to: "/profile", group: "Go to", words: "roles places country" },
  { id: "ai", label: "AI settings", to: "/profile/ai", group: "Go to", words: "key model provider" },
  { id: "usage", label: "AI usage and cost", to: "/profile/ai/usage", group: "Go to", words: "tokens spend" },
  { id: "assistant", label: "Assistant", to: "/profile/assistant", group: "Go to", words: "chat connect", needs: "assistant_enabled" },
  { id: "sources", label: "Job sources", to: "/sources", group: "Go to", words: "boards companies" },
  { id: "help", label: "Help", to: "/help", group: "Go to", words: "how guide" },
];

/** The entries a person can use: the ones their admin switched off are left out (until /me has answered, everything shows). */
export function availableEntries(flags: Partial<Record<"prep_enabled" | "assistant_enabled", boolean>> | undefined): PaletteEntry[] {
  return ENTRIES.filter((e) => !e.needs || flags?.[e.needs] !== false);
}

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/** Every typed word must start a word of the entry (its label or its extra words). Better matches first: label start, then a label word, then extra words. */
export function filterEntries(entries: PaletteEntry[], query: string): PaletteEntry[] {
  const words = norm(query).split(" ").filter(Boolean);
  if (!words.length) return entries;
  const scored: { entry: PaletteEntry; score: number }[] = [];
  for (const entry of entries) {
    const label = norm(entry.label);
    const labelWords = label.split(" ");
    const extra = norm(entry.words ?? "").split(" ").filter(Boolean);
    let score = 0;
    let ok = true;
    for (const w of words) {
      if (label.startsWith(w)) score += 3;
      else if (labelWords.some((x) => x.startsWith(w))) score += 2;
      else if (extra.some((x) => x.startsWith(w))) score += 1;
      else {
        ok = false;
        break;
      }
    }
    if (ok) scored.push({ entry, score });
  }
  return scored.sort((a, b) => b.score - a.score).map((s) => s.entry); // the sort is stable: ties keep their order
}

/** "g" then one of these keys goes to the screen. */
export const GO_TO: Record<string, { to: string; label: string }> = {
  d: { to: "/", label: "Dashboard" },
  j: { to: "/jobs/add", label: "Add a job" },
  c: { to: "/cv", label: "CVs" },
  i: { to: "/interviews", label: "Interviews" },
  p: { to: "/profile", label: "Your profile" },
  h: { to: "/help", label: "Help" },
};

export type KeyStep = { open?: "palette" | "shortcuts"; go?: string; waitForGo?: boolean };

/** True when the key press is going into something the person is typing in, where a shortcut letter is just a letter. */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true;
}

/**
 * What a key press means. `waiting` is true right after "g". Cmd/Ctrl+K works everywhere; the single-letter shortcuts never fire while
 * typing, with a modifier held, or while a dialog is open.
 */
export function readKey(e: { key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; target: EventTarget | null }, waiting: boolean, dialogOpen: boolean): KeyStep | null {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") return { open: "palette" };
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target) || dialogOpen) return null;
  if (waiting) {
    const hit = GO_TO[e.key.toLowerCase()];
    return hit ? { go: hit.to } : null;
  }
  if (e.key === "/") return { open: "palette" };
  if (e.key === "?") return { open: "shortcuts" };
  if (e.key === "g") return { waitForGo: true };
  return null;
}

/** The rows of the shortcuts help, grouped. */
export const SHORTCUTS: { title: string; rows: { keys: string[]; text: string }[] }[] = [
  {
    title: "Anywhere",
    rows: [
      { keys: ["/"], text: "Search and jump to a screen" },
      { keys: ["Ctrl", "K"], text: "The same, also while typing (Cmd K on a Mac)" },
      { keys: ["?"], text: "Show this list" },
      { keys: ["Esc"], text: "Close a dialog or menu" },
    ],
  },
  {
    title: "Go to (press g, then)",
    rows: Object.entries(GO_TO).map(([k, v]) => ({ keys: ["g", k], text: v.label })),
  },
];
