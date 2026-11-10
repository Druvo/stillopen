// Pieces shared by the CV, cover letter and documents screens: safe Markdown display, the fact-check card, the writing check,
// the "Ask for changes" chat, the ATS check and the file download/share helper.
import * as FileSystem from "expo-file-system/legacy";
import { useRouter, type Href } from "expo-router";
import * as Linking from "expo-linking";
import * as Sharing from "expo-sharing";
import React, { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, View, type TextStyle, type ViewStyle } from "react-native";

import {
  coverApi,
  cvApi,
  type AtsCheck,
  type AtsReport,
  type Coverage,
  type CoverageTerm,
  type JobChoices,
  type RefineMessage,
  type RefineState,
  type Suggestion,
  type WritingMatch,
} from "../../api/cv";
import { API_BASE, getToken } from "../../api/client";
import { useStyles, useTheme } from "../../context/ThemeContext";
import type { Palette } from "../../theme";
import { Badge, Button, Card, Divider, ErrorBox, Field, Ionicons, Loading, Muted, notify, Select, Text } from "../../ui";
import { errorText } from "../../ui/useApi";
import { findingText, parseBlocks, parseInline, type Finding } from "./logic/logic";
import { countsText, groupChecks, KIND_LABELS, lineLabel, readinessTone } from "./logic/quality";

// --- small helpers ---------------------------------------------------------------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "3 Nov, 10:00" in the device's own time zone. */
export function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "3 Nov" (or "3 Nov 2025" for another year). */
export function dayOnly(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const year = d.getFullYear() === new Date().getFullYear() ? "" : ` ${d.getFullYear()}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${year}`;
}

export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export const CV_TEMPLATES: { value: string; label: string }[] = [
  { value: "classic", label: "Classic" },
  { value: "modern", label: "Modern" },
  { value: "compact", label: "Compact" },
  { value: "serif", label: "Serif" },
  { value: "forest", label: "Forest" },
  { value: "slate", label: "Slate" },
];

function safeName(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "file";
}

async function offer(uri: string, mimeType?: string) {
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, mimeType ? { mimeType } : undefined);
  } else {
    notify("Saved", `Saved to ${uri}`);
  }
}

/** Download a file the server makes (the token goes in the Authorization header, never in the address) and hand it to the share sheet. */
export async function downloadAndShare(path: string, filename: string, mimeType?: string): Promise<void> {
  const token = await getToken();
  const dest = `${FileSystem.cacheDirectory}${safeName(filename)}`;
  const result = await FileSystem.downloadAsync(`${API_BASE}${path}`, dest, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (result.status !== 200) throw new Error(result.status === 404 ? "That file is not available yet. Review and approve any flagged items first." : `Download failed (${result.status})`);
  await offer(result.uri, mimeType);
}

/** Share text the app already holds as a file (used for the cover letter's plain text, which the server only serves to a signed-in browser). */
export async function shareTextFile(text: string, filename: string): Promise<void> {
  const dest = `${FileSystem.cacheDirectory}${safeName(filename)}`;
  await FileSystem.writeAsStringAsync(dest, text);
  await offer(dest, "text/plain");
}

/** Fetch the extra things some screens switch on. Failures just mean "off". */
export function useFlag<T>(load: () => Promise<T>, fallback: T): T {
  const [value, setValue] = useState<T>(fallback);
  useEffect(() => {
    load().then(setValue).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return value;
}

const make = (c: Palette) =>
  ({
    docBox: { backgroundColor: c.surface, borderRadius: 12, borderWidth: 1, borderColor: c.border, padding: 16, gap: 6 } as ViewStyle,
    h1: { fontSize: 20, fontWeight: "700", marginTop: 4 } as TextStyle,
    h2: { fontSize: 15, fontWeight: "700", marginTop: 10, textTransform: "uppercase", letterSpacing: 0.5, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.border, paddingBottom: 3 } as TextStyle,
    h3: { fontSize: 15, fontWeight: "600", marginTop: 6 } as TextStyle,
    p: { fontSize: 14, lineHeight: 21 } as TextStyle,
    liRow: { flexDirection: "row", gap: 8, paddingRight: 8 } as ViewStyle,
    rule: { height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginVertical: 6 } as ViewStyle,
    link: { color: c.accent, textDecorationLine: "underline" } as TextStyle,
    warnCard: { borderColor: c.warn } as ViewStyle,
    goodCard: { borderColor: c.good } as ViewStyle,
    mono: { fontSize: 13, lineHeight: 19 } as TextStyle,
    bubbleUser: { alignSelf: "flex-end", backgroundColor: c.accentSoft, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 7, maxWidth: "88%" } as ViewStyle,
    bubbleAi: { alignSelf: "flex-start", backgroundColor: c.surfaceAlt, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 7, maxWidth: "88%" } as ViewStyle,
    section: { borderWidth: 1, borderColor: c.border, borderRadius: 12, marginBottom: 12, backgroundColor: c.surface } as ViewStyle,
    sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 14, minHeight: 48 } as ViewStyle,
    termChip: { backgroundColor: c.surfaceAlt, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 } as ViewStyle,
    row: { flexDirection: "row", flexWrap: "wrap", gap: 8, alignItems: "center" } as ViewStyle,
    diffAdd: { backgroundColor: c.accentSoft } as ViewStyle,
    diffDel: { backgroundColor: c.surfaceAlt } as ViewStyle,
  }) satisfies Record<string, ViewStyle | TextStyle>;
export const useCvStyles = () => useStyles(make);

// --- markdown, shown as plain native text -----------------------------------------------------------------------------------------

/** A CV or letter as native text: headings, bullets, bold, italic and web links. It is never turned into HTML, so nothing in it can act as markup. */
export function Document({ text }: { text: string }) {
  const s = useCvStyles();
  const blocks = parseBlocks(text);
  const inline = (line: string, base?: TextStyle) =>
    parseInline(line).map((piece, i) => {
      if (piece.kind === "strong") return <Text key={i} style={[base, { fontWeight: "700" }]}>{piece.text}</Text>;
      if (piece.kind === "em") return <Text key={i} style={[base, { fontStyle: "italic" }]}>{piece.text}</Text>;
      if (piece.kind === "link") {
        return (
          <Text key={i} style={[base, s.link]} accessibilityRole="link" onPress={() => piece.href && /^https?:\/\//i.test(piece.href) && Linking.openURL(piece.href)}>
            {piece.text}
          </Text>
        );
      }
      return <React.Fragment key={i}>{piece.text}</React.Fragment>;
    });
  return (
    <View style={s.docBox}>
      {blocks.map((b, i) => {
        if (b.kind === "hr") return <View key={i} style={s.rule} />;
        if (b.kind === "li") {
          return (
            <View key={i} style={s.liRow}>
              <Text style={s.p}>{"•"}</Text>
              <Text style={[s.p, { flex: 1 }]}>{inline(b.text, s.p)}</Text>
            </View>
          );
        }
        const style = b.kind === "h1" ? s.h1 : b.kind === "h2" ? s.h2 : b.kind === "h3" ? s.h3 : s.p;
        return (
          <Text key={i} style={style}>
            {inline(b.text, style)}
          </Text>
        );
      })}
    </View>
  );
}

/** A section the person opens and closes. */
export function Collapsible({ title, children, defaultOpen = false, badge }: { title: string; children: React.ReactNode; defaultOpen?: boolean; badge?: React.ReactNode }) {
  const s = useCvStyles();
  const { colors } = useTheme();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={s.section}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={title} onPress={() => setOpen(!open)} style={s.sectionHead}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}>
          <Text style={{ fontSize: 16, fontWeight: "700" }}>{title}</Text>
          {badge}
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={colors.textMuted} />
      </Pressable>
      {open ? <View style={{ paddingHorizontal: 14, paddingBottom: 14 }}>{children}</View> : null}
    </View>
  );
}

// --- fact check ---------------------------------------------------------------------------------------------------------------------

/** The fact-check result and the approve button. The person approves; nothing here (or any AI) can do it for them. */
export function Findings({
  items, thing, approved, approvedAt, onApprove, busy,
}: { items: Finding[]; thing: "CV" | "letter"; approved: boolean; approvedAt: string | null; onApprove: () => void; busy: boolean }) {
  const s = useCvStyles();
  const { colors } = useTheme();
  if (items.length === 0) {
    return (
      <Card style={s.goodCard}>
        <Text style={{ color: colors.good }}>Fact check passed: nothing here goes beyond your own CV and documents.</Text>
      </Card>
    );
  }
  if (approved) {
    return (
      <Card style={s.goodCard}>
        <Text style={{ color: colors.good }}>
          You approved this {thing}
          {approvedAt ? ` on ${dayOnly(approvedAt)}` : ""} after reviewing {items.length} flagged item{items.length === 1 ? "" : "s"}.
        </Text>
      </Card>
    );
  }
  return (
    <Card style={s.warnCard}>
      <Text style={{ fontWeight: "700", marginBottom: 4 }}>Check these before you use this {thing}.</Text>
      <Muted style={{ marginBottom: 8 }}>They are not in your own CV or documents, so they may have been invented.</Muted>
      {items.map((f, i) => (
        <Text key={i} style={{ marginBottom: 4 }}>
          {"•"} {findingText(f)} <Text style={{ color: colors.textMuted }}>(line {f.line})</Text>
        </Text>
      ))}
      <Muted style={{ marginVertical: 8 }}>
        Edit the text to remove anything untrue{thing === "CV" ? ", which makes a new version" : ""}. If everything listed is in fact true, approve it. Downloading is locked until then.
      </Muted>
      <Button label="Everything listed is true: approve" onPress={onApprove} busy={busy} />
    </Card>
  );
}

// --- writing check ------------------------------------------------------------------------------------------------------------------

/** Grammar and clarity check (LanguageTool). Only shown when the site has one set up. */
export function WritingCheck({ run }: { run: () => Promise<{ matches: WritingMatch[] }> }) {
  const { colors } = useTheme();
  const [matches, setMatches] = useState<WritingMatch[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <View style={{ marginBottom: 12 }}>
      <Button
        label={busy ? "Checking writing..." : "Check writing"}
        variant="secondary"
        icon="checkmark-done-outline"
        busy={busy}
        onPress={async () => {
          setBusy(true);
          setError("");
          try {
            setMatches((await run()).matches);
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      />
      {error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{error}</Text> : null}
      {matches ? (
        matches.length === 0 ? (
          <Muted style={{ marginTop: 8 }}>No issues found.</Muted>
        ) : (
          <View style={{ marginTop: 8, gap: 8 }}>
            {matches.map((m, i) => (
              <Card key={i} style={{ marginBottom: 0, padding: 12 }}>
                <Text>{m.message}</Text>
                {m.context ? <Muted style={{ marginTop: 4 }}>"{m.context}"</Muted> : null}
                {m.suggestions.length > 0 ? <Text style={{ marginTop: 4, fontSize: 13 }}>Try: {m.suggestions.join(", ")}</Text> : null}
              </Card>
            ))}
          </View>
        )
      ) : null}
    </View>
  );
}

// --- "Ask for changes" --------------------------------------------------------------------------------------------------------------

const IDEAS = ["Make it shorter", "Less formal", "Lead with my strongest work", "Use plainer words"];

/**
 * Type what you want different; the person's own AI sends back a revised copy, which is fact-checked like a tailored one. On a CV it becomes a
 * new version (this screen then opens it, and Undo opens the parent: nothing is rewritten); on a cover letter the text changes in place and Undo
 * restores it. `flagged` are the lines the fact check could not find in the person's own material, shown before they approve.
 */
export function RefinePanel({ kind, id, flagged, onLetter }: { kind: "cv" | "cover"; id: number; flagged: Finding[]; onLetter?: () => void }) {
  const router = useRouter();
  const { colors } = useTheme();
  const s = useCvStyles();
  const [state, setState] = useState<RefineState | null>(null);
  const [loadError, setLoadError] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const log = useRef<import("react-native").ScrollView>(null);

  useEffect(() => {
    let live = true;
    (kind === "cv" ? cvApi.refineState(id) : coverApi.refineState(id))
      .then((r) => live && setState(r))
      .catch((e) => live && setLoadError(errorText(e)));
    return () => {
      live = false;
    };
  }, [kind, id]);

  if (loadError) return <Text style={{ color: colors.danger }}>{loadError}</Text>;
  if (!state) return <Loading />;
  if (!state.ai.available) {
    return (
      <View>
        <Muted>{state.ai.missing_message}</Muted>
        <Button label="Set up AI first" variant="secondary" style={{ marginTop: 10 }} onPress={() => router.push("/profile/ai" as Href)} />
      </View>
    );
  }
  const canUndo = kind === "cv" ? Boolean(state.undo_to) : Boolean(state.can_undo);

  const openCv = (cvId: number) => router.replace({ pathname: "/cv/[id]", params: { id: String(cvId), refine: "1" } });

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      if (kind === "cv") {
        const r = await cvApi.refine(id, message);
        notify("Changed", `${r.summary} ${r.flagged_count ? `${r.flagged_count} lines need your check before you approve.` : "Nothing to check."} Opening the new version.`);
        setText("");
        openCv(r.id);
      } else {
        const r = await coverApi.refine(id, message);
        setState({ ai: state!.ai, messages: r.messages, can_undo: r.can_undo });
        setText("");
        onLetter?.();
        notify("Changed", `${r.summary} ${r.letter.flagged_count ? `${r.letter.flagged_count} lines need your check before you approve.` : "Nothing to check."}`);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true);
    setError("");
    try {
      if (kind === "cv") {
        const r = await cvApi.refineUndo(id);
        openCv(r.id);
      } else {
        const r = await coverApi.refineUndo(id);
        setState({ ai: state!.ai, messages: r.messages, can_undo: r.can_undo });
        onLetter?.();
        notify("Undone", r.summary);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const messages: RefineMessage[] = state.messages;
  return (
    <View style={{ gap: 10 }}>
      {messages.length === 0 ? (
        <Muted>
          Tell the AI what you would like different and it sends back a new copy. It can only use what is already in your own CV and documents, and anything it adds that is not there is flagged for you to check.{" "}
          {kind === "cv" ? "Your current version is kept." : "You can undo the change."}
        </Muted>
      ) : (
        <View style={{ gap: 6, maxHeight: 280 }}>
          {messages.slice(-12).map((m) => (
            <View key={m.id} style={m.role === "user" ? s.bubbleUser : s.bubbleAi}>
              <Text style={{ fontSize: 14 }}>{m.text}</Text>
              {m.role === "assistant" && m.flagged_count > 0 ? <Muted>({m.flagged_count} to check)</Muted> : null}
              {m.role === "assistant" && m.result_id && kind === "cv" && m.result_id !== id ? (
                <Text style={s.link} onPress={() => openCv(m.result_id!)}>
                  Open that version
                </Text>
              ) : null}
            </View>
          ))}
        </View>
      )}
      {flagged.length > 0 ? (
        <Card style={[s.warnCard, { marginBottom: 0 }]}>
          <Text style={{ fontWeight: "700", marginBottom: 4 }}>Check these before you use it. They are not in your own CV or documents.</Text>
          {flagged.map((f, i) => (
            <Text key={i} style={{ fontSize: 13 }}>
              {"•"} {findingText(f)} (line {f.line})
            </Text>
          ))}
        </Card>
      ) : null}
      {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      <Field label="What would you like changed?" value={text} onChangeText={setText} multiline maxLength={600} placeholder="For example: make it shorter" hint="Up to 600 characters." />
      <View style={s.row}>
        <Button label="Send" onPress={() => send(text)} busy={busy} disabled={!text.trim()} icon="send" />
        {canUndo ? <Button label="Undo the last change" variant="secondary" disabled={busy} onPress={undo} /> : null}
      </View>
      <View style={s.row}>
        {IDEAS.map((idea) => (
          <Pressable key={idea} disabled={busy} onPress={() => send(idea)} accessibilityRole="button" accessibilityLabel={idea} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, opacity: busy ? 0.5 : 1 }}>
            <Text style={{ fontSize: 13 }}>{idea}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

// --- ATS check ----------------------------------------------------------------------------------------------------------------------

const STATUS_WORDS = { fail: "Needs fixing", warn: "Worth a look", pass: "Looks good" } as const;

function toneColor(c: Palette, tone: "good" | "warn" | "bad" | "fail" | "pass"): string {
  return tone === "good" || tone === "pass" ? c.good : tone === "warn" ? c.warn : c.danger;
}

function CheckRow({ check }: { check: AtsCheck }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const where = lineLabel(check.lines);
  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10 }}>
      <Pressable onPress={() => setOpen(!open)} accessibilityRole="button" accessibilityLabel={`${STATUS_WORDS[check.status]}: ${check.title}`} style={{ flexDirection: "row", alignItems: "center", gap: 8, minHeight: 28 }}>
        <Badge label={STATUS_WORDS[check.status]} color={toneColor(colors, check.status)} />
        <Text style={{ flex: 1, fontWeight: "600", fontSize: 14 }}>{check.title}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.textMuted} />
      </Pressable>
      {open ? (
        <View style={{ marginTop: 8, gap: 4 }}>
          <Text style={{ fontSize: 14 }}>
            <Text style={{ fontWeight: "700" }}>Why it matters: </Text>
            {check.why}
          </Text>
          {check.fix ? (
            <Text style={{ fontSize: 14 }}>
              <Text style={{ fontWeight: "700" }}>How to fix it: </Text>
              {check.fix}
            </Text>
          ) : null}
          {where ? <Muted>Found at {where} of the text.</Muted> : null}
        </View>
      ) : null}
    </View>
  );
}

function Terms({ items, empty }: { items: CoverageTerm[]; empty: string }) {
  const s = useCvStyles();
  if (items.length === 0) return <Muted>{empty}</Muted>;
  return (
    <View style={s.row}>
      {items.map((t) => (
        <View key={t.term} style={s.termChip}>
          <Text style={{ fontSize: 13 }}>
            {t.term}
            {t.required ? " (asked for)" : ""}
          </Text>
        </View>
      ))}
    </View>
  );
}

function CoverageBox({ coverage, jobLabel }: { coverage: Coverage; jobLabel: string }) {
  return (
    <View style={{ marginTop: 14, gap: 6 }}>
      <Text style={{ fontWeight: "700", fontSize: 15 }}>Words from {jobLabel}</Text>
      <Text style={{ fontSize: 14 }}>
        This CV has {coverage.found.length} of the {coverage.wanted} words the posting uses most ({coverage.percent}%). It is a rough guide, not a verdict.
      </Text>
      <Text style={{ fontWeight: "600", marginTop: 4 }}>Already in this CV</Text>
      <Terms items={coverage.found} empty="None of the main words yet." />
      <Text style={{ fontWeight: "600", marginTop: 4 }}>Your own material has these, but this CV leaves them out</Text>
      <Terms items={coverage.in_material} empty="Nothing here: every word your material could back is already in this CV." />
      <Text style={{ fontWeight: "600", marginTop: 4 }}>Not in your material at all: do not add these unless they are true</Text>
      <Terms items={coverage.not_in_material} empty="Nothing here." />
      <Muted style={{ marginTop: 4 }}>{coverage.note}</Muted>
    </View>
  );
}

function SuggestionCard({ s: sg, applied, onApply, onDismiss }: { s: Suggestion; applied: boolean; onApply: () => void; onDismiss: () => void }) {
  const { colors } = useTheme();
  return (
    <Card style={{ marginBottom: 0, padding: 12 }}>
      <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <Badge label={KIND_LABELS[sg.kind] ?? sg.kind} />
        <Muted style={{ flex: 1 }}>{sg.reason}</Muted>
      </View>
      {sg.original.trim() ? (
        <Text style={{ marginBottom: 6 }}>
          <Text style={{ fontWeight: "700" }}>Now: </Text>
          {sg.original}
        </Text>
      ) : null}
      <Text style={{ marginBottom: 8 }}>
        <Text style={{ fontWeight: "700" }}>Suggested: </Text>
        {sg.replacement}
      </Text>
      {applied ? (
        <Text style={{ color: colors.good }}>Applied in the editor below. Save a new version to keep it.</Text>
      ) : (
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label="Apply this change" onPress={onApply} style={{ flex: 1 }} />
          <Button label="Dismiss" variant="secondary" onPress={onDismiss} />
        </View>
      )}
    </Card>
  );
}

/**
 * The ATS check on a CV: the readiness number, the checks in three groups, an optional comparison with one of the person's jobs and an optional
 * "Improve with AI". `onApply` puts a suggestion into the editor and says whether it fitted; nothing is saved by this card.
 */
export function AtsCard({ cvId, defaultJobId, onApply }: { cvId: number; defaultJobId: number | null; onApply: (s: Suggestion) => boolean }) {
  const router = useRouter();
  const { colors } = useTheme();
  const [jobId, setJobId] = useState<number | null>(defaultJobId);
  const [report, setReport] = useState<AtsReport | null>(null);
  const [reportError, setReportError] = useState("");
  const [choices, setChoices] = useState<JobChoices | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [aiMessage, setAiMessage] = useState("");
  const [aiFailed, setAiFailed] = useState(false);
  const [improving, setImproving] = useState(false);
  const [applied, setApplied] = useState<number[]>([]);

  useEffect(() => {
    cvApi.jobChoices().then(setChoices).catch(() => {});
  }, []);
  useEffect(() => {
    let live = true;
    setReport(null);
    setReportError("");
    cvApi
      .ats(cvId, jobId)
      .then((r) => live && setReport(r))
      .catch((e) => live && setReportError(errorText(e)));
    return () => {
      live = false;
    };
  }, [cvId, jobId]);
  useEffect(() => {
    setSuggestions(null);
    setAiMessage("");
  }, [cvId]);

  const ai = report?.ai ?? choices?.ai;
  const jobs = choices?.jobs ?? [];

  async function improve() {
    setImproving(true);
    setAiMessage("");
    setAiFailed(false);
    try {
      const r = await cvApi.improve(cvId, jobId);
      setSuggestions(r.suggestions);
      setApplied([]);
      setAiMessage(r.message);
    } catch (e) {
      setSuggestions(null);
      setAiFailed(true);
      setAiMessage(errorText(e));
    } finally {
      setImproving(false);
    }
  }

  const readinessColor = report ? toneColor(colors, readinessTone(report.readiness)) : colors.text;
  return (
    <View>
      <Muted style={{ marginBottom: 10 }}>
        Applicant tracking systems read a CV as plain text, in order. This free check shows what they commonly need. It does not use AI and nothing leaves your account.
      </Muted>
      {!report && !reportError ? <Loading /> : null}
      {reportError ? (
        <View>
          <ErrorBox message={reportError} />
          {jobId !== null ? <Button label="Check without a job" variant="secondary" onPress={() => setJobId(null)} /> : null}
        </View>
      ) : null}
      {report ? (
        <View>
          <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
            <Text style={{ fontSize: 38, fontWeight: "800", color: readinessColor }} accessibilityLabel={`ATS readiness ${report.readiness} out of 100: ${report.label}`}>
              {report.readiness}
            </Text>
            <Muted>out of 100</Muted>
            <Badge label={report.label} color={readinessColor} />
          </View>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceAlt, overflow: "hidden", marginBottom: 8 }}>
            <View style={{ width: `${Math.max(2, Math.min(100, report.readiness))}%`, height: 8, backgroundColor: readinessColor }} />
          </View>
          <Text style={{ marginBottom: 6 }}>{countsText(report.counts)}.</Text>
          <Muted style={{ marginBottom: 8 }}>{report.caveat} Each check counts for the weight shown in its details; a check that could not be judged is left out.</Muted>
          {report.notes.map((n) => (
            <Muted key={n} style={{ marginBottom: 6 }}>{n}</Muted>
          ))}
          {groupChecks(report.checks).map((g) => (
            <View key={g.status} style={{ marginBottom: 10, gap: 6 }}>
              <Text style={{ fontWeight: "700" }}>
                {g.label} ({g.items.length})
              </Text>
              {g.items.map((c) => (
                <CheckRow key={c.id} check={c} />
              ))}
            </View>
          ))}
          <Muted style={{ marginBottom: 8 }}>How the files StillOpen makes are read: {report.export.summary}</Muted>
        </View>
      ) : null}

      <Select
        label="Check against a job"
        value={jobId}
        onChange={(v) => setJobId(v === 0 ? null : (v as number))}
        placeholder="No job: check the CV on its own"
        options={[{ value: 0, label: "No job: check the CV on its own" }, ...jobs.map((j) => ({ value: j.id, label: `${j.company} - ${j.role}${j.has_description ? "" : " (no description yet)"}` }))]}
      />
      <Muted style={{ marginTop: -8, marginBottom: 8 }}>Adds the words that job's posting uses, and which of them this CV has.</Muted>
      {report?.coverage && report.job ? <CoverageBox coverage={report.coverage} jobLabel={`${report.job.company} - ${report.job.role}`} /> : null}

      <Divider />
      <Text style={{ fontWeight: "700", fontSize: 15, marginBottom: 6 }}>Improve with AI</Text>
      {ai && !ai.available ? (
        <View>
          <Muted>{ai.missing_message} The check above works without it.</Muted>
          <Button label="Open AI settings" variant="secondary" style={{ marginTop: 8 }} onPress={() => router.push("/profile/ai" as Href)} />
        </View>
      ) : (
        <View>
          <Muted style={{ marginBottom: 8 }}>
            Your own AI suggests up to six small changes. It only rewords what your CV already says and only uses skills your own material shows. Nothing changes until you apply it and save.
          </Muted>
          <Button label={improving ? "Asking your AI..." : "Improve with AI"} icon="sparkles-outline" onPress={improve} busy={improving} disabled={!ai} />
        </View>
      )}
      {aiMessage ? <Text style={{ marginTop: 8, color: aiFailed ? colors.danger : colors.text }}>{aiMessage}</Text> : null}
      {suggestions && suggestions.length > 0 ? (
        <View style={{ marginTop: 10, gap: 8 }}>
          {suggestions.map((sg) => (
            <SuggestionCard
              key={sg.id}
              s={sg}
              applied={applied.includes(sg.id)}
              onApply={() => {
                if (onApply(sg)) {
                  setApplied((a) => [...a, sg.id]);
                  notify("Change applied", "It is in the editor below. Save as a new version to keep it.");
                } else {
                  notify("Nothing changed", "That line is no longer in the editor.");
                }
              }}
              onDismiss={() => setSuggestions((list) => (list ?? []).filter((x) => x.id !== sg.id))}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

