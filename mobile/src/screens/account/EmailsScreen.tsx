import * as Linking from "expo-linking";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { accountApi, type ProfileData } from "../../api/account";
import { API_BASE } from "../../api/client";
import { Badge, Button, Card, ErrorBox, Loading, Muted, Screen, Text, Toggle, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";

type State = "on" | "off" | "owner_off";
type Choices = { email_followups: boolean; email_interviews: boolean; email_weekly: boolean };

const WORD: Record<State, string> = { on: "On", off: "Off", owner_off: "Not switched on by the site owner" };
const LINES: Record<State, string> = {
  on: "On. You will get this.",
  off: "Off. You will not get this.",
  owner_off: "You have this on, but the site owner has not switched it on yet, so nothing is sent for now.",
};

const choicesOf = (p: ProfileData["profile"]): Choices => ({ email_followups: p.email_followups ?? true, email_interviews: p.email_interviews ?? true, email_weekly: p.email_weekly ?? false });
const stateOf = (chosen: boolean, ownerOn: boolean): State => (!chosen ? "off" : ownerOn ? "on" : "owner_off");

function addressLine(email: string, verified: boolean | undefined): string {
  if (!email) return "You have no email address on your account yet, so nothing can be sent. Add one below.";
  if (verified) return `Emails go to ${email}.`;
  return `Your address ${email} is not confirmed yet, so nothing is sent until you confirm it. Look for our email, or add it again below.`;
}

export default function EmailsScreen() {
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => accountApi.profile());
  return (
    <Screen title="Emails" onRefresh={refresh} refreshing={refreshing}>
      {loading ? <Loading /> : error && !data ? <ErrorBox message={error} onRetry={reload} /> : data ? <EmailForm data={data} /> : null}
    </Screen>
  );
}

function EmailForm({ data }: { data: ProfileData }) {
  const { colors } = useTheme();
  const [current, setCurrent] = useState(data);
  const [draft, setDraft] = useState<Choices>(choicesOf(data.profile));
  const [saved, setSaved] = useState(false);
  const action = useAction();
  const { profile, site, account } = current;
  const changed = JSON.stringify(choicesOf(profile)) !== JSON.stringify(draft);

  useEffect(() => setDraft(choicesOf(current.profile)), [current]);

  const rows: { key: string; field: keyof Choices | null; label: string; hint: string; state: State }[] = [
    { key: "followups", field: "email_followups", label: "Follow-up reminders", hint: "One email a day at most, listing follow-ups that have just become due.", state: stateOf(draft.email_followups, !!site.followup_emails_enabled) },
    { key: "interviews", field: "email_interviews", label: "Interview reminders", hint: "A reminder the day before an interview.", state: stateOf(draft.email_interviews, !!site.followup_emails_enabled) },
    {
      key: "weekly",
      field: "email_weekly",
      label: "Your week, once a week",
      hint: "What is due, what is coming up and your best new matches. Never more than one a week, and none when there is nothing to say.",
      state: stateOf(draft.email_weekly, !!site.weekly_emails_enabled),
    },
    { key: "alerts", field: null, label: "New job alerts", hint: "Changed under Your profile, in Job alerts.", state: stateOf(!!profile.scan_digest_enabled, !!site.scan_emails_enabled) },
  ];

  const save = async () => {
    const next = await action.run(() => accountApi.saveProfile({ ...draft }));
    if (!next) return;
    setCurrent(next);
    setSaved(true);
  };

  const web = (path: string) => void Linking.openURL(`${API_BASE}${path}`);

  return (
    <>
      <Muted style={{ marginBottom: 12 }}>Choose which emails you get. StillOpen never writes to an employer for you; these only go to you.</Muted>
      <Card style={{ borderColor: account.email_verified ? colors.border : colors.warn }}>
        <Text>{addressLine(account.email, account.email_verified)}</Text>
        {account.email ? <View style={{ marginTop: 8 }}><Badge label={account.email_verified ? "Confirmed" : "Not confirmed"} color={account.email_verified ? colors.good : colors.warn} /></View> : null}
        <Muted style={{ marginTop: 10 }}>Adding an address, confirming it and choosing the main one is done on the website, where you sign in with your password.</Muted>
        <Button variant="secondary" label="Change or add email on the website" icon="open-outline" style={{ marginTop: 8 }} onPress={() => web(account.classic.email)} />
      </Card>

      <Card>
        {rows.map((row) => (
          <View key={row.key} style={{ marginBottom: 6 }}>
            {row.field ? (
              <Toggle
                label={row.label}
                hint={row.hint}
                value={draft[row.field]}
                onChange={(v) => {
                  setSaved(false);
                  setDraft((d) => ({ ...d, [row.field as keyof Choices]: v }));
                }}
              />
            ) : (
              <View style={{ marginBottom: 6 }}>
                <Text>{row.label}</Text>
                <Muted>{row.hint}</Muted>
              </View>
            )}
            <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
              <Badge label={WORD[row.state]} color={row.state === "on" ? colors.good : row.state === "owner_off" ? colors.warn : undefined} />
              <Muted style={{ flex: 1 }}>{LINES[row.state]}</Muted>
            </View>
          </View>
        ))}
        <Muted>Every email ends with a line telling you where to change these choices.</Muted>
      </Card>
      {action.error ? <ErrorBox message={action.error} /> : null}
      {saved && !action.error ? <Muted style={{ marginBottom: 10 }}>Your email choices are saved.</Muted> : null}
      <Button label="Save email choices" busy={action.busy} disabled={!changed} onPress={save} />
    </>
  );
}
