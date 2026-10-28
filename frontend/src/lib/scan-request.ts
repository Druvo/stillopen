/**
 * "Search for jobs now" from the palette is asked from anywhere, but only the dashboard can start a search. The request waits here
 * (briefly) until the dashboard has its data, then it is taken once.
 */
let askedAt = 0;
const FRESH_MS = 15_000;

export function requestScan(now = Date.now()) {
  askedAt = now;
}

/** True once for a request made in the last 15 seconds; a stale one is dropped. */
export function takeScanRequest(now = Date.now()): boolean {
  const fresh = askedAt > 0 && now - askedAt <= FRESH_MS;
  askedAt = 0;
  return fresh;
}
