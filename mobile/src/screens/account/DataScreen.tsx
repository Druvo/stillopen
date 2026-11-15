import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import React, { useState } from "react";
import { View } from "react-native";

import { accountApi, type DataImportReport, type PickedFile } from "../../api/account";
import { authorizedFetch } from "../../api/endpoints";
import { Body, Button, Card, ErrorBox, Loading, Muted, notify, Screen, SectionTitle, Text } from "../../ui";
import { errorText, useLoad } from "../../ui/useApi";
import { importLines } from "./format";

const MAX_BYTES = 8 * 1024 * 1024;

export default function DataScreen() {
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => accountApi.profile());
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [file, setFile] = useState<PickedFile | null>(null);
  const [report, setReport] = useState<DataImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [importError, setImportError] = useState("");

  const exportData = async () => {
    if (!data) return;
    setExporting(true);
    setExportError("");
    try {
      const response = await authorizedFetch(data.account.classic.export);
      const body = await response.text();
      // A page that is not JSON means the server asked for a web sign-in instead of the token.
      if (!body.trim().startsWith("{")) throw new Error("The server did not give the export to the app. Use Export my data on the website for now.");
      const dest = `${FileSystem.cacheDirectory}stillopen-export.json`;
      await FileSystem.writeAsStringAsync(dest, body);
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(dest, { mimeType: "application/json", dialogTitle: "Your StillOpen data" });
      else notify("Export saved", dest);
    } catch (e) {
      setExportError(errorText(e));
    } finally {
      setExporting(false);
    }
  };

  const choose = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: ["application/json", "text/plain"], copyToCacheDirectory: true });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    setFile({ uri: asset.uri, name: asset.name, mimeType: asset.mimeType ?? "application/json", size: asset.size });
    setReport(null);
    setImportError(asset.size && asset.size > MAX_BYTES ? "That file is bigger than 8 MB, so it is not one of our exports." : "");
  };

  const clear = () => {
    setFile(null);
    setReport(null);
    setImportError("");
  };

  const run = async (preview: boolean) => {
    if (!file) return;
    setBusy(true);
    setImportError("");
    try {
      const done = await accountApi.importData(file, preview);
      if (preview) setReport(done);
      else {
        notify("Your export was added back.", "Nothing that was already here was changed.");
        clear();
      }
    } catch (e) {
      setReport(null);
      setImportError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title="Your data" onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : error && !data ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : data ? (
        <>
          <Card>
            <Text style={{ fontWeight: "700", marginBottom: 4 }}>Export my data</Text>
            <Body>Download everything stored about you as one JSON file. Secrets such as AI keys are never included.</Body>
            <Muted style={{ marginTop: 6, marginBottom: 10 }}>
              Stored about you: {data.account.counts.jobs} jobs, {data.account.counts.cv_versions} CV versions, {data.account.counts.documents} documents, {data.account.counts.search_areas} search areas, and your profile.
            </Muted>
            {exportError ? <ErrorBox message={exportError} /> : null}
            <Button label="Export my data (JSON)" icon="download-outline" busy={exporting} onPress={exportData} />
          </Card>

          <SectionTitle>Add an export back</SectionTitle>
          <Card>
            <Muted style={{ marginBottom: 10 }}>
              Choose a file you downloaded from this account with the button above. We show what would be added first. Your profile answers, CV versions, cover letters and job notes are added only where you do not already have them, and nothing you have now is
              changed.
            </Muted>
            <Button variant="secondary" label={file ? `Chosen: ${file.name}` : "Choose your export file (.json)"} icon="document-outline" onPress={choose} disabled={busy} />
            {importError ? (
              <View style={{ marginTop: 10 }}>
                <ErrorBox message={importError} />
              </View>
            ) : null}
            {file && !report ? <Button label="Check the file" busy={busy} disabled={(file.size ?? 0) > MAX_BYTES} onPress={() => run(true)} style={{ marginTop: 10 }} /> : null}
            {report ? (
              <View style={{ marginTop: 12 }}>
                {importLines(report).map((line) => (
                  <Body key={line} style={{ marginBottom: 4 }}>
                    {`• ${line}`}
                  </Body>
                ))}
                {report.nothing ? (
                  <Muted style={{ marginTop: 8 }}>There is nothing new to add from this file.</Muted>
                ) : (
                  <Button label="Add these" busy={busy} onPress={() => run(false)} style={{ marginTop: 10 }} />
                )}
                <Button variant="ghost" label="Cancel" disabled={busy} onPress={clear} />
              </View>
            ) : null}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
