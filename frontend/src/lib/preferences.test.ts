import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applyDisplay, createPrefsSaver, DEFAULT_PREFERENCES, mergePreferences, normalizePreferences, readLocalDisplay } from "./preferences";
import type { Preferences } from "./types";

describe("normalizing preferences", () => {
  it("gives the defaults for nothing or junk", () => {
    expect(normalizePreferences(undefined)).toEqual(DEFAULT_PREFERENCES);
    expect(normalizePreferences("x")).toEqual(DEFAULT_PREFERENCES);
    expect(normalizePreferences({ view: "grid", theme: "pink", text_size: "huge", density: "tiny", sort: "sideways", sidebar: 3, tab: "" })).toEqual(DEFAULT_PREFERENCES);
  });

  it("keeps good values, including the six filters", () => {
    const given = {
      view: "board", tab: "active", sort: "newest", filters_open: true, sidebar: "collapsed", theme: "dark", text_size: "larger", density: "compact",
      filters: { fit: "fits", match: "Strong", work: "remote", country: "MY", posting: "active", found: "week", extra: "x" },
    };
    const out = normalizePreferences(given);
    expect(out).toMatchObject({ view: "board", tab: "active", sort: "newest", filters_open: true, sidebar: "collapsed", theme: "dark", text_size: "larger", density: "compact" });
    expect(out.filters).toEqual({ fit: "fits", match: "Strong", work: "remote", country: "MY", posting: "active", found: "week" });
  });
});

describe("merging a change", () => {
  it("replaces the filters as a whole and leaves the rest", () => {
    const current: Preferences = { ...DEFAULT_PREFERENCES, view: "board", filters: { ...DEFAULT_PREFERENCES.filters, fit: "fits", work: "remote" } };
    const next = mergePreferences(current, { filters: { ...DEFAULT_PREFERENCES.filters, found: "today" } });
    expect(next.filters).toEqual({ ...DEFAULT_PREFERENCES.filters, found: "today" });
    expect(next.view).toBe("board");
    expect(mergePreferences(current, { sort: "oldest" }).filters).toEqual(current.filters);
    expect(current.filters.fit).toBe("fits"); // the original is untouched
  });
});

describe("the browser copy", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.text;
    delete document.documentElement.dataset.density;
  });

  it("puts the choices on the html element and mirrors them under the keys the first-paint script reads", () => {
    applyDisplay({ theme: "dark", text_size: "large", density: "compact", sidebar: "collapsed" });
    const root = document.documentElement;
    expect([root.dataset.theme, root.dataset.text, root.dataset.density]).toEqual(["dark", "large", "compact"]);
    expect([localStorage.getItem("so-theme"), localStorage.getItem("so-sidebar"), localStorage.getItem("so-text"), localStorage.getItem("so-density")]).toEqual(["dark", "collapsed", "large", "compact"]);
    applyDisplay({ theme: "light", text_size: "normal", density: "comfortable", sidebar: "expanded" });
    expect([root.dataset.theme, root.dataset.text, root.dataset.density]).toEqual([undefined, undefined, undefined]);
    expect(localStorage.getItem("so-theme")).toBe("light");
  });

  it("reads them back, with safe fallbacks", () => {
    expect(readLocalDisplay()).toEqual({ theme: "light", sidebar: "expanded", text_size: "normal", density: "comfortable" });
    localStorage.setItem("so-theme", "dark");
    localStorage.setItem("so-text", "larger");
    localStorage.setItem("so-density", "nonsense");
    expect(readLocalDisplay()).toMatchObject({ theme: "dark", text_size: "larger", density: "comfortable" });
    expect(
      readLocalDisplay(() => {
        throw new Error("blocked");
      }),
    ).toEqual({ theme: "light", sidebar: "expanded", text_size: "normal", density: "comfortable" });
  });
});

describe("saving changes", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const make = () => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const send = vi.fn(async (patch: object, _keepalive: boolean) => ({ ...DEFAULT_PREFERENCES, ...patch }) as Preferences);
    const onSaved = vi.fn();
    const onError = vi.fn();
    return { send, onSaved, onError, saver: createPrefsSaver({ send, onSaved, onError, delay: 400 }) };
  };

  it("sends changes made within 400 ms as one request, later values winning", () => {
    const { saver, send } = make();
    saver.queue({ view: "board" });
    vi.advanceTimersByTime(300);
    saver.queue({ sort: "oldest" });
    saver.queue({ view: "list" });
    vi.advanceTimersByTime(399);
    expect(send).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith({ view: "list", sort: "oldest" }, false);
  });

  it("remembers what is not yet confirmed, so a fresh read can be laid under it, and forgets it once saved", async () => {
    const { saver, onSaved } = make();
    saver.queue({ theme: "dark" });
    expect(saver.pending()).toEqual({ theme: "dark" });
    await vi.advanceTimersByTimeAsync(400);
    await vi.advanceTimersByTimeAsync(0);
    expect(saver.pending()).toEqual({});
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ theme: "dark" }), true);
  });

  it("sends at once when the page is being left, asking for the request to outlive the page", () => {
    const { saver, send } = make();
    saver.queue({ density: "compact" });
    saver.flush(true);
    expect(send).toHaveBeenCalledWith({ density: "compact" }, true);
    vi.advanceTimersByTime(1000);
    expect(send).toHaveBeenCalledTimes(1);
    saver.flush(true); // nothing waiting: nothing sent
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("reports a refusal", async () => {
    const { saver, send, onError, onSaved } = make();
    send.mockRejectedValueOnce(new Error("no"));
    saver.queue({ theme: "dark" });
    await vi.advanceTimersByTimeAsync(400);
    await vi.advanceTimersByTimeAsync(0);
    expect(onError).toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect(saver.pending()).toEqual({});
  });
});
