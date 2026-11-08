import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import * as endpoints from "../../api/endpoints";
import type { CvList, CvSummary } from "../../api/types";
import { colors } from "../../theme";

function Row({ item, onPress }: { item: CvSummary; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <Text style={styles.label}>{item.label}</Text>
        <Text style={styles.meta}>
          {item.job ? `${item.job.role} · ${item.job.company}` : item.kind_label}
        </Text>
      </View>
      {item.flagged && !item.approved ? (
        <View style={styles.badgeWarn}>
          <Text style={styles.badgeWarnText}>Review</Text>
        </View>
      ) : item.exportable ? (
        <View style={styles.badgeOk}>
          <Text style={styles.badgeOkText}>Ready</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

export default function CvListScreen() {
  const router = useRouter();
  const [data, setData] = useState<CvList | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => setData(await endpoints.listCvVersions()), []);

  useFocusEffect(
    useCallback(() => {
      load().finally(() => setLoading(false));
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (loading || !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  const sections = [
    { title: "Tailored for a job", data: data.tailored },
    { title: "Master CV", data: data.masters },
  ].filter((s) => s.data.length > 0);

  return (
    <FlatList
      style={{ backgroundColor: colors.background }}
      contentContainerStyle={{ padding: 16 }}
      data={sections}
      keyExtractor={(s) => s.title}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
      renderItem={({ item: section }) => (
        <View style={{ marginBottom: 20 }}>
          <Text style={styles.sectionTitle}>{section.title}</Text>
          {section.data.map((v) => (
            <View key={v.id} style={{ marginBottom: 8 }}>
              <Row item={v} onPress={() => router.push({ pathname: "/cv/[id]", params: { id: String(v.id), label: v.label } })} />
            </View>
          ))}
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.background, alignItems: "center", justifyContent: "center" },
  sectionTitle: { color: colors.text, fontWeight: "700", fontSize: 16, marginBottom: 8 },
  row: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: 12, padding: 14 },
  label: { color: colors.text, fontWeight: "600" },
  meta: { color: colors.textMuted, marginTop: 2, fontSize: 13 },
  badgeWarn: { backgroundColor: "#3a2a12", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  badgeWarnText: { color: "#f0b94d", fontSize: 12, fontWeight: "700" },
  badgeOk: { backgroundColor: "#16321c", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  badgeOkText: { color: colors.good, fontSize: 12, fontWeight: "700" },
});
