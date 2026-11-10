import * as DocumentPicker from "expo-document-picker";
import { useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { documentsApi, type DocumentRow, type Documents, type PickedFile } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Badge, Button, Card, confirm, Empty, ErrorBox, Field, Loading, Muted, notify, Screen, SectionTitle, Select, Text } from "../../ui";
import { errorText, useAction, useLoad } from "../../ui/useApi";
import { fileSize } from "./parts";

function AddDocument({ data, onAdded }: { data: Documents; onAdded: () => Promise<void> }) {
  const { colors } = useTheme();
  const act = useAction();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState(data.kinds.some((k) => k.value === "project") ? "project" : data.kinds[0]?.value ?? "other");
  const [text, setText] = useState("");
  const [file, setFile] = useState<PickedFile | null>(null);
  const [pickError, setPickError] = useState("");

  async function pick() {
    setPickError("");
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf", "text/plain", "text/markdown", "text/x-markdown"],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      if (asset.size && asset.size > data.limits.max_file_bytes) {
        setPickError(`That file is larger than ${fileSize(data.limits.max_file_bytes)}. Try a smaller one.`);
        return;
      }
      setFile({ uri: asset.uri, name: asset.name, mimeType: asset.mimeType });
      if (!title.trim()) setTitle(asset.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setPickError(errorText(e));
    }
  }

  async function add() {
    const made = await act.run(() => (file ? documentsApi.addFile(title, kind, text, file) : documentsApi.addText(title, kind, text)));
    if (made) {
      setTitle("");
      setText("");
      setFile(null);
      notify("Added", `Added ${made.title}.`);
      await onAdded();
    }
  }

  return (
    <Card>
      <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 10 }}>Add a document</Text>
      <Field label="Title" value={title} onChangeText={setTitle} maxLength={160} error={act.fields?.title} />
      <Select label="What it is" options={data.kinds} value={kind} onChange={setKind} />
      <Field label="Text" value={text} onChangeText={setText} multiline hint="Paste it here, or choose a file below." error={act.fields?.text} style={{ minHeight: 120 }} />
      <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: "600", marginBottom: 6 }}>Or choose a file</Text>
      <View style={{ flexDirection: "row", gap: 10, alignItems: "center", marginBottom: 6 }}>
        <Button label={file ? "Choose another file" : "Choose a file"} variant="secondary" icon="attach-outline" onPress={pick} />
        {file ? (
          <Text style={{ flex: 1 }} numberOfLines={1}>
            {file.name}
          </Text>
        ) : null}
      </View>
      <Muted style={{ marginBottom: 10 }}>A .txt, .md or .pdf file, up to {fileSize(data.limits.max_file_bytes)}. We read the text and then discard the file.</Muted>
      {pickError ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{pickError}</Text> : null}
      {act.fields?.file ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{act.fields.file}</Text> : null}
      {act.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{act.error}</Text> : null}
      <Button label="Add document" onPress={add} busy={act.busy} disabled={!title.trim() || (!text.trim() && !file)} />
    </Card>
  );
}

function DocRow({ doc, onChanged }: { doc: DocumentRow; onChanged: () => Promise<void> }) {
  const { colors } = useTheme();
  const act = useAction();
  async function toggle() {
    const r = await act.run(() => documentsApi.toggle(doc.id));
    if (r) {
      notify(r.enabled ? "In use again" : "Hidden", r.enabled ? `"${doc.title}" will be used again.` : `"${doc.title}" is hidden from the AI.`);
      await onChanged();
    }
  }
  async function remove() {
    if (!(await confirm(`Delete "${doc.title}"?`, "This cannot be undone."))) return;
    const r = await act.run(() => documentsApi.remove(doc.id));
    if (r) await onChanged();
  }
  return (
    <Card>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Text style={{ fontWeight: "700", fontSize: 16 }}>{doc.title}</Text>
        {!doc.enabled ? <Badge label="Hidden from the AI" /> : null}
      </View>
      <Muted style={{ marginTop: 2 }}>
        {doc.kind_label} - {doc.characters.toLocaleString()} characters - {doc.passages} passages
      </Muted>
      {act.error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{act.error}</Text> : null}
      <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
        <Button label={doc.enabled ? "Hide from the AI" : "Use again"} variant="secondary" busy={act.busy} onPress={toggle} style={{ flex: 1 }} />
        <Button label="Delete" variant="danger" busy={act.busy} onPress={remove} />
      </View>
    </Card>
  );
}

export default function DocumentsScreen() {
  const router = useRouter();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => documentsApi.list());
  const refetch = async () => {
    await reload();
  };
  return (
    <Screen title="Documents about you" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>
        Projects, work history details, certificates, cover letters. For each job, only the passages that matter are used. Uploaded files are read for their text and then discarded; only the text is kept.
      </Muted>
      {loading ? <Loading /> : null}
      {error && !data ? <ErrorBox message={error} onRetry={reload} /> : null}
      {data ? (
        <>
          <Card>
            {data.cv.present ? (
              <View style={{ gap: 6 }}>
                <Badge label="Your CV is included" />
                <Muted>It comes from your profile and is always used.</Muted>
              </View>
            ) : (
              <View style={{ gap: 6 }}>
                <Badge label="No CV yet" />
                <Muted>Add your CV so tailoring and fit checks have something to work from.</Muted>
                <Button label="Build or import a CV" variant="secondary" onPress={() => router.push("/cv/new" as Href)} />
              </View>
            )}
          </Card>
          {data.sources.length >= data.limits.max_documents ? (
            <Card>
              <Text>You have reached the limit of {data.limits.max_documents} documents. Delete one to add another.</Text>
            </Card>
          ) : (
            <AddDocument data={data} onAdded={refetch} />
          )}
          <SectionTitle>Your documents ({data.sources.length}/{data.limits.max_documents})</SectionTitle>
          {data.sources.length === 0 ? (
            <Empty title="Nothing added yet" hint="Add a project write-up, a certificate or anything else that shows what you can do, using the form above." />
          ) : (
            data.sources.map((doc) => <DocRow key={doc.id} doc={doc} onChanged={refetch} />)
          )}
        </>
      ) : null}
    </Screen>
  );
}
