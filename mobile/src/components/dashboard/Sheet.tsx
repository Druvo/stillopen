import React from "react";
import { Modal, Pressable, ScrollView, StyleSheet, TouchableOpacity, View } from "react-native";

import { Ionicons, Text, useStyles, useTheme } from "../../ui";
import { radius } from "../../theme";

export type SheetOption<T> = { value: T; label: string; hint?: string; color?: string; disabled?: boolean; danger?: boolean };

/** A bottom sheet with a list of choices (status picker, card actions, filter values). Tap outside to close. */
export function Sheet<T extends string | number>({
  visible,
  title,
  options,
  value,
  onPick,
  onClose,
}: {
  visible: boolean;
  title: string;
  options: SheetOption<T>[];
  value?: T | null;
  onPick: (v: T) => void;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const s = useStyles((c) => StyleSheet.create({
    shade: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
    sheet: { backgroundColor: c.surface, borderTopLeftRadius: radius.card, borderTopRightRadius: radius.card, padding: 18, maxHeight: "75%" },
    title: { fontSize: 17, fontWeight: "700", marginBottom: 6 },
    row: { flexDirection: "row", alignItems: "center", minHeight: 48, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: c.border },
    dot: { width: 10, height: 10, borderRadius: 5, marginRight: 10 },
    hint: { color: c.textMuted, fontSize: 12 },
  }));
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.shade} onPress={onClose}>
        <Pressable style={s.sheet} onPress={() => undefined}>
          <Text style={s.title}>{title}</Text>
          <ScrollView>
            {options.map((o) => {
              const on = o.value === value;
              return (
                <TouchableOpacity
                  key={String(o.value)}
                  style={[s.row, o.disabled && { opacity: 0.45 }]}
                  disabled={o.disabled}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                  onPress={() => {
                    onClose();
                    onPick(o.value);
                  }}
                >
                  {o.color ? <View style={[s.dot, { backgroundColor: o.color }]} /> : null}
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: o.danger ? colors.danger : on ? colors.accent : colors.text, fontWeight: on ? "700" : "400", fontSize: 15 }}>{o.label}</Text>
                    {o.hint ? <Text style={s.hint}>{o.hint}</Text> : null}
                  </View>
                  {on ? <Ionicons name="checkmark" size={18} color={colors.accent} /> : null}
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
