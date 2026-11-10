import React from "react";
import { View } from "react-native";

import { accountApi } from "../../api/account";
import { Badge, Card, Empty, ErrorBox, Heading, Loading, Muted, Screen, SectionTitle, Text, useTheme } from "../../ui";
import { useLoad } from "../../ui/useApi";
import { dayTimeText, money, seconds } from "./format";

const num = (value: number | null) => (value === null ? "not reported" : value.toLocaleString());

export default function AiUsageScreen() {
  const { data: u, error, loading, refreshing, refresh, reload } = useLoad(() => accountApi.usage());
  const { colors } = useTheme();
  return (
    <Screen title="AI usage" onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : error && !u ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : u ? (
        <>
          <Muted style={{ marginBottom: 12 }}>This month ({u.month}). Only numbers are kept here, never what you asked or what came back.</Muted>
          {u.calls === 0 && u.recent.length === 0 ? (
            <Empty title="No AI calls yet" hint="When you check a fit, tailor a CV or ask for changes with your own AI, each call shows here. The free keyword match never does." />
          ) : (
            <>
              <Card>
                <Heading>This month</Heading>
                <View style={{ flexDirection: "row", gap: 16, marginBottom: 8 }}>
                  <Stat value={String(u.calls)} label="calls" />
                  <Stat value={u.input_tokens.toLocaleString()} label="tokens sent" />
                  <Stat value={u.output_tokens.toLocaleString()} label="tokens received" />
                </View>
                {u.failed > 0 ? <Badge label={`${u.failed} failed`} color={colors.danger} /> : null}
                <Text style={{ marginTop: 8 }}>
                  {u.costs.length
                    ? `About ${u.costs.map((c) => money(c.amount, c.currency)).join(" and ")}${u.any_estimated ? " (an estimate: provider prices change)" : ""}.`
                    : "No cost to show: none of the models used has a known price."}
                  {u.unpriced_calls > 0 ? ` ${u.unpriced_calls} call${u.unpriced_calls === 1 ? "" : "s"} used a model with no known price, so no cost is guessed.` : ""}
                </Text>
                <Muted style={{ marginTop: 4 }}>
                  {u.latency.samples
                    ? `Time to answer: typically ${seconds(u.latency.p50_ms)}, slowest 1 in 20 about ${seconds(u.latency.p95_ms)} (${u.latency.samples} timed calls).`
                    : "Time to answer is only recorded for newer calls."}
                </Muted>
              </Card>

              <SectionTitle>Calls by what they were for</SectionTitle>
              <Card>
                {u.purposes.map((p) => {
                  const max = Math.max(1, ...u.purposes.map((x) => x.calls));
                  return (
                    <View key={p.purpose} style={{ marginBottom: 10 }} accessible accessibilityLabel={`${p.label}: ${p.calls} calls, ${p.failed} failed`}>
                      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                        <Text>{p.label}</Text>
                        <Text>{p.calls}</Text>
                      </View>
                      <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.accentSoft, marginTop: 4 }}>
                        <View style={{ height: 8, borderRadius: 4, width: `${(p.calls / max) * 100}%`, backgroundColor: colors.chart[0] }} />
                      </View>
                    </View>
                  );
                })}
              </Card>

              <SectionTitle>By model</SectionTitle>
              {u.models.map((m) => (
                <Card key={`${m.provider}/${m.model}`}>
                  <Text style={{ fontWeight: "700" }}>{m.model || m.provider}</Text>
                  <Muted>
                    {m.calls} call{m.calls === 1 ? "" : "s"} · {m.input_tokens.toLocaleString()} in / {m.output_tokens.toLocaleString()} out
                  </Muted>
                  <Muted>{m.cost === null ? "No known price" : `${money(m.cost, m.currency)}${m.estimated ? " (estimate)" : ""}`}</Muted>
                </Card>
              ))}

              <SectionTitle>{`Your last ${u.recent.length} calls`}</SectionTitle>
              {u.recent.map((r) => (
                <Card key={r.id}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Text style={{ fontWeight: "600", flex: 1 }}>{r.purpose}</Text>
                    <Badge label={r.ok ? "Worked" : "Failed"} color={r.ok ? colors.good : colors.danger} />
                  </View>
                  <Muted>
                    {dayTimeText(r.at)} · {r.model || r.provider} · took {seconds(r.duration_ms)}
                  </Muted>
                  <Muted>
                    Tokens in / out: {num(r.input_tokens)} / {num(r.output_tokens)}
                  </Muted>
                </Card>
              ))}
            </>
          )}
        </>
      ) : null}
    </Screen>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View>
      <Text style={{ fontSize: 22, fontWeight: "700" }}>{value}</Text>
      <Muted>{label}</Muted>
    </View>
  );
}
