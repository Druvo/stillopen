/**
 * The quick-add bar reads a posting, then Add job opens with what was found. The text can be long (a whole job description), so it travels
 * through this tab's session storage, never the address, and is taken out the moment Add job reads it (nothing is saved until the person
 * has looked it over and pressed Save).
 */
export type QuickAddPrefill = { url: string; role: string; company: string; description: string; blocked_host?: string; message?: string };

const KEY = "stillopen-quickadd-prefill";

export function stashPrefill(found: QuickAddPrefill): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ url: found.url, role: found.role, company: found.company, description: found.description, blocked_host: found.blocked_host, message: found.message }));
  } catch {
    /* storage is blocked: Add job opens empty and the person can paste the link there */
  }
}

/** The stashed prefill, once; null when there is none. */
export function takePrefill(): QuickAddPrefill | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);
    const parsed = JSON.parse(raw);
    const text = (v: unknown) => (typeof v === "string" ? v : "");
    return {
      url: text(parsed.url), role: text(parsed.role), company: text(parsed.company), description: text(parsed.description),
      ...(text(parsed.blocked_host) ? { blocked_host: text(parsed.blocked_host), message: text(parsed.message) } : {}),
    };
  } catch {
    return null;
  }
}
