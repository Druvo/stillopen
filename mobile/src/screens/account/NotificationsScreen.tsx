import { useRouter, type Href } from "expo-router";
import React, { useMemo, useState } from "react";
import { View } from "react-native";

import { refreshUnread } from "../../components/account/useUnread";
import { noticeApi, groupByDay, timeText, unreadText, type Notice } from "../../api/notifications";
import { Button, Card, confirm, Empty, ErrorBox, Loading, Muted, Screen, SectionTitle, Text, Toggle, useTheme } from "../../ui";
import { errorText, useAction, useLoad } from "../../ui/useApi";

export default function NotificationsScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const list = useLoad(() => noticeApi.list(200));
  const kinds = useLoad(() => noticeApi.settings());
  const act = useAction();
  const [mutesError, setMutesError] = useState("");
  const items = list.data?.items ?? [];
  const unread = list.data?.unread ?? 0;
  const groups = useMemo(() => groupByDay(items), [items]);

  const refreshAll = async () => {
    await Promise.all([list.refresh(), kinds.reload()]);
  };

  const run = async (task: () => Promise<unknown>) => {
    await act.run(task);
    await list.reload();
    refreshUnread();
  };

  const open = async (n: Notice) => {
    if (!n.read) await noticeApi.read(n.id).catch(() => undefined);
    await list.reload();
    refreshUnread();
    if (n.link && n.link.startsWith("/")) router.push(n.link as Href);
  };

  const setKind = async (key: string, on: boolean) => {
    if (!kinds.data) return;
    setMutesError("");
    const muted = kinds.data.kinds.filter((k) => (k.key === key ? !on : !k.on)).map((k) => k.key);
    try {
      kinds.setData(await noticeApi.saveSettings(muted));
    } catch (e) {
      setMutesError(errorText(e));
    }
  };

  return (
    <Screen title="Notifications" onRefresh={refreshAll} refreshing={list.refreshing}>
      {list.loading ? (
        <Loading />
      ) : list.error && !list.data ? (
        <ErrorBox message={list.error} onRetry={list.reload} />
      ) : (
        <>
          <Muted style={{ marginBottom: 10 }}>{unreadText(unread)}</Muted>
          {act.error ? <ErrorBox message={act.error} /> : null}
          {items.length > 0 ? (
            <View style={{ flexDirection: "row", gap: 10, marginBottom: 12 }}>
              <Button variant="secondary" label="Mark all as read" disabled={unread === 0 || act.busy} onPress={() => run(() => noticeApi.readAll())} style={{ flex: 1 }} />
              <Button
                variant="secondary"
                label="Clear all"
                disabled={act.busy}
                onPress={async () => {
                  if (await confirm("Clear all notifications?", "They are removed from this list.", "Clear all")) await run(() => noticeApi.clearAll());
                }}
                style={{ flex: 1 }}
              />
            </View>
          ) : null}
          {items.length === 0 ? (
            <Empty title="You have no notifications" hint="When a search finds new jobs, a deadline gets close or a follow-up is due, it will show here. Start a search from your dashboard." action={{ label: "Go to your dashboard", onPress: () => router.push("/") }} />
          ) : (
            groups.map((g) => (
              <View key={g.label}>
                <SectionTitle>{g.label}</SectionTitle>
                {g.items.map((n) => (
                  <Card key={n.id} onPress={() => open(n)}>
                    <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 10 }}>
                      {!n.read ? <View accessibilityLabel="Unread" style={{ width: 10, height: 10, borderRadius: 5, marginTop: 6, backgroundColor: colors.accent }} /> : null}
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontWeight: n.read ? "400" : "700" }}>{n.title}</Text>
                        {n.text ? <Muted>{n.text}</Muted> : null}
                        <Muted>{timeText(n.created_at)}</Muted>
                      </View>
                    </View>
                    <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
                      {!n.read ? <Button variant="ghost" label="Mark read" onPress={() => run(() => noticeApi.read(n.id))} /> : null}
                      <Button variant="ghost" label="Clear" onPress={() => run(() => noticeApi.clearOne(n.id))} />
                    </View>
                  </Card>
                ))}
              </View>
            ))
          )}

          {kinds.data ? (
            <>
              <SectionTitle>Which notices do you want?</SectionTitle>
              <Card>
                <Muted style={{ marginBottom: 10 }}>Switch one off to stop getting that kind. Notices you already have stay until you clear them.</Muted>
                {kinds.data.kinds.map((k) => (
                  <Toggle key={k.key} label={k.label} value={k.on} onChange={(on) => setKind(k.key, on)} />
                ))}
                {mutesError ? <ErrorBox message={mutesError} /> : null}
              </Card>
            </>
          ) : null}
        </>
      )}
    </Screen>
  );
}
