// Every posting any search has seen: search, filter by source, sort, page, check fit, add to the tracker.
import { useRouter, type Href } from "expo-router";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View } from "react-native";

import { jobsApi, type Duplicate, type FitCheck, type PostingPage, type PostingRow } from "../../api/jobs";
import { Badge, Body, Button, Card, Empty, ErrorBox, Field, Loading, Muted, Screen, Select, Text, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";
import { POSTINGS_SORT_OPTIONS, applyHref, duplicateMessage, longDate, openLink, postingsQuery, repostHint, safeWebUrl, type PostingsSort } from "./logic";

export default function PostingsScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState("");
  const [source, setSource] = useState("");
  const [sort, setSort] = useState<PostingsSort>("newest");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PostingPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [dup, setDup] = useState<{ row: PostingRow; same: Duplicate } | null>(null);
  const [fits, setFits] = useState<Record<number, FitCheck | string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const page_ = await jobsApi.postings(postingsQuery({ q, source, page, sort }));
      if (mine === seq.current) {
        setData(page_);
        setError("");
      }
    } catch (e) {
      if (mine === seq.current) setError(errorText(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [q, source, page, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const checkFit = async (row: PostingRow) => {
    setBusyId(row.id);
    try {
      const r = await jobsApi.checkPostingFit(row.id);
      setFits((f) => ({ ...f, [row.id]: r }));
    } catch (e) {
      setFits((f) => ({ ...f, [row.id]: errorText(e) }));
    } finally {
      setBusyId(null);
    }
  };

  const add = async (row: PostingRow, allow: boolean) => {
    setBusyId(row.id);
    setMessage(null);
    try {
      const r = await jobsApi.addPosting(row.id, allow);
      if (!r.ok) {
        setDup({ row, same: r.duplicate });
        return;
      }
      setDup(null);
      setMessage({ error: false, text: r.data.created ? `Added ${r.data.company} - ${r.data.role}.` : "Already in your tracker." });
      await load();
    } catch (e) {
      setMessage({ error: true, text: errorText(e) });
    } finally {
      setBusyId(null);
    }
  };

  const filtered = Boolean(q || source);
  const sourceOptions = [{ value: "", label: "All sources" }, ...(data?.sources ?? []).map((s) => ({ value: String(s.id), label: `${s.name} (${s.connector})` }))];

  return (
    <Screen title="All postings" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>
        Every posting any search has found, whether it matched your target roles or not. Your tracker only adds the ones that fit on their own; add any other here by hand.
      </Muted>
      <Field label="Search title or company" value={draft} onChangeText={setDraft} returnKeyType="search" onSubmitEditing={() => { setQ(draft); setPage(1); }} autoCapitalize="none" />
      <View style={{ flexDirection: "row", gap: 8, marginBottom: 14 }}>
        <Button label="Search" onPress={() => { setQ(draft); setPage(1); }} />
        {filtered ? <Button label="Clear" variant="ghost" onPress={() => { setDraft(""); setQ(""); setSource(""); setPage(1); }} /> : null}
      </View>
      <Select label="Source" options={sourceOptions} value={source} onChange={(v) => { setSource(v); setPage(1); }} />
      <Select label="Sort by" options={POSTINGS_SORT_OPTIONS} value={sort} onChange={(v) => { setSort(v); setPage(1); }} />

      {loading ? <Loading /> : null}
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {data ? (
        <>
          <Text style={{ fontWeight: "700", marginBottom: 8 }}>
            {data.total} posting{data.total === 1 ? "" : "s"}
          </Text>
          {data.limit_message ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{data.limit_message}</Text> : null}
          {message ? <Text style={{ color: message.error ? colors.danger : colors.good, marginBottom: 8 }}>{message.text}</Text> : null}
          {dup ? (
            <Card style={{ borderColor: colors.warn }}>
              <Text style={{ fontWeight: "700" }}>{duplicateMessage(dup.same)}</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                <Button label="Open it" variant="secondary" onPress={() => router.push(`/job/${dup.same.id}` as Href)} />
                <Button label="Add this one anyway" variant="secondary" busy={busyId === dup.row.id} onPress={() => add(dup.row, true)} />
                <Button label="Cancel" variant="ghost" onPress={() => setDup(null)} />
              </View>
            </Card>
          ) : null}
          {data.postings.length === 0 ? (
            <Empty
              title={filtered ? "Nothing matches that" : "No postings yet"}
              hint={filtered ? "Try a shorter word, or clear the filter." : "Search for jobs on your dashboard, and what it finds will be listed here."}
              action={filtered ? undefined : { label: "Go to my dashboard", onPress: () => router.push("/" as Href) }}
            />
          ) : (
            data.postings.map((p) => {
              const fit = fits[p.id];
              const mail = applyHref(p.apply_address);
              return (
                <Card key={p.id}>
                  <Text style={{ fontWeight: "700", fontSize: 16 }}>{p.title}</Text>
                  <Muted>
                    {p.company || "Company not named"} · {p.source.name} ({p.source.connector}){p.location ? ` · ${p.location}` : ""}
                  </Muted>
                  <Muted>
                    First seen {longDate(p.first_seen)}, last seen {longDate(p.last_seen)}
                  </Muted>
                  {p.credit ? <Muted>{p.credit.label}</Muted> : null}
                  {mail ? (
                    <Text style={{ color: colors.accent, marginTop: 6 }} accessibilityRole="link" onPress={() => openLink(mail)}>
                      Apply address: {p.apply_address}
                    </Text>
                  ) : null}
                  {p.repost ? (
                    <View style={{ marginTop: 6 }}>
                      <Badge label={`Possible repost: ${p.repost.distinct_urls} postings on ${p.repost.distinct_dates} days`} color={colors.warn} />
                      <Muted style={{ marginTop: 4 }}>{repostHint(p.repost)}</Muted>
                    </View>
                  ) : null}
                  {fit !== undefined ? (
                    typeof fit === "string" ? (
                      <Text style={{ color: colors.danger, marginTop: 6 }}>{fit}</Text>
                    ) : (
                      <View style={{ marginTop: 6 }}>
                        <Badge label={`${fit.match_percent}% match`} color={fit.match_percent >= 70 ? colors.good : fit.match_percent >= 50 ? colors.textMuted : colors.warn} />
                        <Body style={{ marginTop: 4 }}>{fit.summary}</Body>
                      </View>
                    )
                  ) : null}
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10, alignItems: "center" }}>
                    {safeWebUrl(p.url) ? <Button label="Open" variant="ghost" onPress={() => openLink(p.url)} /> : null}
                    {p.tracked ? (
                      p.job_id ? <Button label="Tracked: open it" variant="secondary" onPress={() => router.push(`/job/${p.job_id}` as Href)} /> : <Badge label="Tracked" color={colors.good} />
                    ) : (
                      <>
                        <Button label="Check my fit" variant="secondary" busy={busyId === p.id} onPress={() => checkFit(p)} />
                        <Button label="Add to tracker" variant="secondary" busy={busyId === p.id} onPress={() => add(p, false)} />
                      </>
                    )}
                  </View>
                </Card>
              );
            })
          )}
          {data.pages > 1 ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <Button label="Previous" variant="secondary" disabled={data.page <= 1} onPress={() => setPage(data.page - 1)} />
              <Muted>
                Page {data.page} of {data.pages}
              </Muted>
              <Button label="Next" variant="secondary" disabled={data.page >= data.pages} onPress={() => setPage(data.page + 1)} />
            </View>
          ) : null}
        </>
      ) : null}
    </Screen>
  );
}
