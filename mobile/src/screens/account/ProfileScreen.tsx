import { useRouter, type Href } from "expo-router";
import React, { useCallback, useState } from "react";
import { View } from "react-native";

import { accountApi, type Preferences, type ProfileData, type ProfileValues, type PickedFile, type Strength } from "../../api/account";
import { useAuth } from "../../context/AuthContext";
import { Button, Card, confirm, ErrorBox, Field, ListItem, Loading, Muted, notify, Screen, SectionTitle, Text, Toggle, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { addRole, canConfirmDelete, plural, toggleValue } from "./format";
import { AreasEditor, CV_FILE_HINT, DisplayCard, GoalsCard, pickCvFile, StrengthMeter, SuggestRoles, TimeZoneCard } from "./ProfileParts";

type Bundle = { profile: ProfileData; prefs: Preferences; strength: Strength | null };

async function loadAll(): Promise<Bundle> {
  const [profile, prefs, strength] = await Promise.all([accountApi.profile(), accountApi.preferences(), accountApi.strength().catch(() => null)]);
  return { profile, prefs, strength };
}

export default function ProfileScreen() {
  const { data, error, loading, refreshing, refresh, reload } = useLoad(loadAll);
  return (
    <Screen title="Your profile" onRefresh={refresh} refreshing={refreshing}>
      {loading ? <Loading /> : error && !data ? <ErrorBox message={error} onRetry={reload} /> : data ? <ProfileBody initial={data} reloadStrength={reload} /> : null}
    </Screen>
  );
}

function ProfileBody({ initial, reloadStrength }: { initial: Bundle; reloadStrength: () => Promise<void> }) {
  const router = useRouter();
  const { me, signOut } = useAuth();
  const { colors } = useTheme();
  const [data, setData] = useState(initial.profile);
  const [prefs, setPrefs] = useState(initial.prefs);
  const [version, setVersion] = useState(0); // a new number re-seeds the form from what the server saved (for example the CV read from a file)
  const prefsAction = useAction();

  const savePrefs = useCallback(
    async (patch: Partial<Preferences>) => {
      setPrefs((p) => ({ ...p, ...patch }));
      const saved = await prefsAction.run(() => accountApi.savePreferences(patch));
      if (saved) setPrefs((p) => ({ ...p, ...saved }));
    },
    [prefsAction],
  );

  const go = (to: string) => router.push(to as Href);

  return (
    <>
      <Card>
        <Text style={{ fontSize: 17, fontWeight: "700" }}>{me?.name}</Text>
        <Muted>{data.account.email || data.account.username}</Muted>
        <Muted style={{ marginTop: 6 }}>This is what your matches are based on. Only you can see it. Changes apply to your next fit check.</Muted>
      </Card>

      <StrengthMeter strength={initial.strength} />

      <ProfileForm
        key={version}
        data={data}
        onSaved={(next) => {
          setData(next);
          setVersion((v) => v + 1);
          void reloadStrength();
        }}
      />

      <AreasEditor areas={data.areas} max={data.max_areas} periods={data.choices.salary_periods} />

      <Card>
        <Text style={{ fontWeight: "700" }}>More about you</Text>
        <Muted style={{ marginVertical: 6 }}>Projects, work history details, certificates and cover letters help the AI judge fit. You have {plural(data.account.counts.documents, "extra document")}.</Muted>
        <Button variant="secondary" label="Manage documents" onPress={() => go("/documents")} />
      </Card>

      <GoalsCard prefs={prefs} onChange={savePrefs} />
      <DisplayCard prefs={prefs} onChange={savePrefs} />
      {prefsAction.error ? <ErrorBox message={prefsAction.error} /> : null}
      <TimeZoneCard data={data} onSaved={setData} />

      <SectionTitle>Your account</SectionTitle>
      <Muted style={{ marginBottom: 8 }}>
        Signed in as {data.account.username}
        {data.account.email ? ` (${data.account.email})` : ""}
        {data.account.google ? ". Google sign-in is linked" : ""}.
      </Muted>
      <ListItem title="Emails" subtitle="Which emails you get, and the address" icon="mail-outline" onPress={() => go("/profile/emails")} />
      <ListItem title="Notifications" subtitle="What shows in your notifications, and what you mute" icon="notifications-outline" onPress={() => go("/notifications")} />
      <ListItem title="AI settings" subtitle="Your own AI key and provider" icon="sparkles-outline" onPress={() => go("/profile/ai")} />
      <ListItem title="AI usage" icon="stats-chart-outline" onPress={() => go("/profile/usage")} />
      <ListItem title="Google connection" subtitle="Optional: Gmail and Calendar" icon="logo-google" onPress={() => go("/profile/connections")} />
      {data.site.assistant_enabled ? <ListItem title="Connect an AI assistant" icon="hardware-chip-outline" onPress={() => go("/profile/assistant")} /> : null}
      <ListItem title="Your data" subtitle="Export or add an export back" icon="cloud-download-outline" onPress={() => go("/profile/data")} />
      <ListItem title="Help" icon="help-circle-outline" onPress={() => go("/help")} />
      <Muted style={{ marginVertical: 8 }}>
        Stored about you: {plural(data.account.counts.jobs, "job")}, {plural(data.account.counts.cv_versions, "CV version")}, {plural(data.account.counts.documents, "document")}, {plural(data.account.counts.search_areas, "search area")}, and this profile.
      </Muted>

      <Button
        variant="secondary"
        label="Sign out"
        icon="log-out-outline"
        onPress={async () => {
          if (await confirm("Sign out?", undefined, "Sign out")) await signOut();
        }}
        style={{ marginTop: 8 }}
      />

      <DeleteAccount data={data} onDeleted={() => signOut()} dangerColor={colors.danger} />
    </>
  );
}

function ProfileForm({ data, onSaved }: { data: ProfileData; onSaved: (next: ProfileData) => void }) {
  const [values, setValues] = useState<ProfileValues>(data.profile);
  const [file, setFile] = useState<PickedFile | null>(null);
  const [saved, setSaved] = useState(false);
  const action = useAction();
  const set = <K extends keyof ProfileValues>(key: K, value: ProfileValues[K]) => {
    setSaved(false);
    setValues((v) => ({ ...v, [key]: value }));
  };
  const text = (key: keyof ProfileValues) => ({ value: (values[key] as string) ?? "", onChangeText: (t: string) => set(key, t as never), error: action.fields?.[key] });

  const save = async () => {
    // Time zone and the email choices have their own cards, so saving this form never undoes them.
    const { timezone: _tz, email_followups: _a, email_interviews: _b, email_weekly: _c, ...rest } = values;
    void _tz; void _a; void _b; void _c;
    const next = await action.run(() => (file ? accountApi.saveProfileWithFile(rest, file) : accountApi.saveProfile(rest)));
    if (!next) return;
    setSaved(true);
    onSaved(next);
  };

  const checks = (key: "employment_types" | "seniority_levels", options: { value: string; label: string }[]) =>
    options.map((c) => <Toggle key={c.value} label={c.label} value={values[key].includes(c.value)} onChange={() => set(key, toggleValue(values[key], c.value))} />);

  return (
    <>
      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 10 }}>What you are looking for</Text>
        <Field label="The roles you want" hint="One role per line, for example Senior Backend Engineer." multiline placeholder={"Senior Backend Engineer\nSolutions Architect"} autoCapitalize="words" {...text("target_roles")} />
        <SuggestRoles cv={values.profile_cv} roles={values.target_roles} onAddRole={(role) => set("target_roles", addRole(values.target_roles, role))} />
        <Field label="The country you live in" hint="A name like Bangladesh or a code like BD. Remote jobs limited to one country only fit you if it is this one." {...text("home_country")} />
        <Text style={{ fontWeight: "600", marginBottom: 6 }}>Kinds of employment you want</Text>
        {checks("employment_types", data.choices.employment_types)}
        <Muted style={{ marginBottom: 14 }}>Leave all off for no preference.</Muted>
        <Text style={{ fontWeight: "600", marginBottom: 6 }}>Seniority you want</Text>
        {checks("seniority_levels", data.choices.seniority_levels)}
        <Muted style={{ marginBottom: 14 }}>Leave all off for no preference.</Muted>
        <Field label="Industries you want" hint="One per line, or leave blank for any." multiline placeholder={"Fintech\nE-commerce"} {...text("industries")} />
        <Field label="Languages you can work in" hint="One per line." multiline placeholder={"English\nBangla"} {...text("languages")} />
        <Field label="Notice period" hint="For example 30 days, or available now." {...text("notice_period")} />
        <Field label="Your minimum pay" hint="With currency and period, for example 100,000 BDT/month." {...text("salary_floor")} />
        <Field label="Things you will not accept" hint="One per line." multiline {...text("deal_breakers")} />
        <Field label="Anything else the AI should know" multiline {...text("about")} />
      </Card>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 10 }}>Job alerts</Text>
        <Toggle
          label="Search for new jobs for me and email me what is found"
          hint={`Runs your saved search on a schedule and emails one short list of new matches. Off until you turn it on.${data.site.scan_emails_enabled ? "" : " The site owner has not switched scheduled emails on yet, so nothing is sent for now."}`}
          value={values.scan_digest_enabled}
          onChange={(v) => set("scan_digest_enabled", v)}
        />
        <Toggle
          label="Also prepare tailored CV drafts for my best new matches"
          hint={`After a scheduled search, writes a draft CV for your top new matches with your own AI settings (you need an AI set up and a CV). Drafts wait for you to check; nothing is approved, downloaded or sent for you.${data.site.draft_ahead_site_enabled ? "" : " The site owner has not switched this on yet, so no drafts are made for now."}`}
          value={values.draft_ahead_enabled}
          onChange={(v) => set("draft_ahead_enabled", v)}
        />
        <Toggle
          label="Email me a weekly summary of how my search is going"
          hint={`Applications sent, interviews, offers and follow-ups from the last 7 days. Off until you turn it on.${data.site.weekly_digest_site_enabled ? "" : " The site owner has not switched the weekly digest on yet, so nothing is sent for now."}`}
          value={values.weekly_digest_enabled}
          onChange={(v) => set("weekly_digest_enabled", v)}
        />
      </Card>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 10 }}>Your CV</Text>
        <Muted style={{ marginBottom: 8 }}>No CV yet? Build one step by step under CVs.</Muted>
        <Button
          variant="secondary"
          label={file ? `Chosen: ${file.name}` : "Upload your CV"}
          icon="document-attach-outline"
          onPress={async () => {
            const picked = await pickCvFile();
            if (picked) {
              setFile(picked);
              setSaved(false);
            }
          }}
        />
        <Muted style={{ marginTop: 6, marginBottom: 12 }}>{CV_FILE_HINT}</Muted>
        {action.fields?.cv_file ? <Muted>{action.fields.cv_file}</Muted> : null}
        <Field label="Your CV (text)" multiline style={{ minHeight: 220 }} {...text("profile_cv")} />
      </Card>

      {action.error ? <ErrorBox message={action.error} /> : null}
      {saved && !action.error ? <Muted style={{ marginBottom: 10 }}>Saved. Your next matches will use this.</Muted> : null}
      <Button label="Save profile" busy={action.busy} onPress={save} />
    </>
  );
}

function DeleteAccount({ data, onDeleted, dangerColor }: { data: ProfileData; onDeleted: () => void; dangerColor: string }) {
  const [typed, setTyped] = useState("");
  const action = useAction();
  const { account } = data;
  if (!account.can_delete) return <Muted style={{ marginTop: 16 }}>Site admin accounts cannot be deleted here. Ask another admin.</Muted>;
  return (
    <Card style={{ marginTop: 20, borderColor: dangerColor }}>
      <Text style={{ fontWeight: "700", marginBottom: 6 }}>Delete my account</Text>
      <Muted style={{ marginBottom: 10 }}>This removes your jobs, CVs, documents and settings for good. You can export your data first under Your data.</Muted>
      <Field label={`Type your username (${account.username}) to confirm`} value={typed} onChangeText={setTyped} autoCapitalize="none" autoCorrect={false} error={action.fields?.confirm} />
      {action.error ? <ErrorBox message={action.error} /> : null}
      <Button
        variant="danger"
        label="Delete account and data"
        busy={action.busy}
        disabled={!canConfirmDelete(typed, account.username)}
        onPress={async () => {
          if (!(await confirm("Delete your account and all of your data?", "This cannot be undone.", "Delete everything"))) return;
          const ok = await action.run(() => accountApi.deleteAccount(typed.trim()));
          if (ok) {
            notify("Your account was deleted.");
            onDeleted();
          }
        }}
      />
    </Card>
  );
}
