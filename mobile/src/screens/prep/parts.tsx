// Small pieces shared by the prep and interview-assist screens.
import * as Clipboard from "expo-clipboard";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { Linking, TouchableOpacity, View } from "react-native";

import type { Source, Tally } from "../../api/prep";
import { Button, Ionicons, notify, Text, useStyles, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";

/** Opens a lesson or answer source in the phone's browser. Only http(s) links are ever opened. */
export function SourceLinks({ sources }: { sources: Source[] }) {
  const s = useStyles((c) => ({
    link: { color: c.accent, fontSize: 14, paddingVertical: 8, textDecorationLine: "underline" as const },
    note: { color: c.warn, fontSize: 12 },
  })) as unknown as Record<string, never>;
  if (!sources?.length) return <Text style={{ fontSize: 13 }}>No source given.</Text>;
  return (
    <View>
      {sources.map((src, i) =>
        /^https?:\/\//i.test(src.url) ? (
          <View key={i}>
            <TouchableOpacity accessibilityRole="link" accessibilityLabel={`Open ${src.title || src.url}`} onPress={() => void Linking.openURL(src.url)} style={{ minHeight: 36, justifyContent: "center" }}>
              <Text style={s.link}>{src.title || src.url}</Text>
            </TouchableOpacity>
            {src.checked === false ? <Text style={s.note}>We could not open this link from the server; the site may just block automatic visits.</Text> : null}
          </View>
        ) : (
          <Text key={i} style={{ fontSize: 14 }}>
            {src.title}
          </Text>
        ),
      )}
    </View>
  );
}

/** A big, clear tick row (44pt+) used for "Mark done" and "This came up". */
export function TickRow({ label, checked, onPress, disabled }: { label: string; checked: boolean; onPress: () => void; disabled?: boolean }) {
  const { colors } = useTheme();
  return (
    <TouchableOpacity
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled }}
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={{ flexDirection: "row", alignItems: "center", minHeight: 44, gap: 10, opacity: disabled ? 0.6 : 1 }}
    >
      <Ionicons name={checked ? "checkmark-circle" : "ellipse-outline"} size={26} color={checked ? colors.good : colors.textMuted} />
      <Text style={{ flex: 1, fontSize: 15 }}>{label}</Text>
    </TouchableOpacity>
  );
}

/** The "This came up" tick for one question; `setter` returns the new tally. */
export function CameUpTick({ ticked, onSet }: { ticked: boolean; onSet: (value: boolean) => Promise<Tally> | Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const { colors } = useTheme();
  return (
    <View>
      <TickRow
        label="This came up"
        checked={ticked}
        disabled={busy}
        onPress={async () => {
          setBusy(true);
          setProblem("");
          try {
            await onSet(!ticked);
          } catch (e) {
            setProblem(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      />
      {problem ? <Text style={{ color: colors.danger, fontSize: 12 }}>{problem}</Text> : null}
    </View>
  );
}

export async function copyToClipboard(text: string) {
  try {
    await Clipboard.setStringAsync(text);
    notify("Copied.");
  } catch {
    notify("We could not copy that. Select the text and copy it by hand.");
  }
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  return <Button label={label} variant="secondary" icon="copy-outline" onPress={() => copyToClipboard(text)} />;
}

/** What replaces an AI button when no AI is set up: one plain line and the way to fix it. */
export function NoKeyLine() {
  const router = useRouter();
  return (
    <View>
      <Text style={{ fontSize: 14, marginBottom: 8 }}>Add your free Google AI Studio key in AI settings to use this.</Text>
      <Button label="Open AI settings" variant="secondary" onPress={() => router.push("/profile/ai" as never)} />
    </View>
  );
}

export function AiNotice({ children }: { children?: React.ReactNode }) {
  const { colors } = useTheme();
  return <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{children ?? "Written by AI, which can be wrong. Check it and put it in your own words."}</Text>;
}

export function Problem({ message }: { message?: string | null }) {
  const { colors } = useTheme();
  return message ? <Text style={{ color: colors.danger, fontSize: 13, marginTop: 8 }}>{message}</Text> : null;
}

/** A thin progress bar. */
export function Bar({ percent }: { percent: number }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(percent) }} style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceAlt, overflow: "hidden", marginVertical: 8 }}>
      <View style={{ height: 8, width: `${Math.max(0, Math.min(100, percent))}%`, backgroundColor: colors.accent }} />
    </View>
  );
}
