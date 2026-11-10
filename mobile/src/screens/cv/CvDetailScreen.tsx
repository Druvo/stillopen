import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { cvApi, type JobDocuments } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Badge, Button, Card, confirm, ErrorBox, Field, Loading, Muted, notify, Screen, Select, Text } from "../../ui";
import { errorText, useAction, useLoad } from "../../ui/useApi";
import { applySuggestion } from "./logic/quality";
import { AtsCard, Collapsible, CV_TEMPLATES, Document, downloadAndShare, Findings, RefinePanel, useFlag, when, WritingCheck } from "./parts";
import { settingsApi } from "../../api/cv";

export default function CvDetailScreen() {
  const { id, refine } = useLocalSearchParams<{ id: string; label?: string; refine?: string }>();
  const cvId = Number(id);
  const router = useRouter();
  const { colors } = useTheme();
  const { data: v, error, loading, refreshing, refresh, reload } = useLoad(() => cvApi.get(cvId), [cvId]);
  const writingCheck = useFlag(settingsApi.writingCheckEnabled, false);
  const act = useAction();
  const [template, setTemplate] = useState("classic");
  const [draft, setDraft] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [downloading, setDownloading] = useState("");
  const [zip, setZip] = useState<JobDocuments | null>(null);

  // The zip of a job's CV and cover letter together (only offered on a CV that belongs to a job and may be exported).
  const jobId = v?.job?.id ?? null;
  const exportable = Boolean(v?.downloads);
  useEffect(() => {
    setZip(null);
    if (exportable && jobId) cvApi.documents(jobId).then(setZip).catch(() => {});
  }, [exportable, jobId]);

  if (loading) return <Screen title="CV"><Loading /></Screen>;
  if (!v) return <Screen title="CV"><ErrorBox message={error ?? "We could not find that CV."} onRetry={reload} /></Screen>;

  const master = v.kind === "master";
  const content = draft ?? v.content;
  const changed = draft !== null && draft !== v.content;

  async function share(path: string, filename: string, mime: string) {
    setDownloading(path);
    try {
      await downloadAndShare(path, filename, mime);
    } catch (e) {
      notify("Could not download", errorText(e));
    } finally {
      setDownloading("");
    }
  }

  async function approve() {
    const done = await act.run(() => cvApi.approve(cvId));
    if (done) {
      setNote("Approved. You can now download this version.");
      await reload();
    }
  }

  async function restore() {
    if (!(await confirm("Make this your current CV?", "Your history is kept.", "Restore"))) return;
    const made = await act.run(() => cvApi.restore(cvId));
    if (made) {
      notify("Restored", "It is now your current CV. The history is kept.");
      router.replace({ pathname: "/cv/[id]", params: { id: String(made.id) } });
    }
  }

  async function remove() {
    if (!(await confirm("Delete this tailored version?", "This cannot be undone."))) return;
    const done = await act.run(() => cvApi.remove(cvId));
    if (done) router.replace("/cv" as Href);
  }

  async function save() {
    const made = await act.run(() => cvApi.edit(cvId, content, label));
    if (!made) return;
    if (made.changed) {
      notify("Saved", "Saved as a new version.");
      setDraft(null);
      setLabel("");
      router.replace({ pathname: "/cv/[id]", params: { id: String(made.id) } });
    } else {
      setNote("No changes to save.");
    }
  }

  const name = (v.label || `cv-${v.id}`).slice(0, 40);
  return (
    <Screen title={v.label || "CV"} onRefresh={refresh} refreshing={refreshing}>
      <View style={{ flexDirection: "row", gap: 8, alignItems: "center", marginBottom: 6 }}>
        <Badge label={`v${v.id}`} />
        {v.current ? <Badge label="Current" /> : null}
      </View>
      <Muted style={{ marginBottom: 10 }}>
        {v.kind_label} - {v.source_label}
        {v.provider ? ` (${v.provider})` : ""} - {when(v.created_at)}
        {v.job ? ` - for ${v.job.company}: ${v.job.role}` : ""}
      </Muted>
      {v.parent ? (
        <Text style={{ color: colors.accent, marginBottom: 10 }} onPress={() => router.push({ pathname: "/cv/[id]", params: { id: String(v.parent!.id) } })}>
          Based on v{v.parent.id}
        </Text>
      ) : null}
      {act.error ? <ErrorBox message={act.error} /> : null}
      {note ? <Text style={{ color: colors.good, marginBottom: 10 }}>{note}</Text> : null}

      {!master ? <Findings items={v.check_report} thing="CV" approved={v.approved} approvedAt={v.approved_at} busy={act.busy} onApprove={approve} /> : null}

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 8 }}>Download</Text>
        {v.downloads ? (
          <View>
            <Select label="Look (font and colour only, still one plain column)" options={CV_TEMPLATES} value={template} onChange={setTemplate} />
            <View style={{ gap: 8 }}>
              <Button label="Download DOCX" icon="document-outline" busy={downloading === `${v.downloads.docx}?template=${template}`} onPress={() => share(`${v.downloads!.docx}?template=${template}`, `${name}.docx`, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")} />
              <Button label="Markdown" variant="secondary" busy={downloading === v.downloads.md} onPress={() => share(v.downloads!.md, `${name}.md`, "text/markdown")} />
              <Button label="Print page (save as PDF from your browser)" variant="secondary" busy={downloading === `${v.downloads.print}?template=${template}`} onPress={() => share(`${v.downloads!.print}?template=${template}`, `${name}.html`, "text/html")} />
              {zip ? (
                zip.ready && zip.url ? (
                  <Button
                    label={zip.has_cv && zip.has_cover ? "CV and cover letter (zip)" : zip.has_cv ? "CV (zip)" : "Cover letter (zip)"}
                    variant="secondary"
                    busy={downloading === zip.url}
                    onPress={() => share(zip.url!, `${name}-documents.zip`, "application/zip")}
                  />
                ) : (
                  <Muted>{zip.reason}</Muted>
                )
              ) : null}
            </View>
          </View>
        ) : (
          <Muted>Downloads unlock after you review the flagged items and approve this version.</Muted>
        )}
      </Card>

      <View style={{ flexDirection: "row", gap: 10, marginBottom: 12 }}>
        <Button label="Compare" variant="secondary" icon="git-compare-outline" style={{ flex: 1 }} onPress={() => router.push({ pathname: "/cv/[id]/diff", params: { id: String(v.id) } })} />
        {master ? (
          <Button label="Restore as current" variant="secondary" busy={act.busy} onPress={restore} style={{ flex: 1 }} />
        ) : (
          <Button label="Delete" variant="danger" busy={act.busy} onPress={remove} />
        )}
      </View>

      <Collapsible title="Ask for changes" defaultOpen={refine === "1"}>
        <RefinePanel kind="cv" id={cvId} flagged={v.source === "ai" && !v.approved ? v.check_report : []} />
      </Collapsible>

      <Collapsible title="ATS check" badge={typeof v.ats_readiness === "number" ? <Badge label={`${v.ats_readiness}/100`} /> : undefined}>
        <AtsCard
          cvId={cvId}
          defaultJobId={v.job?.id ?? null}
          onApply={(s) => {
            const result = applySuggestion(content, s);
            if (!result.applied) return false;
            setDraft(result.text);
            return true;
          }}
        />
      </Collapsible>

      {writingCheck ? <WritingCheck run={() => cvApi.writingCheck(cvId)} /> : null}

      <Text style={{ fontWeight: "700", fontSize: 17, marginBottom: 8 }}>Preview</Text>
      <Document text={v.content} />

      <Text style={{ fontWeight: "700", fontSize: 17, marginTop: 18, marginBottom: 4 }}>Edit</Text>
      <Muted style={{ marginBottom: 8 }}>Saving creates a new version; this one stays as it is.{master ? " The saved text becomes your current CV." : ""}</Muted>
      <Card>
        <Field label="Name for the new version (optional)" value={label} onChangeText={setLabel} maxLength={140} error={act.fields?.label} />
        <Field label="CV (Markdown: # name, ## sections, - bullets, **bold**)" value={content} onChangeText={setDraft} multiline autoCapitalize="sentences" style={{ minHeight: 260, fontSize: 13 }} error={act.fields?.content} />
        {changed ? <Muted style={{ marginBottom: 8 }}>You have changes that are not saved yet.</Muted> : null}
        <Button label="Save as new version" onPress={save} busy={act.busy} disabled={!changed && !label} />
      </Card>

      {v.job_snapshot ? (
        <View style={{ marginTop: 12 }}>
          <Collapsible title="Job description when this was made">
            <Text style={{ fontSize: 13, lineHeight: 19 }}>{v.job_snapshot}</Text>
          </Collapsible>
        </View>
      ) : null}
    </Screen>
  );
}
