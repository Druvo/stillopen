// The shared building blocks every screen uses, so the whole app looks and behaves the same. Import from "../../ui" (or "../ui").
import { Ionicons } from "@expo/vector-icons";
import { Stack } from "expo-router";
import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";

import { colors } from "../theme";

export type IconName = React.ComponentProps<typeof Ionicons>["name"];
export { Ionicons };

/** A scrolling page with a header title, pull-to-refresh and room for the keyboard. Every screen starts with this. */
export function Screen({
  title,
  children,
  onRefresh,
  refreshing = false,
  scroll = true,
  padded = true,
  headerRight,
}: {
  title?: string;
  children: React.ReactNode;
  onRefresh?: () => void | Promise<void>;
  refreshing?: boolean;
  scroll?: boolean;
  padded?: boolean;
  headerRight?: () => React.ReactNode;
}) {
  const options = title !== undefined || headerRight ? { title, headerRight } : undefined;
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.background }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      {options ? <Stack.Screen options={options} /> : null}
      {scroll ? (
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[padded && { padding: 16 }, { paddingBottom: 40 }]}
          keyboardShouldPersistTaps="handled"
          refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} /> : undefined}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={{ flex: 1 }}>{children}</View>
      )}
    </KeyboardAvoidingView>
  );
}

export function Card({ children, style, onPress }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void }) {
  const body = <View style={[s.card, style]}>{children}</View>;
  return onPress ? (
    <TouchableOpacity activeOpacity={0.7} onPress={onPress}>
      {body}
    </TouchableOpacity>
  ) : (
    body
  );
}

export function Heading({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <Text style={[s.heading, style as never]}>{children}</Text>;
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: { label: string; onPress: () => void } }) {
  return (
    <View style={s.sectionRow}>
      <Text style={s.sectionTitle}>{children}</Text>
      {action ? (
        <TouchableOpacity onPress={action.onPress} hitSlop={8}>
          <Text style={s.link}>{action.label}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export function Body({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <Text style={[s.body, style as never]}>{children}</Text>;
}

export function Muted({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <Text style={[s.muted, style as never]}>{children}</Text>;
}

export function Button({
  label,
  onPress,
  variant = "primary",
  busy = false,
  disabled = false,
  icon,
  style,
}: {
  label: string;
  onPress: () => void | Promise<void>;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
  disabled?: boolean;
  icon?: IconName;
  style?: StyleProp<ViewStyle>;
}) {
  const off = busy || disabled;
  const text = variant === "primary" ? "#0a0e07" : variant === "danger" ? colors.danger : colors.text;
  return (
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={off}
      activeOpacity={0.75}
      onPress={onPress}
      style={[s.button, s[`button_${variant}`], off && { opacity: 0.55 }, style]}
    >
      {busy ? (
        <ActivityIndicator color={text} />
      ) : (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          {icon ? <Ionicons name={icon} size={18} color={text} /> : null}
          <Text style={[s.buttonText, { color: text }]}>{label}</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

export function Field({
  label,
  value,
  onChangeText,
  hint,
  error,
  multiline,
  ...rest
}: { label: string; value: string; onChangeText: (v: string) => void; hint?: string; error?: string } & Omit<TextInputProps, "value" | "onChangeText">) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        multiline={multiline}
        placeholderTextColor={colors.textMuted}
        accessibilityLabel={label}
        style={[s.input, multiline && { minHeight: 96, textAlignVertical: "top" }, error ? { borderColor: colors.danger } : null]}
        {...rest}
      />
      {error ? <Text style={s.error}>{error}</Text> : hint ? <Text style={s.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Toggle({ label, value, onChange, hint }: { label: string; value: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <View style={[s.toggleRow, { marginBottom: 14 }]}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <Text style={s.toggleLabel}>{label}</Text>
        {hint ? <Text style={s.hint}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.accent, false: colors.border }} thumbColor="#fff" accessibilityLabel={label} />
    </View>
  );
}

export function Chip({ label, selected, onPress, color }: { label: string; selected?: boolean; onPress?: () => void; color?: string }) {
  const tint = color ?? colors.accent;
  const body = (
    <View style={[s.chip, selected && { backgroundColor: tint, borderColor: tint }]}>
      <Text style={[s.chipText, selected && { color: "#0a0e07", fontWeight: "700" }]}>{label}</Text>
    </View>
  );
  return onPress ? (
    <TouchableOpacity onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!selected }}>
      {body}
    </TouchableOpacity>
  ) : (
    body
  );
}

export function Badge({ label, color = colors.accent }: { label: string; color?: string }) {
  return (
    <View style={[s.badge, { borderColor: color }]}>
      <Text style={[s.badgeText, { color }]}>{label}</Text>
    </View>
  );
}

/** A row of chips to pick one option (or none when `allowNone`). */
export function Choice<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Text style={s.label}>{label}</Text> : null}
      <View style={s.chipWrap}>
        {options.map((o) => (
          <Chip key={String(o.value)} label={o.label} selected={o.value === value} onPress={() => onChange(o.value)} />
        ))}
      </View>
    </View>
  );
}

/** A labelled field that opens a list to pick from (for long lists such as statuses, countries or CV versions). */
export function Select<T extends string | number>({
  label,
  options,
  value,
  onChange,
  placeholder = "Choose…",
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TouchableOpacity style={[s.input, { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }]} onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel={label}>
        <Text style={{ color: current ? colors.text : colors.textMuted }}>{current?.label ?? placeholder}</Text>
        <Ionicons name="chevron-down" size={18} color={colors.textMuted} />
      </TouchableOpacity>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={s.modalShade} onPress={() => setOpen(false)}>
          <View style={s.modalSheet}>
            <Text style={[s.sectionTitle, { marginBottom: 8 }]}>{label}</Text>
            <ScrollView>
              {options.map((o) => (
                <TouchableOpacity
                  key={String(o.value)}
                  style={s.optionRow}
                  onPress={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                >
                  <Text style={{ color: o.value === value ? colors.accent : colors.text, fontWeight: o.value === value ? "700" : "400" }}>{o.label}</Text>
                  {o.value === value ? <Ionicons name="checkmark" size={18} color={colors.accent} /> : null}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

export function Loading() {
  return (
    <View style={{ padding: 40, alignItems: "center" }}>
      <ActivityIndicator color={colors.accent} />
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card style={{ borderColor: colors.danger }}>
      <Text style={{ color: colors.danger, marginBottom: onRetry ? 10 : 0 }}>{message}</Text>
      {onRetry ? <Button label="Try again" variant="secondary" onPress={onRetry} /> : null}
    </Card>
  );
}

/** Every empty list says what to do next (a project rule), so `hint` is required. */
export function Empty({ title, hint, action }: { title: string; hint: string; action?: { label: string; onPress: () => void } }) {
  return (
    <View style={{ padding: 28, alignItems: "center" }}>
      <Text style={[s.heading, { fontSize: 17, textAlign: "center" }]}>{title}</Text>
      <Text style={[s.muted, { textAlign: "center", marginTop: 6, marginBottom: action ? 16 : 0 }]}>{hint}</Text>
      {action ? <Button label={action.label} onPress={action.onPress} /> : null}
    </View>
  );
}

export function Row({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: "row", alignItems: "center", gap: 10 }, style]}>{children}</View>;
}

export function Divider() {
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: 12 }} />;
}

/** A tappable list row with an optional right-hand value and chevron. */
export function ListItem({ title, subtitle, right, onPress, icon }: { title: string; subtitle?: string; right?: React.ReactNode; onPress?: () => void; icon?: IconName }) {
  return (
    <TouchableOpacity activeOpacity={onPress ? 0.7 : 1} onPress={onPress} style={s.listItem} disabled={!onPress}>
      {icon ? <Ionicons name={icon} size={22} color={colors.accent} style={{ marginRight: 14 }} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={s.listTitle}>{title}</Text>
        {subtitle ? <Text style={s.muted}>{subtitle}</Text> : null}
      </View>
      {right}
      {onPress ? <Ionicons name="chevron-forward" size={18} color={colors.textMuted} style={{ marginLeft: 8 }} /> : null}
    </TouchableOpacity>
  );
}

/** Ask before anything destructive. Resolves true only if the person confirms. */
export function confirm(title: string, message?: string, confirmLabel = "Delete"): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
      { text: confirmLabel, style: "destructive", onPress: () => resolve(true) },
    ]);
  });
}

export function notify(title: string, message?: string) {
  Alert.alert(title, message);
}

const s = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14, marginBottom: 12 },
  heading: { color: colors.text, fontSize: 22, fontWeight: "700", marginBottom: 6 },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8, marginBottom: 10 },
  sectionTitle: { color: colors.text, fontSize: 17, fontWeight: "700" },
  link: { color: colors.accent, fontWeight: "600" },
  body: { color: colors.text, fontSize: 15, lineHeight: 21 },
  muted: { color: colors.textMuted, fontSize: 13, lineHeight: 18 },
  button: { borderRadius: 12, paddingVertical: 13, paddingHorizontal: 18, alignItems: "center", justifyContent: "center", minHeight: 46 },
  button_primary: { backgroundColor: colors.accent },
  button_secondary: { backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  button_danger: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.danger },
  button_ghost: { backgroundColor: "transparent" },
  buttonText: { fontWeight: "700", fontSize: 15 },
  label: { color: colors.textMuted, fontSize: 13, marginBottom: 6, fontWeight: "600" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, color: colors.text, fontSize: 15 },
  hint: { color: colors.textMuted, fontSize: 12, marginTop: 5 },
  error: { color: colors.danger, fontSize: 12, marginTop: 5 },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  toggleLabel: { color: colors.text, fontSize: 15 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.surface },
  chipText: { color: colors.text, fontSize: 13 },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3, alignSelf: "flex-start" },
  badgeText: { fontSize: 12, fontWeight: "700" },
  modalShade: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 18, maxHeight: "70%" },
  optionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  listItem: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14, marginBottom: 10 },
  listTitle: { color: colors.text, fontSize: 15, fontWeight: "600", marginBottom: 2 },
});
