import { Ionicons } from "@expo/vector-icons";
import { useRouter, type Href } from "expo-router";
import React, { useMemo, useState } from "react";
import { Pressable, View } from "react-native";

import { Button, Card, Empty, Field, Muted, Screen, Text, useTheme } from "../../ui";
import { FAQ, SECTIONS, type Faq, type HelpLink, type HelpSection } from "./helpContent";

/** True when every word typed is somewhere in the text (case does not matter). */
export function matches(query: string, text: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = text.toLowerCase();
  return words.every((w) => hay.includes(w));
}

const sectionText = (s: HelpSection) => [s.title, s.intro ?? "", ...(s.steps ?? []), ...(s.points ?? [])].join(" ");
const faqText = (f: Faq) => `${f.question} ${f.answer}`;

export default function HelpScreen() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({ [SECTIONS[0].id]: true });
  const searching = query.trim() !== "";

  const sections = useMemo(() => SECTIONS.filter((s) => !searching || matches(query, sectionText(s))), [query, searching]);
  const faqs = useMemo(() => FAQ.filter((f) => !searching || matches(query, faqText(f))), [query, searching]);
  const toggle = (id: string) => setOpen((o) => ({ ...o, [id]: !o[id] }));
  const isOpen = (id: string) => searching || !!open[id]; // a search shows the answers it found, already open

  return (
    <Screen title="Help">
      <Muted style={{ marginBottom: 10 }}>How StillOpen works, in plain words.</Muted>
      <Field label="Search help" value={query} onChangeText={setQuery} placeholder="For example: CV, email, score" autoCapitalize="none" autoCorrect={false} returnKeyType="search" />
      {!searching ? (
        <View style={{ flexDirection: "row", gap: 10, marginBottom: 12 }}>
          <Button variant="secondary" label="Open all" onPress={() => setOpen(Object.fromEntries([...SECTIONS.map((s) => [s.id, true]), ["faq", true]]))} style={{ flex: 1 }} />
          <Button variant="secondary" label="Close all" onPress={() => setOpen({})} style={{ flex: 1 }} />
        </View>
      ) : null}

      {sections.length === 0 && faqs.length === 0 ? (
        <Empty title="Nothing found" hint="Try fewer or different words, for example CV, email, score or AI." action={{ label: "Clear the search", onPress: () => setQuery("") }} />
      ) : null}

      {sections.map((s) => (
        <Disclosure key={s.id} title={s.title} open={isOpen(s.id)} onToggle={() => toggle(s.id)}>
          {s.intro ? <Text style={{ marginBottom: 8 }}>{s.intro}</Text> : null}
          {s.steps?.map((t, i) => (
            <Bullet key={t} marker={`${i + 1}.`} text={t} />
          ))}
          {s.points?.map((t) => (
            <Bullet key={t} marker="•" text={t} />
          ))}
          <Links links={s.links} />
        </Disclosure>
      ))}

      {faqs.length > 0 ? (
        <Disclosure title="Questions people ask" open={isOpen("faq")} onToggle={() => toggle("faq")}>
          {faqs.map((f, i) => (
            <Disclosure key={f.question} small title={f.question} open={isOpen(`faq-${i}`)} onToggle={() => toggle(`faq-${i}`)}>
              <Text>{f.answer}</Text>
              <Links links={f.link ? [f.link] : undefined} />
            </Disclosure>
          ))}
        </Disclosure>
      ) : null}
    </Screen>
  );
}

function Bullet({ marker, text }: { marker: string; text: string }) {
  return (
    <View style={{ flexDirection: "row", gap: 8, marginBottom: 8 }}>
      <Text style={{ width: 20 }}>{marker}</Text>
      <Text style={{ flex: 1, lineHeight: 22 }}>{text}</Text>
    </View>
  );
}

function Links({ links }: { links?: HelpLink[] }) {
  const router = useRouter();
  if (!links?.length) return null;
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
      {links.map((l) => (
        <Button key={l.to + l.label} variant="secondary" label={l.label} onPress={() => router.push(l.to as Href)} />
      ))}
    </View>
  );
}

function Disclosure({ title, open, onToggle, children, small }: { title: string; open: boolean; onToggle: () => void; children: React.ReactNode; small?: boolean }) {
  const { colors } = useTheme();
  return (
    <Card style={small ? { borderWidth: 0, borderTopWidth: 1, borderRadius: 0, paddingHorizontal: 0, marginBottom: 0 } : undefined}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={title} onPress={onToggle} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 44, gap: 10 }}>
        <Text style={{ flex: 1, fontWeight: "700", fontSize: small ? 15 : 17 }}>{title}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={colors.textMuted} />
      </Pressable>
      {open ? <View style={{ paddingTop: 8 }}>{children}</View> : null}
    </Card>
  );
}
