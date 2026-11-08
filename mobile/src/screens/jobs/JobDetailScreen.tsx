import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import * as endpoints from "../../api/endpoints";
import type { Dashboard, JobCard } from "../../api/types";
import { colors } from "../../theme";

export default function JobDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [statuses, setStatuses] = useState<Dashboard["statuses"]>([]);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [current, setCurrent] = useState<JobCard | null>(null);

  useEffect(() => {
    // The dashboard already has every job card; there's no single-job JSON endpoint on the backend (see
    // `tracker/api/routes.py`), so re-fetching it here and picking the one we need is the simplest correct option.
    endpoints.getDashboard().then((d) => {
      setStatuses(d.statuses);
      setCurrent(d.jobs.find((j) => String(j.id) === id) ?? null);
    });
  }, [id]);

  if (!current) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  const changeStatus = async (statusId: number) => {
    setBusy(true);
    try {
      const result = await endpoints.setJobStatus(current.id, statusId);
      setCurrent({ ...current, status_id: result.status_id, bucket_key: result.bucket_key });
    } finally {
      setBusy(false);
    }
  };

  const checkFit = async () => {
    setChecking(true);
    try {
      const result = await endpoints.evaluateJob(current.id);
      setCurrent({ ...current, percent: result.match_percent });
    } finally {
      setChecking(false);
    }
  };

  return (
    <ScrollView style={{ backgroundColor: colors.background }} contentContainerStyle={{ padding: 16 }}>
      <Text style={styles.role}>{current.role}</Text>
      <Text style={styles.company}>{current.company}</Text>
      {current.location ? <Text style={styles.meta}>{current.location}</Text> : null}
      {current.arrangement ? <Text style={styles.meta}>{current.arrangement}</Text> : null}
      {current.advertised_pay ? <Text style={styles.meta}>{current.advertised_pay}</Text> : null}

      {current.percent != null ? (
        <View style={styles.fitRow}>
          <Text style={[styles.fitPercent, { color: current.band?.color ?? colors.accent }]}>{current.percent}%</Text>
          <Text style={styles.fitText}>{current.fit_text}</Text>
        </View>
      ) : (
        <TouchableOpacity style={styles.secondaryButton} onPress={checkFit} disabled={checking}>
          <Text style={styles.secondaryButtonText}>{checking ? "Checking…" : "Check my fit"}</Text>
        </TouchableOpacity>
      )}

      {current.next_action ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Next action</Text>
          <Text style={styles.cardBody}>{current.next_action}</Text>
        </View>
      ) : null}

      {current.ai_summary ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>About this job</Text>
          <Text style={styles.cardBody}>{current.ai_summary}</Text>
        </View>
      ) : null}

      {current.cv ? (
        <TouchableOpacity
          style={styles.card}
          onPress={() => router.push({ pathname: "/cv/[id]", params: { id: String(current.cv!.id), label: current.cv!.label } })}
        >
          <Text style={styles.cardTitle}>{current.cv.label}</Text>
          <Text style={styles.cardBody}>
            {current.cv.flagged && !current.cv.approved ? "Needs review before download" : current.cv.approved ? "Approved · ready to download" : "Tap to view"}
          </Text>
        </TouchableOpacity>
      ) : null}

      <Text style={styles.sectionTitle}>Move to</Text>
      <View style={styles.statusWrap}>
        {statuses.map((s) => (
          <TouchableOpacity
            key={s.id}
            style={[styles.statusChip, { borderColor: s.color }, s.id === current.status_id && { backgroundColor: s.color }]}
            onPress={() => changeStatus(s.id)}
            disabled={busy}
          >
            <Text style={[styles.statusChipText, s.id === current.status_id && { color: "#0a0e07", fontWeight: "700" }]}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {current.notes ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Notes</Text>
          <Text style={styles.cardBody}>{current.notes}</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.background, alignItems: "center", justifyContent: "center" },
  role: { fontSize: 24, fontWeight: "700", color: colors.text },
  company: { fontSize: 17, color: colors.textMuted, marginTop: 2 },
  meta: { color: colors.textMuted, marginTop: 4 },
  fitRow: { flexDirection: "row", alignItems: "center", marginTop: 16, gap: 12 },
  fitPercent: { fontSize: 28, fontWeight: "700" },
  fitText: { color: colors.textMuted, flex: 1 },
  secondaryButton: { marginTop: 16, backgroundColor: colors.surface, borderRadius: 10, padding: 14, alignItems: "center" },
  secondaryButtonText: { color: colors.accent, fontWeight: "700" },
  card: { backgroundColor: colors.surface, borderRadius: 12, padding: 16, marginTop: 16 },
  cardTitle: { color: colors.text, fontWeight: "700", marginBottom: 6 },
  cardBody: { color: colors.textMuted, lineHeight: 20 },
  sectionTitle: { color: colors.text, fontWeight: "700", fontSize: 16, marginTop: 24, marginBottom: 10 },
  statusWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  statusChip: { borderWidth: 1.5, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8 },
  statusChipText: { color: colors.text, fontSize: 13 },
});
