import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { cvApi } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Empty, ErrorBox, Loading, Muted, Screen, Select, Text } from "../../ui";
import { useLoad } from "../../ui/useApi";
import { diffSummary } from "./logic/logic";
import { useCvStyles } from "./parts";

export default function CvDiffScreen() {
  const params = useLocalSearchParams<{ id: string; against?: string }>();
  const id = Number(params.id);
  const router = useRouter();
  const s = useCvStyles();
  const { colors } = useTheme();
  const [against, setAgainst] = useState<number | undefined>(params.against && /^\d+$/.test(params.against) ? Number(params.against) : undefined);
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => cvApi.diff(id, against), [id, against]);

  return (
    <Screen title="Compare" onRefresh={refresh} refreshing={refreshing}>
      {loading ? <Loading /> : null}
      {error && !data ? <ErrorBox message={error} onRetry={reload} /> : null}
      {data ? (
        <>
          <Text style={{ color: colors.accent }} onPress={() => router.back()} accessibilityRole="link">
            Back to v{id}
          </Text>
          {!data.other ? (
            <Empty title="Nothing to compare yet" hint="Pick another version below, or save an edit first so there are two versions." />
          ) : (
            <Muted style={{ marginVertical: 10 }}>
              Removed lines (marked -) are in {data.other.label || "the earlier version"} (v{data.other.id}) only. Added lines (marked +) are in {data.version.label || "this version"} (v{data.version.id}) only. {diffSummary(data.rows)}
            </Muted>
          )}
          {data.choices.length > 0 ? (
            <Select label={`Compare v${id} with`} value={data.other?.id ?? null} onChange={(v) => setAgainst(v)} placeholder="Choose a version" options={data.choices.map((c) => ({ value: c.id, label: `v${c.id} - ${c.label}` }))} />
          ) : null}
          {data.rows.length > 0 ? (
            <View style={s.docBox}>
              {data.rows.map((row, i) => (
                <View key={i} style={row.tag === "add" ? s.diffAdd : row.tag === "del" ? s.diffDel : undefined}>
                  <Text style={[s.mono, row.tag === "del" && { textDecorationLine: "line-through" }, row.tag !== "same" && { fontWeight: "700" }]}>
                    {row.tag === "del" ? "- " : row.tag === "add" ? "+ " : "  "}
                    {row.text}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </>
      ) : null}
    </Screen>
  );
}
