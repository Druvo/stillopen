/** Money as plain text in the offer's own currency. Never converted. A code the browser does not know is shown as written. */
export function formatMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${Math.round(value).toLocaleString()} ${currency}`;
  }
}

/** "2026-11-03T14:30" (the person's own time) as a readable date and time. */
export function whenLabel(local: string): string {
  const date = new Date(local);
  if (Number.isNaN(date.getTime())) return local;
  return date.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** A dated field ("2026-11-03") as a readable date. */
export function dayLabel(day: string): string {
  if (!day) return "";
  const date = new Date(`${day}T00:00:00`);
  return Number.isNaN(date.getTime()) ? day : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** The first job to pre-select in an add form: the `?job=` of the address when it is one of the person's jobs, else none. */
export function jobFromSearch(search: string, jobs: { id: number }[]): string {
  const id = new URLSearchParams(search).get("job") ?? "";
  return jobs.some((j) => String(j.id) === id) ? id : "";
}
