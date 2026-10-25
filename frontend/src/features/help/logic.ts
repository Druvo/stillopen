/** The site's contact address if it looks like an address, else "" (then the Help page shows no "write to" line at all). */
export function contactAddress(value: string | undefined | null): string {
  const text = (value ?? "").trim();
  return /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(text) ? text : "";
}
