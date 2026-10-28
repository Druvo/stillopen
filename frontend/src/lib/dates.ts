/**
 * One way to write a date, everywhere: "29 Sep 2026", and with a time "Sat 31 Oct 2026, 04:55". The same words on every screen and in
 * every browser language, so a date on Interviews reads like the one on the dashboard. Anything that is not a date comes back unchanged.
 */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n: number) => String(n).padStart(2, "0");

/** "2026-09-29" (or a full timestamp) as "29 Sep 2026", read as the calendar day written, never shifted by a time zone. */
export function dayText(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return iso;
  return `${Number(m[3])} ${MONTHS[month - 1]} ${m[1]}`;
}

/** A moment (an ISO timestamp, or a local "2026-11-03T14:30") as "Tue 3 Nov 2026, 14:30" in the viewer's own time zone. */
export function dayTimeText(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
