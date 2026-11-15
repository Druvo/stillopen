// A date box the person can type (YYYY-MM-DD) or pick from the system calendar; empty means "no date".
import DateTimePicker, { DateTimePickerAndroid, type DateTimePickerEvent } from "@react-native-community/datetimepicker";
import React, { useState } from "react";
import { Modal, Platform, Pressable, View } from "react-native";

import { validIsoDate } from "../../screens/jobs/logic";
import { Button, Field, Text, useStyles } from "../../ui";

function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function DateField({ label, value, onChange, hint, error }: { label: string; value: string; onChange: (v: string) => void; hint?: string; error?: string }) {
  const [iosOpen, setIosOpen] = useState(false);
  const styles = useStyles((c) => ({
    shade: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
    sheet: { backgroundColor: c.surface, padding: 16 },
  })) as unknown as Record<string, never>;
  const current = value && validIsoDate(value) ? new Date(`${value}T12:00:00`) : new Date();
  const pick = () => {
    if (Platform.OS === "android") {
      DateTimePickerAndroid.open({ value: current, mode: "date", onChange: (_e: DateTimePickerEvent, d?: Date) => d && onChange(toIso(d)) });
    } else setIosOpen(true);
  };
  const bad = value && !validIsoDate(value) ? "Write the date as YYYY-MM-DD, for example 2026-12-31." : undefined;
  return (
    <View>
      <Field label={label} value={value} onChangeText={onChange} placeholder="YYYY-MM-DD" autoCapitalize="none" keyboardType="numbers-and-punctuation" hint={hint} error={error ?? bad} />
      <View style={{ flexDirection: "row", gap: 8, marginTop: -6, marginBottom: 14 }}>
        <Button label="Pick a date" variant="secondary" icon="calendar-outline" onPress={pick} />
        {value ? <Button label="Clear" variant="ghost" onPress={() => onChange("")} /> : null}
      </View>
      <Modal visible={iosOpen} transparent animationType="fade" onRequestClose={() => setIosOpen(false)}>
        <Pressable style={styles.shade} onPress={() => setIosOpen(false)}>
          <View style={styles.sheet}>
            <Text style={{ fontWeight: "700", marginBottom: 8 }}>{label}</Text>
            <DateTimePicker value={current} mode="date" display="inline" onChange={(_e: DateTimePickerEvent, d?: Date) => d && onChange(toIso(d))} />
            <Button label="Done" onPress={() => setIosOpen(false)} />
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}
