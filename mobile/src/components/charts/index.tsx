// Small, generic charts drawn with react-native-svg and themed through useTheme (series colours come from `colors.chart`).
// Other screens may reuse them. Every label is drawn as plain text (never interpreted as markup), and every chart also states its numbers
// as text (a value next to each bar, an accessibilityLabel on the whole figure), so nothing is told by colour alone.
//
//   <StatTile label value note? onPress? />                     a big number in a soft tile
//   <BarList items=[{label,value,color?}] />                    horizontal bars, one row per item
//   <GroupedBars groups=[{label, values:number[]}] series=[{label}] />   a block of bars per group (eg. per week)
//   <LineChart labels series=[{label,values}] />                lines over shared labels (eg. per month)
//   <Donut slices=[{label,value,color?}] centerLabel? />        share of a whole, with a legend
//   <Heatmap weeks=[[{date,level,text}|null]] />                 calendar heat grid, Monday first, level 0 to 4
//   <FunnelBars stages=[{label,count,share?}] />                 steps that narrow, each with its count
//   <Ring done target label />                                   a progress ring
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import Svg, { Circle, G, Path, Polyline, Rect } from "react-native-svg";

import { radius } from "../../theme";
import { Text, useStyles, useTheme } from "../../ui";

/** One horizontal bar width: a real but tiny value still shows a sliver, so "1" never looks like "0". */
export function barPercent(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.min(100, Math.max(4, Math.round((100 * value) / max)));
}

const maxOf = (values: number[]) => Math.max(1, ...values);

export function StatTile({ label, value, note }: { label: string; value: number | string; note?: string }) {
  const s = useStyles((c) => ({
    tile: { flexGrow: 1, flexBasis: "46%", backgroundColor: c.surface, borderRadius: radius.card, borderWidth: 1, borderColor: c.border, padding: 14 },
    value: { fontSize: 28, fontWeight: "700", letterSpacing: -0.5 },
    label: { color: c.textMuted, fontSize: 13 },
    note: { color: c.textMuted, fontSize: 12, marginTop: 2 },
  })) as unknown as Record<string, never>;
  return (
    <View style={s.tile} accessible accessibilityLabel={`${label}: ${value}${note ? `, ${note}` : ""}`}>
      <Text style={s.value}>{value}</Text>
      <Text style={s.label}>{label}</Text>
      {note ? <Text style={s.note}>{note}</Text> : null}
    </View>
  );
}

export type BarItem = { label: string; value: number; color?: string };

/** One row: label, a track with the filled part, the number as text. */
function BarRow({ label, value, max, color }: { label: string; value: number; max: number; color?: string }) {
  const { colors } = useTheme();
  const width = barPercent(value, max);
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <Text numberOfLines={1} style={{ width: 104, fontSize: 12, color: colors.textMuted }}>
        {label}
      </Text>
      <View style={{ flex: 1, height: 12, borderRadius: 6, backgroundColor: colors.surfaceAlt, overflow: "hidden" }}>
        <View style={{ width: `${width}%`, height: 12, borderRadius: 6, backgroundColor: color ?? colors.chart[0] }} />
      </View>
      <Text style={{ width: 34, textAlign: "right", fontSize: 12, fontWeight: "700" }}>{value}</Text>
    </View>
  );
}

export function BarList({ items, caption }: { items: BarItem[]; caption?: string }) {
  const max = maxOf(items.map((i) => i.value));
  return (
    <View accessible accessibilityLabel={`${caption ?? "Chart"}: ${items.map((i) => `${i.label} ${i.value}`).join(", ")}`}>
      {caption ? <Text style={{ fontSize: 13, fontWeight: "600", marginBottom: 8 }}>{caption}</Text> : null}
      {items.map((i, n) => (
        <BarRow key={`${i.label}-${n}`} label={i.label} value={i.value} max={max} color={i.color} />
      ))}
    </View>
  );
}

/** A block of one bar per series for each group (for example found / checked / applied for each week). */
export function GroupedBars({ groups, series, caption }: { groups: { label: string; values: number[] }[]; series: { label: string }[]; caption?: string }) {
  const { colors } = useTheme();
  const max = maxOf(groups.flatMap((g) => g.values));
  return (
    <View accessible accessibilityLabel={`${caption ?? "Chart"}: ${groups.map((g) => `${g.label}, ${g.values.map((v, i) => `${series[i]?.label} ${v}`).join(", ")}`).join("; ")}`}>
      {caption ? <Text style={{ fontSize: 13, fontWeight: "600", marginBottom: 8 }}>{caption}</Text> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14, marginBottom: 10 }}>
        {series.map((s, i) => (
          <View key={s.label} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <View style={{ width: 14, height: 10, borderRadius: 3, backgroundColor: colors.chart[i % colors.chart.length] }} />
            <Text style={{ fontSize: 12 }}>{s.label}</Text>
          </View>
        ))}
      </View>
      {groups.map((g) => (
        <View key={g.label} style={{ marginBottom: 10 }}>
          <Text style={{ fontSize: 12, fontWeight: "600", marginBottom: 3 }}>{g.label}</Text>
          {g.values.map((v, i) => (
            <BarRow key={i} label={series[i]?.label ?? ""} value={v} max={max} color={colors.chart[i % colors.chart.length]} />
          ))}
        </View>
      ))}
    </View>
  );
}

/** Lines over shared labels (x axis). Drawn at the width the screen gives it. */
export function LineChart({ labels, series, height = 150, caption }: { labels: string[]; series: { label: string; values: number[] }[]; height?: number; caption?: string }) {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const max = maxOf(series.flatMap((s) => s.values));
  const padX = 14;
  const padTop = 8;
  const padBottom = 6;
  const plotW = Math.max(0, width - padX * 2);
  const plotH = height - padTop - padBottom;
  const x = (i: number) => padX + (labels.length <= 1 ? plotW / 2 : (plotW * i) / (labels.length - 1));
  const y = (v: number) => padTop + plotH - (plotH * v) / max;
  return (
    <View accessible accessibilityLabel={`${caption ?? "Chart"}: ${series.map((s) => `${s.label} ${s.values.join(", ")}`).join("; ")}, over ${labels.join(", ")}`}>
      {caption ? <Text style={{ fontSize: 13, fontWeight: "600", marginBottom: 8 }}>{caption}</Text> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 14, marginBottom: 6 }}>
        {series.map((s, i) => (
          <View key={s.label} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <View style={{ width: 14, height: 4, borderRadius: 2, backgroundColor: colors.chart[i % colors.chart.length] }} />
            <Text style={{ fontSize: 12 }}>{s.label}</Text>
          </View>
        ))}
      </View>
      <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ height }}>
        {width > 0 ? (
          <Svg width={width} height={height}>
            {[0, 0.5, 1].map((f) => (
              <Rect key={f} x={padX} y={padTop + plotH * f} width={plotW} height={1} fill={colors.border} />
            ))}
            {series.map((s, si) => {
              const color = colors.chart[si % colors.chart.length];
              return (
                <G key={s.label}>
                  <Polyline points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
                  {s.values.map((v, i) => (
                    <Circle key={i} cx={x(i)} cy={y(v)} r={3.5} fill={color} />
                  ))}
                </G>
              );
            })}
          </Svg>
        ) : null}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 4, marginTop: 2 }}>
        {labels.map((l) => (
          <Text key={l} style={{ fontSize: 11, color: colors.textMuted }}>
            {l}
          </Text>
        ))}
      </View>
    </View>
  );
}

export type Slice = { label: string; value: number; color?: string };

/** Share of a whole as a ring, with a legend that gives every number as text. */
export function Donut({ slices, centerLabel, size = 140 }: { slices: Slice[]; centerLabel?: string; size?: number }) {
  const { colors } = useTheme();
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const r = size / 2 - 14;
  const circumference = 2 * Math.PI * r;
  let offset = 0;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 16, flexWrap: "wrap" }} accessible accessibilityLabel={`Share: ${slices.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
      <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
        <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <G rotation={-90} origin={`${size / 2}, ${size / 2}`}>
            <Circle cx={size / 2} cy={size / 2} r={r} stroke={colors.surfaceAlt} strokeWidth={16} fill="none" />
            {total > 0
              ? slices.map((s, i) => {
                  const len = (s.value / total) * circumference;
                  const el = (
                    <Circle
                      key={`${s.label}-${i}`}
                      cx={size / 2}
                      cy={size / 2}
                      r={r}
                      stroke={s.color ?? colors.chart[i % colors.chart.length]}
                      strokeWidth={16}
                      fill="none"
                      strokeDasharray={`${len} ${circumference - len}`}
                      strokeDashoffset={-offset}
                    />
                  );
                  offset += len;
                  return el;
                })
              : null}
          </G>
        </Svg>
        {centerLabel ? <Text style={{ position: "absolute", fontSize: 20, fontWeight: "700" }}>{centerLabel}</Text> : null}
      </View>
      <View style={{ flex: 1, minWidth: 140 }}>
        {slices.map((s, i) => (
          <View key={`${s.label}-${i}`} style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: s.color ?? colors.chart[i % colors.chart.length] }} />
            <Text style={{ flex: 1, fontSize: 13 }}>{s.label}</Text>
            <Text style={{ fontSize: 13, fontWeight: "700" }}>{s.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export type HeatCellView = { date: string; level: 0 | 1 | 2 | 3 | 4; text: string };

const STEPS = [0, 0.25, 0.45, 0.7, 1]; // opacity of the accent colour for each level

/** Calendar heat grid: one column per week (Monday first), colour from the accent. Tap a day to read its numbers. */
export function Heatmap({ weeks, onPick, cell = 13 }: { weeks: (HeatCellView | null)[][]; onPick?: (c: HeatCellView) => void; cell?: number }) {
  const { colors } = useTheme();
  const gap = 3;
  const width = weeks.length * (cell + gap);
  const height = 7 * (cell + gap);
  const [picked, setPicked] = useState<string>("");
  return (
    <View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} ref={(r) => r?.scrollToEnd({ animated: false })}>
        <Svg width={width} height={height}>
          {weeks.map((week, wi) =>
            week.map((c, di) =>
              c ? (
                <G key={`${wi}-${di}`}>
                  <Rect x={wi * (cell + gap)} y={di * (cell + gap)} width={cell} height={cell} rx={3} fill={colors.surfaceAlt} />
                  {c.level > 0 ? <Rect x={wi * (cell + gap)} y={di * (cell + gap)} width={cell} height={cell} rx={3} fill={colors.accent} opacity={STEPS[c.level]} /> : null}
                  <Rect
                    x={wi * (cell + gap)}
                    y={di * (cell + gap)}
                    width={cell}
                    height={cell}
                    rx={3}
                    fill="transparent"
                    onPress={() => {
                      setPicked(c.text);
                      onPick?.(c);
                    }}
                  />
                </G>
              ) : null,
            ),
          )}
        </Svg>
      </ScrollView>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 8 }}>
        <Text style={{ fontSize: 11, color: colors.textMuted }}>Fewer</Text>
        {STEPS.map((o, i) => (
          <View key={i} style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: colors.surfaceAlt, overflow: "hidden" }}>
            <View style={{ flex: 1, backgroundColor: colors.accent, opacity: o }} />
          </View>
        ))}
        <Text style={{ fontSize: 11, color: colors.textMuted }}>More</Text>
      </View>
      {picked ? <Text style={{ fontSize: 13, marginTop: 8 }}>{picked}</Text> : <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 8 }}>Tap a square to read that day.</Text>}
    </View>
  );
}

/** Steps that narrow (sent, heard back, interview, offer), each with its count and its share of the step before. */
export function FunnelBars({ stages }: { stages: { label: string; count: number; share?: string }[] }) {
  const { colors } = useTheme();
  const max = maxOf(stages.map((s) => s.count));
  return (
    <View accessible accessibilityLabel={`Funnel: ${stages.map((s) => `${s.label} ${s.share ?? s.count}`).join(", ")}`}>
      {stages.map((s, i) => (
        <View key={s.label} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 3 }}>
            <Text style={{ fontSize: 13 }}>{s.label}</Text>
            <Text style={{ fontSize: 13, fontWeight: "700" }}>{s.share ?? s.count}</Text>
          </View>
          <View style={{ height: 18, borderRadius: 9, backgroundColor: colors.surfaceAlt, overflow: "hidden" }}>
            <View style={{ width: `${barPercent(s.count, max)}%`, height: 18, borderRadius: 9, backgroundColor: colors.chart[i % colors.chart.length] }} />
          </View>
        </View>
      ))}
    </View>
  );
}

/** A progress ring: fills as `done` approaches `target`; the figure is also printed in the middle. */
export function Ring({ done, target, label, size = 68 }: { done: number; target: number; label: string; size?: number }) {
  const { colors } = useTheme();
  const pct = target <= 0 ? 0 : Math.min(1, done / target);
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }} accessible accessibilityLabel={`${label}: ${done} of ${target}`}>
      <Svg width={size} height={size}>
        <G rotation={-90} origin={`${size / 2}, ${size / 2}`}>
          <Circle cx={size / 2} cy={size / 2} r={r} stroke={colors.surfaceAlt} strokeWidth={7} fill="none" />
          <Circle cx={size / 2} cy={size / 2} r={r} stroke={colors.accent} strokeWidth={7} fill="none" strokeLinecap="round" strokeDasharray={`${c * pct} ${c}`} />
        </G>
      </Svg>
      <Text style={{ position: "absolute", fontSize: 13, fontWeight: "700" }}>
        {done}/{target}
      </Text>
    </View>
  );
}

// Path is re-exported so a screen that needs a custom shape does not import react-native-svg a second time for one element.
export { Path };
