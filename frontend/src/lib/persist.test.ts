import type { PersistedClient } from "@tanstack/react-query-persist-client";
import { describe, expect, it } from "vitest";
import { APP_BUSTER, CACHE_KEY, cacheBuster, clearPersistedStorage, readUid, shouldPersistKey, trimToLimit, UID_KEY, writeUid } from "./persist";

const store = () => {
  const data = new Map<string, string>();
  return { data, getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) };
};

describe("the cache key per person", () => {
  it("has its own buster for each person and for nobody yet, tied to the app version", () => {
    expect(cacheBuster(7)).toBe(`${APP_BUSTER}:7`);
    expect(cacheBuster(8)).not.toBe(cacheBuster(7));
    expect(cacheBuster(null)).toBe(`${APP_BUSTER}:anon`);
  });

  it("remembers whose cache this tab holds, and ignores a broken value", () => {
    const s = store();
    expect(readUid(s)).toBeNull();
    writeUid(s, 42);
    expect(readUid(s)).toBe(42);
    s.data.set(UID_KEY, "abc");
    expect(readUid(s)).toBeNull();
    s.data.set(UID_KEY, "-3");
    expect(readUid(s)).toBeNull();
    expect(readUid(null)).toBeNull();
  });
});

describe("clearing", () => {
  it("removes the cache and whose it was (sign-out, or the session ended)", () => {
    const s = store();
    s.data.set(CACHE_KEY, "{}");
    s.data.set(UID_KEY, "5");
    s.data.set("so-theme", "dark");
    clearPersistedStorage(s);
    expect([...s.data.keys()]).toEqual(["so-theme"]);
    expect(() => clearPersistedStorage(null)).not.toThrow();
    expect(() =>
      clearPersistedStorage({
        removeItem: () => {
          throw new Error("blocked");
        },
      }),
    ).not.toThrow();
  });
});

describe("what is kept", () => {
  it("never keeps live progress", () => {
    expect(shouldPersistKey(["dashboard"])).toBe(true);
    expect(shouldPersistKey(["me"])).toBe(true);
    expect(shouldPersistKey(["scan-log", "x"])).toBe(false);
    expect(shouldPersistKey(["scan"])).toBe(false);
    expect(shouldPersistKey(["liveness"])).toBe(false);
  });

  type Q = PersistedClient["clientState"]["queries"][number];
  const q = (key: string, size: number) => ({ queryKey: [key], queryHash: key, state: { data: "x".repeat(size) } }) as unknown as Q;
  const client = (...queries: Q[]): PersistedClient => ({ timestamp: 1, buster: "b", clientState: { mutations: [], queries } });

  it("stays as it is when small", () => {
    const small = client(q("me", 10), q("dashboard", 10));
    expect(trimToLimit(small, 10_000)).toBe(small);
  });

  it("falls back to only who is signed in (and their preferences) when too big", () => {
    const big = client(q("me", 10), q("dashboard", 5000));
    const out = trimToLimit(big, 1000);
    expect(out.clientState.queries.map((x) => x.queryKey[0])).toEqual(["me"]);
    expect(out.buster).toBe("b");
  });
});
