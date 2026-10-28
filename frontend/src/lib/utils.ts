import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** The link for an apply address a posting publishes (a bare email or a web link), or "" when it is neither. Never sends anything. */
export function applyHref(address: string | undefined | null): string {
  const a = (address ?? "").trim();
  if (/^https?:\/\//i.test(a)) return a;
  return /^[^\s@<>"']+@[^\s@<>"']+\.[A-Za-z]{2,}$/.test(a) ? `mailto:${a}` : "";
}
