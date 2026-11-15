import * as Linking from "expo-linking";
import React from "react";
import { View } from "react-native";

import { API_BASE } from "../../api/client";
import { googleApi } from "../../api/google";
import { Badge, Button, Card, confirm, ErrorBox, Loading, Muted, notify, Screen, Text, Toggle, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { dayText } from "./format";

export default function ConnectionsScreen() {
  const { colors } = useTheme();
  const { data: s, error, loading, refreshing, refresh, reload, setData } = useLoad(() => googleApi.status());
  const action = useAction();

  const disconnect = async () => {
    if (!(await confirm("Disconnect your Google account?", "StillOpen will lose its permission and forget it.", "Disconnect"))) return;
    const next = await action.run(() => googleApi.disconnect());
    if (next) {
      setData(next);
      notify("Disconnected.", "Google no longer lets StillOpen in, and the saved permissions are deleted.");
    }
  };
  const setSync = async (on: boolean) => {
    const next = await action.run(() => googleApi.setCalendarSync(on));
    if (next) setData(next);
  };

  return (
    <Screen title="Connections" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>Optional. Connect your own Google account so StillOpen can help with the email and calendar side of a job search.</Muted>
      {loading ? (
        <Loading />
      ) : error && !s ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : s ? (
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <Text style={{ fontSize: 17, fontWeight: "700" }}>Google</Text>
            {s.connected ? <Badge label="Connected" color={colors.good} /> : null}
          </View>
          {s.message ? <Muted style={{ marginBottom: 8 }}>{s.message}</Muted> : null}
          {!s.available ? (
            <Muted>Not set up on this site. The site&apos;s admin can switch it on in Site configuration, under Google connection.</Muted>
          ) : (
            <>
              {s.connected ? (
                <Text style={{ marginBottom: 8 }}>
                  Connected as {s.email || "your Google account"}
                  {s.connected_at ? ` since ${dayText(s.connected_at)}` : ""}.
                </Text>
              ) : null}
              {s.problem ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{s.problem}</Text> : null}

              <Text style={{ fontWeight: "700", marginTop: 4 }}>What it can do</Text>
              <Muted>• Send an application from your own Gmail, but only when you press Send on a message you have seen in full.</Muted>
              <Muted>• Show the replies in that one conversation next to the job, and help you draft an answer you edit yourself.</Muted>
              <Muted>• Look at when you are free, to suggest three interview times you can paste into a reply.</Muted>
              <Muted>• Keep your Google Calendar in step with your interviews, if you switch that on below.</Muted>
              <Text style={{ fontWeight: "700", marginTop: 10 }}>What it never does</Text>
              <Muted>• It never sends anything by itself, on a schedule, or for an AI assistant.</Muted>
              <Muted>• It never reads the rest of your mail, only the conversation of a job you applied to from here.</Muted>
              <Muted>• It never keeps whole emails: only who wrote, when, and a short snippet.</Muted>
              <Muted>• It never touches calendar events it did not create.</Muted>

              <View style={{ marginTop: 14 }}>
                {s.connected ? (
                  <>
                    <Toggle label="Keep my Google Calendar in step with my interviews" hint="Adds, moves and removes the events StillOpen made. A time you move in Google comes back here." value={s.calendar_sync} onChange={setSync} />
                    <Button variant="danger" label="Disconnect Google" busy={action.busy} onPress={disconnect} />
                  </>
                ) : (
                  <>
                    <Muted style={{ marginBottom: 8 }}>
                      Google sends you back to the website after you allow access, so connecting is done there, in your phone&apos;s browser, on this same page. Come back here afterwards and pull down to refresh.
                    </Muted>
                    <Button label="Connect on the website" icon="open-outline" onPress={() => void Linking.openURL(`${API_BASE}/app/profile/connections`)} />
                  </>
                )}
              </View>
            </>
          )}
          {action.error ? (
            <View style={{ marginTop: 10 }}>
              <ErrorBox message={action.error} />
            </View>
          ) : null}
        </Card>
      ) : null}
    </Screen>
  );
}
