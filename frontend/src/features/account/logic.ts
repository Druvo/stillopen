import type { Area, AreaValues, Preset } from "./api";

/** Add the value to the list if it is missing, take it out if it is there (a group of tick boxes). */
export function toggleValue(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * The same values as multipart form data, for a save that carries a CV file. Lists repeat the key, booleans are "true"/"false",
 * and the file goes in as `cv_file` (its text is read on the server; the file is not kept).
 */
export function toFormData(values: Record<string, unknown>, file: File | null, fileField = "cv_file"): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) value.forEach((item) => form.append(key, String(item)));
    else form.append(key, String(value));
  }
  if (file) form.append(fileField, file);
  return form;
}

export function areaToValues(area: Area): AreaValues {
  return {
    place: area.place, city: area.city, allow_remote: area.allow_remote, allow_hybrid: area.allow_hybrid, allow_onsite: area.allow_onsite,
    needs_visa_sponsorship: area.needs_visa_sponsorship, needs_relocation_support: area.needs_relocation_support,
    min_salary: area.min_salary === null ? "" : String(area.min_salary), salary_currency: area.salary_currency, salary_period: area.salary_period,
  };
}

export const BLANK_AREA: AreaValues = {
  place: "", city: "", allow_remote: true, allow_hybrid: false, allow_onsite: false, needs_visa_sponsorship: false, needs_relocation_support: false,
  min_salary: "", salary_currency: "", salary_period: "month",
};

/** What to send for an area: an empty minimum pay is `null`, not an empty string. */
export function areaPayload(values: AreaValues): Record<string, unknown> {
  return { ...values, min_salary: values.min_salary.trim() === "" ? null : values.min_salary.trim() };
}

/** Quick setup: the provider, address and model a preset fills in. The key is never part of it. */
export function applyPreset(preset: Preset) {
  return { ai_provider: preset.provider, ai_base_url: preset.base_url, ai_model: preset.model };
}

/** The one line to paste in a terminal to connect Claude Code. Built in the browser from the token shown once; nothing is stored. */
export function claudeCommand(endpoint: string, token: string): string {
  return `claude mcp add --transport http stillopen ${endpoint} --header "Authorization: Bearer ${token}"`;
}

/** The settings block other assistants (Cursor, Windsurf and similar) take. */
export function mcpConfig(endpoint: string, token: string): string {
  return JSON.stringify({ mcpServers: { stillopen: { type: "http", url: endpoint, headers: { Authorization: `Bearer ${token}` } } } }, null, 2);
}

/** "3 days ago" style text for a last-used time, or "Never". */
export function lastUsed(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "Never";
}

/** The delete button stays off until the typed text is exactly the username (the server checks again). */
export function canConfirmDelete(typed: string, username: string): boolean {
  return typed.trim() === username && username !== "";
}
