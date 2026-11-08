// The website's colours, exactly (see /design.md and frontend/src/app/globals.css): Bento Grid in light mode, Dark Command Center in
// dark mode, one olive/lime accent tuned per mode, radius 12/18, Albert Sans. Dark is the default until the person (or the site's
// own default, Site configuration > Appearance) says otherwise.
export type Palette = {
  background: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  accent: string;
  accentSoft: string;
  accentContrast: string; // text on a filled accent button
  good: string;
  warn: string;
  danger: string;
  chart: string[]; // the six category colours, the same in both modes
};

const chart = ["#5b8c3f", "#c97a2e", "#3f8fa8", "#8a5fb0", "#b2555f", "#6b6b63"];

export const palettes: Record<"light" | "dark", Palette> = {
  light: {
    background: "#f2f2f0",
    surface: "#ffffff",
    surfaceAlt: "#e9e9e6",
    border: "#e3e3e0",
    text: "#16160f",
    textMuted: "#68685f",
    accent: "#4a6400",
    accentSoft: "#eef2df",
    accentContrast: "#ffffff",
    good: "#2f6239",
    warn: "#8f5518",
    danger: "#a8443a",
    chart,
  },
  dark: {
    background: "#0a0a0b",
    surface: "#141416",
    surfaceAlt: "#1c1c1f",
    border: "#232326",
    text: "#e8e8ea",
    textMuted: "#a0a0a6",
    accent: "#c6ff3d",
    accentSoft: "rgba(198, 255, 61, 0.12)",
    accentContrast: "#0a0a0b",
    good: "#7ad184",
    warn: "#e0a458",
    danger: "#e08478",
    chart,
  },
};

export type Mode = "light" | "dark";

/** The website's corner radii: 12 for controls, 18 for cards (tiles). */
export const radius = { control: 12, card: 18, pill: 999 };

/** Kept for code that cannot use a hook (module-level constants): always the dark palette. Prefer `useTheme().colors`. */
export const colors = palettes.dark;
