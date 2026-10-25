/** Time zone helpers: the device's zone, the list to pick from, and when to suggest switching. Names are IANA names such as "Asia/Dhaka". */

/** This device's own time zone name, or "" when the browser cannot say. */
export function deviceZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

/** True when the browser knows `name` as a time zone. */
export function isZoneName(name: string): boolean {
  if (!name) return false;
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: name });
    return true;
  } catch {
    return false;
  }
}

/** The browser's one spelling of a zone, so "Asia/Calcutta" and "Asia/Kolkata" count as the same place. */
export function canonicalZone(name: string): string {
  if (!isZoneName(name)) return name;
  try {
    return new Intl.DateTimeFormat(undefined, { timeZone: name }).resolvedOptions().timeZone;
  } catch {
    return name;
  }
}

/** The common zones first, then every other zone the browser knows (when it can list them), without repeats. */
export function allZones(common: readonly string[]): string[] {
  const seen = new Set(common);
  const rest: string[] = [];
  try {
    const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
    for (const zone of supported) if (!seen.has(zone)) rest.push(zone);
  } catch {
    // an older browser: the common list alone is still useful, and any valid name can be typed
  }
  return [...common, ...rest.sort()];
}

/** The zone a person's days follow: their own, else the site's. */
export function effectiveZone(saved: string, site: string): string {
  return saved || site;
}

/** Suggest this device's zone only when it is a real zone, is not the one already in use, and the person has not said "not now". */
export function shouldSuggestZone(opts: { device: string; saved: string; site: string; dismissed: boolean }): boolean {
  if (opts.dismissed || !isZoneName(opts.device)) return false;
  const current = effectiveZone(opts.saved, opts.site);
  if (!current) return false;
  return canonicalZone(opts.device) !== canonicalZone(current);
}

/** A profile payload without the zone: the profile form leaves the zone to its own control, so saving the form never undoes it. */
export function withoutTimezone<T extends { timezone?: string }>(values: T): Omit<T, "timezone"> {
  const rest = { ...values };
  delete rest.timezone;
  return rest;
}
