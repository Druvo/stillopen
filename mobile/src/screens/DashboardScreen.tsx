import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import * as endpoints from "../api/endpoints";
import type { Dashboard, JobCard } from "../api/types";
import { colors } from "../theme";

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.statTile}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function JobRow({ job, onPress }: { job: JobCard; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.jobRow} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <Text style={styles.jobRole}>{job.role}</Text>
        <Text style={styles.jobCompany}>
          {job.company}
          {job.location ? ` · ${job.location}` : ""}
        </Text>
        {job.urgent ? <Text style={styles.urgent}>Closing soon{job.days_left != null ? ` · ${job.days_left}d left` : ""}</Text> : null}
      </View>
      {job.percent != null ? (
        <View style={[styles.percentBadge, { borderColor: job.band?.color ?? colors.accent }]}>
          <Text style={[styles.percentText, { color: job.band?.color ?? colors.accent }]}>{job.percent}%</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

export default function DashboardScreen() {
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const dashboard = await endpoints.getDashboard();
    setData(dashboard);
  }, []);

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

  return (
    <FlatList
      style={{ backgroundColor: colors.background }}
      contentContainerStyle={{ padding: 16 }}
      data={data.jobs}
      keyExtractor={(j) => String(j.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
      ListHeaderComponent={
        <View>
          <Text style={styles.greeting}>{data.greeting}</Text>
          <View style={styles.statsRow}>
            <StatTile label="Tracking" value={data.stats.total} />
            <StatTile label="Applied" value={data.stats.submitted} />
            <StatTile label="Avg fit" value={data.stats.average_match != null ? `${data.stats.average_match}%` : "—"} />
            <StatTile label="Urgent" value={data.stats.urgent} />
          </View>
          {data.next_step ? (
            <View style={styles.nextStep}>
              <Text style={styles.nextStepTitle}>{data.next_step.title}</Text>
              <Text style={styles.nextStepBody}>{data.next_step.body}</Text>
            </View>
          ) : null}
          {data.worth_a_look.length > 0 ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Worth a look next</Text>
              {data.worth_a_look.slice(0, 4).map((w, i) => (
                <View key={i} style={{ marginTop: i === 0 ? 8 : 12 }}>
                  <Text style={styles.worthTitle}>{w.title}</Text>
                  <Text style={styles.worthSubtitle}>{w.subtitle}</Text>
                </View>
              ))}
            </View>
          ) : null}
          <Text style={styles.sectionTitle}>Your jobs</Text>
        </View>
      }
      renderItem={({ item }) => <JobRow job={item} onPress={() => router.push(`/job/${item.id}`)} />}
      ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.background, alignItems: "center", justifyContent: "center" },
  greeting: { fontSize: 26, fontWeight: "700", color: colors.text, marginBottom: 16 },
  statsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 16 },
  statTile: { backgroundColor: colors.surface, borderRadius: 12, padding: 14, minWidth: "47%", flexGrow: 1 },
  statValue: { fontSize: 24, fontWeight: "700", color: colors.text },
  statLabel: { color: colors.textMuted, marginTop: 2 },
  nextStep: { backgroundColor: colors.surfaceAlt, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border },
  nextStepTitle: { color: colors.text, fontWeight: "700", fontSize: 16, marginBottom: 4 },
  nextStepBody: { color: colors.textMuted },
  card: { backgroundColor: colors.surface, borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { color: colors.text, fontWeight: "700", fontSize: 15 },
  worthTitle: { color: colors.text, fontWeight: "600" },
  worthSubtitle: { color: colors.textMuted, marginTop: 2 },
  sectionTitle: { color: colors.text, fontWeight: "700", fontSize: 18, marginBottom: 8 },
  jobRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: 12, padding: 14 },
  jobRole: { color: colors.text, fontWeight: "600", fontSize: 15 },
  jobCompany: { color: colors.textMuted, marginTop: 2 },
  urgent: { color: colors.danger, marginTop: 4, fontSize: 12, fontWeight: "600" },
  percentBadge: { borderWidth: 2, borderRadius: 24, width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  percentText: { fontWeight: "700", fontSize: 13 },
});
