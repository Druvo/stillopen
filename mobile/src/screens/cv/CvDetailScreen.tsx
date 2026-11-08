import { useLocalSearchParams, useNavigation } from "expo-router";
// SDK 58 moved to a class-based File/Directory API; `expo-file-system/legacy` keeps the familiar
// downloadAsync/cacheDirectory functions this screen uses (see https://docs.expo.dev/versions/v58.0.0/sdk/filesystem/).
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { API_BASE, getToken } from "../../api/client";
import * as endpoints from "../../api/endpoints";
import type { CvDetail } from "../../api/types";
import { colors } from "../../theme";

export default function CvDetailScreen() {
  const { id, label } = useLocalSearchParams<{ id: string; label?: string }>();
  const cvId = Number(id);
  const navigation = useNavigation();
  const [data, setData] = useState<CvDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);

  const load = useCallback(async () => setData(await endpoints.getCvVersion(cvId)), [cvId]);

  useEffect(() => {
    navigation.setOptions({ title: label ?? "CV" });
    load().finally(() => setLoading(false));
  }, [load, navigation, label]);

  const approve = async () => {
    setApproving(true);
    try {
      await endpoints.approveCvVersion(cvId);
      await load();
    } finally {
      setApproving(false);
    }
  };

  const [downloading, setDownloading] = useState<string | null>(null);

  const downloadAndShare = async (path: string, filename: string) => {
    setDownloading(path);
    try {
      const token = await getToken();
      const dest = FileSystem.cacheDirectory + filename;
      const result = await FileSystem.downloadAsync(`${API_BASE}${path}`, dest, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (result.status !== 200) throw new Error(`Download failed (${result.status})`);
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(result.uri);
      } else {
        Alert.alert("Downloaded", `Saved to ${result.uri}`);
      }
    } catch (err: any) {
      Alert.alert("Could not download", err?.message ?? "Try again.");
    } finally {
      setDownloading(null);
    }
  };

  if (loading || !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  const locked = data.flagged && !data.approved;

  return (
    <ScrollView style={{ backgroundColor: colors.background }} contentContainerStyle={{ padding: 16 }}>
      {locked ? (
        <View style={styles.warnBox}>
          <Text style={styles.warnTitle}>Check these before you use this CV</Text>
          <Text style={styles.warnBody}>They are not in your own CV or documents, so they may have been invented.</Text>
          {data.check_report.map((f, i) => (
            <Text key={i} style={styles.flagItem}>
              • {f.text} (line {f.line})
            </Text>
          ))}
          <TouchableOpacity style={styles.approveButton} onPress={approve} disabled={approving}>
            <Text style={styles.approveButtonText}>{approving ? "Approving…" : "Everything listed is true: approve"}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {data.downloads ? (
        <View style={styles.downloadRow}>
          <TouchableOpacity style={styles.downloadButton} onPress={() => downloadAndShare(data.downloads!.docx, `${label ?? "cv"}.docx`)} disabled={!!downloading}>
            <Text style={styles.downloadButtonText}>{downloading === data.downloads.docx ? "Downloading…" : "Download DOCX"}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.downloadButtonAlt} onPress={() => downloadAndShare(data.downloads!.md, `${label ?? "cv"}.md`)} disabled={!!downloading}>
            <Text style={styles.downloadButtonAltText}>{downloading === data.downloads.md ? "Downloading…" : "Markdown"}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <Text style={styles.lockedNote}>Downloads unlock after you review the flagged items.</Text>
      )}

      <View style={styles.contentBox}>
        <Text style={styles.contentText}>{data.content}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.background, alignItems: "center", justifyContent: "center" },
  warnBox: { backgroundColor: "#241f0c", borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: "#4a3f14" },
  warnTitle: { color: colors.text, fontWeight: "700", marginBottom: 6 },
  warnBody: { color: colors.textMuted, marginBottom: 10 },
  flagItem: { color: "#f0b94d", marginBottom: 4 },
  approveButton: { backgroundColor: colors.accent, borderRadius: 10, padding: 12, alignItems: "center", marginTop: 10 },
  approveButtonText: { color: "#0a0e07", fontWeight: "700" },
  downloadRow: { flexDirection: "row", gap: 10, marginBottom: 16 },
  downloadButton: { backgroundColor: colors.accent, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16 },
  downloadButtonText: { color: "#0a0e07", fontWeight: "700" },
  downloadButtonAlt: { backgroundColor: colors.surface, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16 },
  downloadButtonAltText: { color: colors.text, fontWeight: "700" },
  lockedNote: { color: colors.textMuted, marginBottom: 16, fontStyle: "italic" },
  contentBox: { backgroundColor: colors.surface, borderRadius: 12, padding: 16 },
  contentText: { color: colors.text, fontFamily: "monospace", lineHeight: 20 },
});
