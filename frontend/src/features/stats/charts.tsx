import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { barPercent, maxOf, weekLabel } from "./logic";

/**
 * A chart is a figure with a caption. What is drawn is hidden from screen readers (aria-hidden) and replaced by a table with the same
 * numbers, which is visually hidden. Every bar also carries its number as text, so no value is told by colour or length alone.
 */
export function Chart({ caption, table, children }: { caption: string; table: ReactNode; children: ReactNode }) {
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 text-theme-sm font-medium">{caption}</figcaption>
      <div aria-hidden>{children}</div>
      <div className="sr-only">{table}</div>
    </figure>
  );
}

/** One horizontal bar: label, a track with the filled part, and the number as text. */
export function Bar({ label, value, max, fill, pattern = "solid", className }: { label: ReactNode; value: number; max: number; fill?: string; pattern?: "solid" | "striped" | "outline"; className?: string }) {
  const width = barPercent(value, max);
  return (
    <div className={cn("flex items-center gap-2 text-theme-xs", className)}>
      <span className="w-24 shrink-0 truncate text-muted sm:w-32" title={typeof label === "string" ? label : undefined}>
        {label}
      </span>
      <span className="relative h-3 min-w-0 flex-1 overflow-hidden rounded bg-surface-2">
        <span
          className={cn("absolute inset-y-0 left-0 rounded", pattern === "solid" && "bg-brand", pattern === "outline" && "border-2 border-brand bg-transparent")}
          style={{
            width: `${width}%`,
            ...(fill && pattern !== "outline" ? { background: fill } : {}),
            ...(pattern === "striped" ? { backgroundImage: "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 3px, transparent 3px 6px)", backgroundColor: fill ?? "var(--brand)" } : {}),
          }}
        />
      </span>
      <span className="w-8 shrink-0 text-right font-medium tabular-nums">{value}</span>
    </div>
  );
}

const SERIES = [
  { key: "found", label: "Found", pattern: "solid" },
  { key: "checked", label: "Fit checked", pattern: "striped" },
  { key: "applied", label: "Applied", pattern: "outline" },
] as const;

/** The last eight weeks as grouped bars: for each week, found, fit checked and applied. */
export function WeeklyChart({ weekly }: { weekly: { start: string; found: number; checked: number; applied: number }[] }) {
  const max = maxOf(weekly.flatMap((w) => [w.found, w.checked, w.applied]));
  return (
    <Chart
      caption="Jobs found, fits checked and applications sent, week by week (oldest first)"
      table={
        <table>
          <caption>Weekly numbers</caption>
          <thead>
            <tr>
              <th scope="col">Week</th>
              {SERIES.map((s) => (
                <th key={s.key} scope="col">
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weekly.map((w) => (
              <tr key={w.start}>
                <th scope="row">{weekLabel(w.start)}</th>
                <td>{w.found}</td>
                <td>{w.checked}</td>
                <td>{w.applied}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-theme-xs">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-5 rounded" style={swatch(s.pattern)} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="space-y-3">
        {weekly.map((w) => (
          <div key={w.start} className="space-y-0.5">
            <p className="text-theme-xs font-medium">{weekLabel(w.start)}</p>
            {SERIES.map((s) => (
              <Bar key={s.key} label={s.label} value={w[s.key]} max={max} pattern={s.pattern} />
            ))}
          </div>
        ))}
      </div>
    </Chart>
  );
}

function swatch(pattern: "solid" | "striped" | "outline"): React.CSSProperties {
  if (pattern === "solid") return { background: "var(--brand)" };
  if (pattern === "outline") return { border: "2px solid var(--brand)" };
  return { backgroundColor: "var(--brand)", backgroundImage: "repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 3px, transparent 3px 6px)" };
}

/** A short list of labelled bars (kinds of work, countries, bands). */
export function BarList({ caption, items, unit, fills }: { caption: string; items: { label: string; value: number }[]; unit: string; fills?: (string | undefined)[] }) {
  const max = maxOf(items.map((i) => i.value));
  return (
    <Chart
      caption={caption}
      table={
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">{unit}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.label}>
                <th scope="row">{i.label}</th>
                <td>{i.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div className="space-y-1.5">
        {items.map((i, n) => (
          <Bar key={i.label} label={i.label} value={i.value} max={max} fill={fills?.[n]} />
        ))}
      </div>
    </Chart>
  );
}
