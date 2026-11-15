import React, { useState } from "react";
import { ScrollView, StyleSheet, TouchableOpacity, View } from "react-native";

import type { StatusInfo, ViewMode } from "../../api/dashboard";
import {
  COUNTRY_NOT_STATED, NOT_STATED, SORT_OPTIONS, countryOptions, isFiltered, selectedText, statusLabel,
  type Filters,
} from "../../screens/dashboard/logic";
import type { Job } from "../../api/dashboard";
import { radius } from "../../theme";
import { Button, Ionicons, Text, TextInput, Toggle, useStyles, useTheme } from "../../ui";
import { Sheet, type SheetOption } from "./Sheet";

export type Tab = { key: string; label: string; description: string; count: number };

/** "All" and one tab per stage with its count. The row scrolls sideways. */
export function StageTabs({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  const { colors } = useTheme();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }} contentContainerStyle={{ gap: 6 }} accessibilityRole="tablist">
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <TouchableOpacity
            key={t.key || "all"}
            onPress={() => onChange(t.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={{ minHeight: 44, paddingHorizontal: 14, justifyContent: "center", borderBottomWidth: 2, borderBottomColor: on ? colors.accent : "transparent" }}
          >
            <Text style={{ color: on ? colors.accent : colors.textMuted, fontWeight: "600" }}>{`${t.label}  ${t.count}`}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

function PickRow({ label, value, options, onChange }: { label: string; value: string; options: SheetOption<string>[]; onChange: (v: string) => void }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value)?.label ?? "Any";
  return (
    <>
      <TouchableOpacity onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel={`${label}: ${current}`} style={{ minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Text style={{ color: colors.textMuted }}>{label}</Text>
        <Text style={{ fontWeight: "600" }}>{current} ›</Text>
      </TouchableOpacity>
      <Sheet visible={open} title={label} options={options} value={value} onPick={onChange} onClose={() => setOpen(false)} />
    </>
  );
}

export function FilterPanel({
  filters, set, reset, jobs, bandLabels, inStage, shown, hidden,
}: {
  filters: Filters;
  set: (patch: Partial<Filters>) => void;
  reset: () => void;
  jobs: Job[];
  bandLabels: string[];
  inStage: number;
  shown: number;
  hidden: number;
}) {
  const { colors } = useTheme();
  const any = (extra: SheetOption<string>[]): SheetOption<string>[] => [{ value: "", label: "Any" }, ...extra];
  const countries = countryOptions(jobs);
  const filtered = isFiltered(filters);
  return (
    <View style={{ backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.card, paddingHorizontal: 14, paddingBottom: 12, marginBottom: 10 }}>
      <PickRow label="Fits your places" value={filters.fit} onChange={(v) => set({ fit: v as Filters["fit"] })} options={any([{ value: "fits", label: "Fits" }, { value: "check", label: "Check fit" }, { value: "unknown", label: "Fit unknown" }])} />
      <PickRow label="How well you match" value={filters.band} onChange={(v) => set({ band: v })} options={any([...bandLabels.map((l) => ({ value: l, label: l })), { value: NOT_STATED, label: "Not checked yet" }])} />
      <PickRow label="Work" value={filters.work} onChange={(v) => set({ work: v })} options={any([{ value: "remote", label: "Remote" }, { value: "hybrid", label: "Hybrid" }, { value: "onsite", label: "On-site" }, { value: NOT_STATED, label: "Not stated" }])} />
      <PickRow label="Country" value={filters.country} onChange={(v) => set({ country: v })} options={[{ value: "", label: "Anywhere" }, ...countries.map((c) => ({ value: c.code, label: c.name })), { value: COUNTRY_NOT_STATED, label: "Not stated" }]} />
      <PickRow label="Posting" value={filters.live} onChange={(v) => set({ live: v })} options={any([{ value: "active", label: "Open" }, { value: "expired", label: "Closed" }, { value: "uncertain", label: "Unclear" }, { value: "unknown", label: "Not checked" }])} />
      <PickRow label="Found" value={filters.found} onChange={(v) => set({ found: v as Filters["found"] })} options={[{ value: "", label: "Any time" }, { value: "today", label: "Today" }, { value: "week", label: "Last 7 days" }]} />
      <View style={{ marginTop: 12 }}>
        <Toggle label="Hide weak matches (under 40%)" hint="Jobs that have not been checked yet are always shown." value={filters.hideWeak} onChange={(v) => set({ hideWeak: v })} />
      </View>
      <Text style={{ color: colors.textMuted, fontSize: 13 }}>
        {filtered ? `Showing ${shown} of ${inStage}` : `Showing all ${inStage}`}
        {hidden > 0 ? ` (${hidden} hidden as weak ${hidden === 1 ? "match" : "matches"})` : ""}
      </Text>
      {filtered || filters.hideWeak ? <Button label="Clear filters" variant="ghost" onPress={reset} /> : null}
    </View>
  );
}

/** The search box, the sort order, the Filters button (with how many are set) and the List | Board switch. */
export function Toolbar({
  filters, set, open, onToggle, activeCount, view, onView,
}: {
  filters: Filters;
  set: (patch: Partial<Filters>) => void;
  open: boolean;
  onToggle: () => void;
  activeCount: number;
  view: ViewMode;
  onView: (v: ViewMode) => void;
}) {
  const { colors } = useTheme();
  const [sortOpen, setSortOpen] = useState(false);
  const s = useStyles((c) => StyleSheet.create({
    field: { minHeight: 44, borderWidth: 1, borderColor: c.border, borderRadius: radius.control, backgroundColor: c.surface, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 6 },
  }));
  const sort = SORT_OPTIONS.find((o) => o.value === filters.sort)?.label ?? "Sort";
  return (
    <View style={{ marginBottom: 10, gap: 8 }}>
      <View style={[s.field, { gap: 8 }]}>
        <Ionicons name="search" size={18} color={colors.textMuted} />
        <TextInput value={filters.q} onChangeText={(q) => set({ q })} placeholder="Search company, role or place" accessibilityLabel="Search your jobs" autoCorrect={false} autoCapitalize="none" style={{ flex: 1, fontSize: 15, paddingVertical: 10 }} />
        {filters.q ? (
          <TouchableOpacity onPress={() => set({ q: "" })} accessibilityLabel="Clear search" hitSlop={8}>
            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        ) : null}
      </View>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <TouchableOpacity style={[s.field, { flex: 1 }]} onPress={() => setSortOpen(true)} accessibilityRole="button" accessibilityLabel={`Sort by: ${sort}`}>
          <Ionicons name="swap-vertical" size={16} color={colors.textMuted} />
          <Text numberOfLines={1} style={{ flex: 1, fontSize: 13 }}>{sort}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.field, open && { borderColor: colors.accent }]} onPress={onToggle} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`Filters${activeCount ? `, ${activeCount} on` : ""}`}>
          <Ionicons name="options-outline" size={18} color={colors.text} />
          <Text style={{ fontWeight: "600" }}>{activeCount ? `Filters ${activeCount}` : "Filters"}</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: "row", borderWidth: 1, borderColor: colors.border, borderRadius: radius.control, overflow: "hidden" }} accessibilityRole="radiogroup">
          {(["list", "board"] as const).map((v) => (
            <TouchableOpacity key={v} onPress={() => onView(v)} accessibilityRole="button" accessibilityState={{ selected: view === v }} accessibilityLabel={v === "list" ? "List view" : "Board view"} style={{ width: 46, minHeight: 44, alignItems: "center", justifyContent: "center", backgroundColor: view === v ? colors.accent : colors.surface }}>
              <Ionicons name={v === "list" ? "list" : "albums-outline"} size={20} color={view === v ? colors.accentContrast : colors.text} />
            </TouchableOpacity>
          ))}
        </View>
      </View>
      <Sheet visible={sortOpen} title="Sort by" options={SORT_OPTIONS} value={filters.sort} onPick={(v) => set({ sort: v })} onClose={() => setSortOpen(false)} />
    </View>
  );
}

/** Shown while the person is choosing several jobs: how many, "all in this tab", and what to do with them. */
export function SelectionBar({
  count, total, allChecked, onToggleAll, statuses, canNotForMe, onNotForMe, onSetStatus, onArchive, onRemove, onCancel, busy,
}: {
  count: number;
  total: number;
  allChecked: boolean;
  onToggleAll: () => void;
  statuses: StatusInfo[];
  canNotForMe: boolean;
  onNotForMe: () => void;
  onSetStatus: (statusId: number) => void;
  onArchive: () => void;
  onRemove: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { colors } = useTheme();
  const [pick, setPick] = useState(false);
  const none = count === 0 || busy;
  return (
    <View style={{ backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.accent, borderRadius: radius.card, padding: 12, marginBottom: 10, gap: 8 }} accessibilityLabel="Actions for the chosen jobs">
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <Text style={{ fontWeight: "600" }}>{selectedText(count)}</Text>
        <TouchableOpacity onPress={onToggleAll} disabled={total === 0 || busy} style={{ minHeight: 44, justifyContent: "center" }} accessibilityRole="button">
          <Text style={{ color: colors.accent, fontWeight: "600" }}>{allChecked ? "Select none" : `Select all (${total})`}</Text>
        </TouchableOpacity>
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {canNotForMe ? <Button label="Not for me" variant="secondary" disabled={none} onPress={onNotForMe} /> : null}
        <Button label="Set status…" variant="secondary" disabled={none} onPress={() => setPick(true)} />
        <Button label="Archive" variant="secondary" disabled={none} onPress={onArchive} />
        <Button label="Remove…" variant="danger" disabled={none} onPress={onRemove} />
        <Button label="Cancel" variant="ghost" onPress={onCancel} />
      </View>
      <Sheet visible={pick} title="Set status for the chosen jobs" options={statuses.map((x) => ({ value: x.id, label: statusLabel(x), color: x.color }))} onPick={onSetStatus} onClose={() => setPick(false)} />
    </View>
  );
}

/** A short message with Undo after a status change; it goes away by itself. */
export function UndoBar({ text, onUndo, onDismiss, busy }: { text: string; onUndo: () => void; onDismiss: () => void; busy: boolean }) {
  const { colors } = useTheme();
  React.useEffect(() => {
    const t = setTimeout(onDismiss, 12000);
    return () => clearTimeout(t);
    // remounted with a new key for every change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={{ position: "absolute", left: 12, right: 12, bottom: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.good, borderRadius: radius.card, padding: 12, flexDirection: "row", alignItems: "center", gap: 10 }} accessibilityLiveRegion="polite">
      <Text style={{ flex: 1, fontSize: 14 }}>{text}</Text>
      <Button label={busy ? "Undoing…" : "Undo"} variant="secondary" disabled={busy} onPress={onUndo} />
      <TouchableOpacity onPress={onDismiss} accessibilityLabel="Dismiss" hitSlop={10}>
        <Ionicons name="close" size={20} color={colors.textMuted} />
      </TouchableOpacity>
    </View>
  );
}
