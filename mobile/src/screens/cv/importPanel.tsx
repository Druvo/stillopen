// "I already have a CV": read a file, show one card per section, and fill the builder from the ones the person takes. Nothing is saved.
import * as DocumentPicker from "expo-document-picker";
import React, { useState } from "react";
import { View } from "react-native";

import { cvApi, type PickedFile } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Badge, Button, Card, Muted, Text, Toggle } from "../../ui";
import { errorText } from "../../ui/useApi";
import { acceptAll, applyCards, canFill, initialDecisions, startStep, summaryText, type Decision, type Imported } from "./logic/importlogic";
import type { BuilderAnswers } from "./logic/quality";

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
  "text/x-markdown",
];

export function ImportPanel({ aiAvailable, current, onFill }: { aiAvailable: boolean; current: BuilderAnswers; onFill: (answers: BuilderAnswers, step: number) => void }) {
  const { colors } = useTheme();
  const [file, setFile] = useState<PickedFile | null>(null);
  const [useAi, setUseAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Imported | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  async function pick() {
    setError("");
    try {
      const r = await DocumentPicker.getDocumentAsync({ type: TYPES, copyToCacheDirectory: true, multiple: false });
      if (r.canceled || !r.assets?.[0]) return;
      const asset = r.assets[0];
      if (asset.size && asset.size > MAX_BYTES) {
        setError("That file is larger than 5 MB. A CV is usually well under 1 MB: try a smaller copy.");
        return;
      }
      setFile({ uri: asset.uri, name: asset.name, mimeType: asset.mimeType });
      setResult(null);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function read() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const out = await cvApi.importFile(file, useAi);
      setResult(out);
      setDecisions(initialDecisions(out.cards));
    } catch (e) {
      setResult(null);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const decide = (key: string, d: Decision) => setDecisions((prev) => ({ ...prev, [key]: d }));
  const label = (d: Decision) => (d === "pending" ? "To decide" : d === "accept" ? "Taken" : d === "edit" ? "Taken, to edit" : "Skipped");

  return (
    <View>
      <Muted style={{ marginBottom: 10 }}>
        Choose a PDF, a Word document (.docx), a Markdown file or a text file, up to 5 MB. We sort it into sections for you to check. Nothing is saved until you finish the questions, and the file itself is not kept.
      </Muted>
      <View style={{ gap: 8, marginBottom: 10 }}>
        <Button label={file ? "Choose another file" : "Choose your CV file"} variant="secondary" icon="attach-outline" onPress={pick} />
        {file ? <Text numberOfLines={1}>{file.name}</Text> : null}
        {aiAvailable ? <Toggle label="Let my AI sort it" value={useAi} onChange={setUseAi} hint="Your own AI sorts the text into sections. It can only use words that are in your file; anything else it suggests is thrown away." /> : null}
        <Button label="Read my CV" onPress={read} busy={busy} disabled={!file} />
      </View>
      {error ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{error}</Text> : null}
      {result ? (
        <View>
          <Text style={{ fontWeight: "600", marginBottom: 6 }}>
            {result.method === "ai" ? "Sorted by your AI." : "Sorted by plain rules, with no AI."} Check each section: accept it, edit it in the questions, or skip it.
          </Text>
          {result.notes.map((n) => (
            <Muted key={n} style={{ marginBottom: 6 }}>{n}</Muted>
          ))}
          {result.cards.map((c) => {
            const d = decisions[c.key] ?? "skip";
            return (
              <Card key={c.key} style={{ padding: 12 }}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 6, gap: 8 }}>
                  <Text style={{ fontWeight: "700", flex: 1 }}>{c.label}</Text>
                  {c.found ? <Badge label={label(d)} color={d === "pending" ? colors.warn : d === "skip" ? colors.textMuted : colors.good} /> : <Badge label="Not found" color={colors.textMuted} />}
                </View>
                {c.found ? (
                  <>
                    {c.preview.map((line, i) => (
                      <Text key={i} style={{ fontSize: 14, marginBottom: 2 }}>{"•"} {line}</Text>
                    ))}
                    {c.more > 0 ? <Muted>and {c.more} more</Muted> : null}
                    <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
                      <Button label="Accept" variant={d === "accept" ? "primary" : "secondary"} style={{ flex: 1 }} onPress={() => decide(c.key, "accept")} />
                      <Button label="Edit" variant={d === "edit" ? "primary" : "secondary"} style={{ flex: 1 }} onPress={() => decide(c.key, "edit")} />
                      <Button label="Skip" variant={d === "skip" ? "primary" : "secondary"} style={{ flex: 1 }} onPress={() => decide(c.key, "skip")} />
                    </View>
                  </>
                ) : (
                  <Muted>We did not find this in your file. You can add it in the questions.</Muted>
                )}
              </Card>
            );
          })}
          <View style={{ gap: 8, marginTop: 4 }}>
            <Button label="Accept all" variant="secondary" onPress={() => setDecisions(acceptAll(result.cards))} />
            <Button label="Fill the questions" onPress={() => onFill(applyCards(current, result.cards, decisions), startStep(result.cards, decisions))} disabled={!canFill(decisions)} />
            <Muted>{summaryText(decisions)}. Edit fills that section and opens the questions at it, so you can change it there.</Muted>
          </View>
        </View>
      ) : null}
    </View>
  );
}
