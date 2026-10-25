import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Reads the colour tokens straight from globals.css and checks that the pairs the screens really use reach WCAG AA (4.5:1 for text).

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

type Rgba = [number, number, number, number];

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}

function parse(value: string): Rgba {
  const hex = /^#([0-9a-f]{6})$/i.exec(value);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)).concat(1) as Rgba;
  const rgba = /^rgba?\(([^)]+)\)$/.exec(value);
  if (rgba) {
    const p = rgba[1].split(",").map((x) => parseFloat(x));
    return [p[0], p[1], p[2], p[3] ?? 1];
  }
  throw new Error(`cannot read ${value}`);
}

const over = (top: Rgba, under: Rgba): Rgba => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1) as Rgba;

function luminance([r, g, b]: Rgba) {
  const [R, G, B] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

export function ratio(a: Rgba, b: Rgba) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const light = block(":root");
const dark = { ...light, ...block(':root[data-theme="dark"]') };

function pairs(tokens: Record<string, string>) {
  const get = (name: string) => parse(tokens[name]);
  const surfaces = { bg: get("bg"), surface: get("surface"), "surface-2": get("surface-2") };
  // A translucent brand-soft sits on whatever the card is on.
  const soft = (under: Rgba) => over(get("brand-soft"), under);
  const grounds: Record<string, Rgba> = { ...surfaces, "brand-soft on surface": soft(surfaces.surface), "brand-soft on bg": soft(surfaces.bg) };
  const out: { name: string; fg: Rgba; bg: Rgba }[] = [];
  for (const [gName, g] of Object.entries(grounds)) {
    for (const t of ["text", "muted", "brand", "good", "warn", "bad"]) out.push({ name: `${t} on ${gName}`, fg: get(t), bg: g });
  }
  out.push({ name: "brand-contrast on brand", fg: get("brand-contrast"), bg: get("brand") });
  return out;
}

describe.each([
  ["light", light],
  ["dark", dark],
])("colour contrast, %s theme", (_name, tokens) => {
  for (const p of pairs(tokens)) {
    it(`${p.name} is at least 4.5:1`, () => {
      expect(ratio(p.fg, p.bg)).toBeGreaterThanOrEqual(4.5);
    });
  }
});

describe("the Tailwind scales used for text in the sidebar and the avatar", () => {
  const theme = Object.fromEntries([...css.matchAll(/--color-([\w-]+):\s*(#[0-9a-f]{6});/gi)].map((m) => [m[1], parse(m[2])]));
  it("gray-500 (sidebar group headings, icons) reads on white and on gray-100", () => {
    expect(ratio(theme["gray-500"], parse("#ffffff"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(theme["gray-500"], theme["gray-100"])).toBeGreaterThanOrEqual(4.5);
  });
  it("the active menu entry (brand-600 on brand-50) reads", () => {
    expect(ratio(theme["brand-600"], theme["brand-50"])).toBeGreaterThanOrEqual(4.5);
  });
  it("the dark sidebar headings (gray-400 on gray-900) read", () => {
    expect(ratio(theme["gray-400"], theme["gray-900"])).toBeGreaterThanOrEqual(4.5);
  });
  it("the helper itself: black on white is 21:1", () => {
    expect(Math.round(ratio([0, 0, 0, 1], [255, 255, 255, 1]))).toBe(21);
  });
});
