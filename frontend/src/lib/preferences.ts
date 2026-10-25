import type { Density, PreferencePatch, Preferences, PrefFilters, SortKey, TextSize, Theme, ViewMode } from "./types";

/** What a person gets before they have chosen anything (the same defaults the server uses). */
export const DEFAULT_PREFERENCES: Preferences = {
  view: "list",
  tab: "all",
  sort: "best",
  filters_open: false,
  ai_prompt_dismissed: false,
  tz_prompt_dismissed: false,
  hide_weak: false,
  filters: { fit: "", match: "", work: "", country: "", posting: "", found: "" },
  sidebar: "expanded",
  theme: "light",
  text_size: "normal",
  density: "comfortable",
};

export const SORT_KEYS: SortKey[] = ["best", "newest", "oldest", "company", "deadline"];
const VIEWS: ViewMode[] = ["list", "board"];
const TEXT_SIZES: TextSize[] = ["normal", "large", "larger"];
const DENSITIES: Density[] = ["comfortable", "compact"];
const THEMES: Theme[] = ["light", "dark"];
const FILTER_KEYS = Object.keys(DEFAULT_PREFERENCES.filters) as (keyof PrefFilters)[];

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

/** Whatever came from the server or from storage, made safe: unknown or missing values fall back to the defaults. */
export function normalizePreferences(raw: unknown): Preferences {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const f = (r.filters && typeof r.filters === "object" ? r.filters : {}) as Record<string, unknown>;
  const filters = { ...DEFAULT_PREFERENCES.filters };
  for (const key of FILTER_KEYS) if (typeof f[key] === "string") filters[key] = f[key] as string;
  return {
    view: pick(r.view, VIEWS, DEFAULT_PREFERENCES.view),
    tab: typeof r.tab === "string" && r.tab ? r.tab : DEFAULT_PREFERENCES.tab,
    sort: pick(r.sort, SORT_KEYS, DEFAULT_PREFERENCES.sort),
    filters_open: r.filters_open === true,
    ai_prompt_dismissed: r.ai_prompt_dismissed === true,
    tz_prompt_dismissed: r.tz_prompt_dismissed === true,
    hide_weak: r.hide_weak === true,
    filters,
    sidebar: r.sidebar === "collapsed" ? "collapsed" : "expanded",
    theme: pick(r.theme, THEMES, DEFAULT_PREFERENCES.theme),
    text_size: pick(r.text_size, TEXT_SIZES, DEFAULT_PREFERENCES.text_size),
    density: pick(r.density, DENSITIES, DEFAULT_PREFERENCES.density),
  };
}

/** A change on top of what is there. `filters` is replaced as a whole, the same rule the server has. */
export function mergePreferences(current: Preferences, patch: PreferencePatch): Preferences {
  return { ...current, ...patch, filters: patch.filters ? { ...patch.filters } : current.filters };
}

// ---- the browser's own copy, so the very first paint is right ---------------------------------------------------------------

export const LOCAL_KEYS = { theme: "so-theme", sidebar: "so-sidebar", text: "so-text", density: "so-density" } as const;

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private window: not mirrored, the server still has it */
  }
}

/** Puts the display choices on <html> (colour, text size, density) and mirrors them where the inline script in layout.tsx reads them. */
export function applyDisplay(prefs: Pick<Preferences, "theme" | "text_size" | "density" | "sidebar">, root: HTMLElement = document.documentElement) {
  if (prefs.theme === "dark") root.dataset.theme = "dark";
  else delete root.dataset.theme;
  if (prefs.text_size === "normal") delete root.dataset.text;
  else root.dataset.text = prefs.text_size;
  if (prefs.density === "compact") root.dataset.density = "compact";
  else delete root.dataset.density;
  store(LOCAL_KEYS.theme, prefs.theme);
  store(LOCAL_KEYS.sidebar, prefs.sidebar);
  store(LOCAL_KEYS.text, prefs.text_size);
  store(LOCAL_KEYS.density, prefs.density);
}

/** The mirrored display choices, for before the server has answered. */
export function readLocalDisplay(read: (key: string) => string | null = (k) => localStorage.getItem(k)): Pick<Preferences, "theme" | "text_size" | "density" | "sidebar"> {
  const get = (k: string) => {
    try {
      return read(k);
    } catch {
      return null;
    }
  };
  return {
    theme: pick(get(LOCAL_KEYS.theme), THEMES, "light"),
    sidebar: get(LOCAL_KEYS.sidebar) === "collapsed" ? "collapsed" : "expanded",
    text_size: pick(get(LOCAL_KEYS.text), TEXT_SIZES, "normal"),
    density: pick(get(LOCAL_KEYS.density), DENSITIES, "comfortable"),
  };
}

// ---- saving: changes within 400 ms go out as one request --------------------------------------------------------------------

export type PrefsSaver = {
  /** Remember a change; it is sent after the delay with everything that came in meanwhile. */
  queue: (patch: PreferencePatch) => void;
  /** Send now (the page is being left). */
  flush: (keepalive?: boolean) => void;
  /** What has been changed here but not yet confirmed by the server, to lay over a fresh read. */
  pending: () => PreferencePatch;
};

export function createPrefsSaver(opts: {
  send: (patch: PreferencePatch, keepalive: boolean) => Promise<Preferences>;
  onSaved: (server: Preferences, settled: boolean) => void;
  onError: (error: unknown) => void;
  delay?: number;
}): PrefsSaver {
  const delay = opts.delay ?? 400;
  let waiting: PreferencePatch = {};
  let sending: PreferencePatch = {};
  let inFlight = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const has = (p: PreferencePatch) => Object.keys(p).length > 0;
  const join = (a: PreferencePatch, b: PreferencePatch): PreferencePatch => ({ ...a, ...b });

  const flush = (keepalive = false) => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (!has(waiting)) return;
    const patch = waiting;
    waiting = {};
    sending = join(sending, patch);
    inFlight += 1;
    opts
      .send(patch, keepalive)
      .then((server) => {
        inFlight -= 1;
        if (inFlight === 0) sending = {};
        opts.onSaved(server, inFlight === 0 && !has(waiting));
      })
      .catch((error) => {
        inFlight -= 1;
        if (inFlight === 0) sending = {};
        opts.onError(error);
      });
  };

  return {
    queue(patch) {
      waiting = join(waiting, patch);
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => flush(false), delay);
    },
    flush,
    pending: () => join(sending, waiting),
  };
}
