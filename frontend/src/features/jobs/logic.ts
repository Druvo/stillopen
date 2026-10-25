/** The query string for the postings list: only what is set, so the address stays short and a reload shows the same page. */
export function postingsQuery({ q, source, page }: { q: string; source: string; page: number }): string {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (source) params.set("source", source);
  if (page > 1) params.set("page", String(page));
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** The reverse of `postingsQuery`, from `window.location.search`; unknown or broken values fall back to "everything, page 1". */
export function readPostingsQuery(search: string): { q: string; source: string; page: number } {
  const params = new URLSearchParams(search);
  const source = params.get("source") ?? "";
  const page = Number(params.get("page"));
  return { q: params.get("q") ?? "", source: /^\d+$/.test(source) ? source : "", page: Number.isInteger(page) && page > 0 ? page : 1 };
}

/** "2 MB", "340 KB": how big a file may be, in words. */
export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** What the add-job form starts with after a link was read: only the fields the link filled in, never overwriting what was typed. */
export function mergePrefill(current: Record<string, string>, prefill: { url: string; role: string; company: string; description: string }): Record<string, string> {
  const next = { ...current };
  for (const key of ["url", "role", "company", "description"] as const) {
    if (!next[key]?.trim() && prefill[key]) next[key] = prefill[key];
  }
  return next;
}
