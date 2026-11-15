// Small pieces the pipeline screens share: a date/time field, a pick-many list, the "move this job?" suggestion, a copy button, a form sheet.
import DateTimePicker, { DateTimePickerAndroid, type DateTimePickerEvent } from "@react-native-community/datetimepicker";
import * as Clipboard from "expo-clipboard";
import React, { useState } from "react";
import { Modal, Platform, Pressable, ScrollView, TouchableOpacity, View } from "react-native";

import { pipelineApi, type SuggestStatus } from "../../api/pipeline";
import { Button, Card, Muted, notify, Row, Text, useStyles, useTheme, Ionicons } from "../../ui";
import { errorText } from "../../ui/useApi";
import { fromInput, toDayInput, toLocalInput, whenLabel, dayLabel } from "./logic";

/** A field showing a date (or a date and time) and opening the phone's own picker. `value` is "YYYY-MM-DD" or "YYYY-MM-DDTHH:mm" ("" = not set). */
export function DateField({ label, value, onChange, withTime = false, hint, error, clearable = false }: {
  label: string; value: string; onChange: (v: string) => void; withTime?: boolean; hint?: string; error?: string; clearable?: boolean;
}) {
  const { colors, mode } = useTheme();
  const s = useStyles((c) => ({
    label: { color: c.textMuted, fontSize: 13, marginBottom: 6, fontWeight: "600" },
    box: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.border, borderRadius: 12, paddingHorizontal: 14, minHeight: 46, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    sheet: { backgroundColor: c.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 18 },
  })) as unknown as Record<string, never>;
  const [iosOpen, setIosOpen] = useState(false);
  const emit = (d: Date) => onChange(withTime ? toLocalInput(d) : toDayInput(d));
  const shown = value ? (withTime ? whenLabel(value) : dayLabel(value)) : "Choose…";

  const open = () => {
    const current = fromInput(value);
    if (Platform.OS === "android") {
      DateTimePickerAndroid.open({
        value: current,
        mode: "date",
        onChange: (e: DateTimePickerEvent, date?: Date) => {
          if (e.type !== "set" || !date) return;
          if (!withTime) return emit(date);
          DateTimePickerAndroid.open({
            value: date,
            mode: "time",
            is24Hour: true,
            onChange: (e2: DateTimePickerEvent, time?: Date) => {
              if (e2.type !== "set" || !time) return;
              const merged = new Date(date);
              merged.setHours(time.getHours(), time.getMinutes(), 0, 0);
              emit(merged);
            },
          });
        },
      });
    } else {
      if (!value) emit(current);
      setIosOpen(true);
    }
  };
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <View style={[s.box, error ? { borderColor: colors.danger } : null]}>
        <TouchableOpacity onPress={open} accessibilityRole="button" accessibilityLabel={`${label}: ${shown}`} style={{ flex: 1, minHeight: 44, justifyContent: "center" }}>
          <Text style={{ color: value ? colors.text : colors.textMuted }}>{shown}</Text>
        </TouchableOpacity>
        {clearable && value ? (
          <TouchableOpacity onPress={() => onChange("")} accessibilityLabel={`Clear ${label}`} hitSlop={10}>
            <Ionicons name="close-circle" size={20} color={colors.textMuted} />
          </TouchableOpacity>
        ) : null}
      </View>
      {error ? <Text style={{ color: colors.danger, fontSize: 12, marginTop: 5 }}>{error}</Text> : hint ? <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 5 }}>{hint}</Text> : null}
      {Platform.OS === "ios" ? (
        <Modal visible={iosOpen} transparent animationType="slide" onRequestClose={() => setIosOpen(false)}>
          <Pressable style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" }} onPress={() => setIosOpen(false)}>
            <Pressable style={s.sheet}>
              <DateTimePicker
                value={fromInput(value)}
                mode={withTime ? "datetime" : "date"}
                display="spinner"
                themeVariant={mode}
                onChange={(_e, d) => d && emit(d)}
              />
              <Button label="Done" onPress={() => setIosOpen(false)} />
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}
    </View>
  );
}

/** A list of things to tick (several can be chosen). */
export function MultiPick({ label, options, value, onChange, empty }: {
  label: string; options: { id: number; label: string }[]; value: number[]; onChange: (v: number[]) => void; empty?: string;
}) {
  const { colors } = useTheme();
  if (options.length === 0) return empty ? <Muted style={{ marginBottom: 14 }}>{empty}</Muted> : null;
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={{ color: colors.textMuted, fontSize: 13, marginBottom: 6, fontWeight: "600" }}>{label}</Text>
      {options.map((o) => {
        const on = value.includes(o.id);
        return (
          <TouchableOpacity
            key={o.id}
            onPress={() => onChange(on ? value.filter((x) => x !== o.id) : [...value, o.id])}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: on }}
            style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44 }}
          >
            <Ionicons name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.accent : colors.textMuted} />
            <Text style={{ flex: 1 }}>{o.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

/** A bottom sheet for add/edit forms. */
export function FormSheet({ visible, title, onClose, children }: { visible: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  const s = useStyles((c) => ({
    shade: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
    sheet: { backgroundColor: c.background, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 16, maxHeight: "92%" },
  })) as unknown as Record<string, never>;
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={s.shade}>
        <View style={s.sheet}>
          <Row style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <Text style={{ fontSize: 18, fontWeight: "700", flex: 1 }}>{title}</Text>
            <TouchableOpacity onPress={onClose} accessibilityRole="button" accessibilityLabel="Close" hitSlop={10} style={{ minHeight: 44, justifyContent: "center" }}>
              <Text style={{ fontWeight: "600" }}>Close</Text>
            </TouchableOpacity>
          </Row>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: 30 }}>
            {children}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

export type Suggestion = { jobId: number; status: SuggestStatus };

/** "Move this job to Interview?" after saving. One tap does it; nothing is ever moved without that tap. */
export function SuggestMove({ suggestion, onDone }: { suggestion: Suggestion; onDone: () => void }) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const move = async () => {
    setBusy(true);
    setError("");
    try {
      await pipelineApi.setStatus(suggestion.jobId, suggestion.status.id);
      notify(`Moved to ${suggestion.status.label}.`);
      onDone();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Move this job to {suggestion.status.label}?</Text>
      <Muted style={{ marginTop: 2, marginBottom: 10 }}>Its status still says it is earlier than that. Moving it keeps your dashboard and numbers in step.</Muted>
      <Row style={{ flexWrap: "wrap" }}>
        <Button label={`Move to ${suggestion.status.label}`} busy={busy} onPress={move} />
        <Button label="Not now" variant="ghost" disabled={busy} onPress={onDone} />
      </Row>
      {error ? <Text style={{ marginTop: 8, color: colors.danger }}>{error}</Text> : null}
    </Card>
  );
}

/** Copy some text to the clipboard (the app never sends a message: the person pastes it where they want). */
export function CopyButton({ text, label }: { text: string; label: string }) {
  return (
    <Button
      label={label}
      variant="secondary"
      icon="copy-outline"
      onPress={async () => {
        await Clipboard.setStringAsync(text);
        notify("Copied.");
      }}
    />
  );
}

export const bad = (colors: { danger: string }) => ({ color: colors.danger });
