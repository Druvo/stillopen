import * as Clipboard from "expo-clipboard";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { accountApi, type NewToken } from "../../api/account";
import { Badge, Body, Button, Card, confirm, Empty, ErrorBox, Field, Heading, Loading, Muted, notify, Screen, SectionTitle, Select, Text } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { dayText, lastUsed } from "./format";

/** The one line to paste in a terminal to connect Claude Code. Built here from the token shown once; nothing is stored. */
const claudeCommand = (endpoint: string, token: string) => `claude mcp add --transport http stillopen ${endpoint} --header "Authorization: Bearer ${token}"`;
const mcpConfig = (endpoint: string, token: string) =>
  JSON.stringify({ mcpServers: { stillopen: { type: "http", url: endpoint, headers: { Authorization: `Bearer ${token}` } } } }, null, 2);

function CopyBlock({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ fontWeight: "600", marginBottom: 4 }}>{label}</Text>
      <Text selectable style={{ fontSize: 12 }}>
        {text}
      </Text>
      <Button
        variant="secondary"
        label={copied ? "Copied" : "Copy"}
        icon="copy-outline"
        style={{ marginTop: 6 }}
        onPress={async () => {
          await Clipboard.setStringAsync(text);
          setCopied(true);
        }}
      />
    </View>
  );
}

export default function AssistantScreen() {
  const router = useRouter();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => accountApi.assistant());
  const [name, setName] = useState("");
  const [access, setAccess] = useState("read");
  const [expires, setExpires] = useState<number | null>(90);
  // The raw token lives in this state only: shown once, gone when the person closes it or leaves the screen.
  const [made, setMade] = useState<NewToken | null>(null);
  const make = useAction();
  const revoke = useAction();

  if (loading) return <Screen title="Assistant"><Loading /></Screen>;
  if (!data) {
    const off = error?.toLowerCase().includes("not available") || error?.includes("404");
    return (
      <Screen title="Assistant">
        {off ? (
          <Empty title="Not switched on" hint="Connecting an AI assistant is not switched on for this site. Ask the person who runs it to turn it on." action={{ label: "Back to your profile", onPress: () => router.back() }} />
        ) : (
          <ErrorBox message={error ?? "We could not load your tokens."} onRetry={reload} />
        )}
      </Screen>
    );
  }

  const create = async () => {
    const result = await make.run(() => accountApi.makeToken({ name, access, expires: expires ?? 90 }));
    if (!result) return;
    setMade(result);
    setName("");
    await reload();
  };

  return (
    <Screen title="Assistant" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 14 }}>
        Make a private token and give it to Claude Code or any other AI assistant that supports MCP. The assistant can then read and update your job search here: list your jobs, judge fit from your CV, tailor a CV, add notes and track interviews. It never sees
        anyone else&apos;s data, it can never delete anything, and it never applies to a job or sends a message for you.
      </Muted>

      {made ? (
        <Card>
          <Heading>{`Your new token: ${made.record.name}`}</Heading>
          <Text style={{ fontWeight: "700", marginBottom: 10 }}>Copy it now. It is shown only once and cannot be recovered. Treat it like a password.</Text>
          <CopyBlock label="Token" text={made.token} />
          <CopyBlock label="Claude Code: paste this in a terminal (one line)" text={claudeCommand(made.endpoint, made.token)} />
          <CopyBlock label="Other assistants (Cursor, Windsurf and similar): add this to their MCP settings" text={mcpConfig(made.endpoint, made.token)} />
          <Muted style={{ marginBottom: 10 }}>
            {made.record.can_write ? "This token can read and make changes (add jobs, notes, interviews, saved evaluations and tailored CVs)." : "This token is read-only."}{" "}
            {made.record.expires_at ? `It stops working on ${dayText(made.record.expires_at)}.` : "It does not expire."}
          </Muted>
          <Button label="I have copied it" onPress={() => setMade(null)} />
        </Card>
      ) : null}

      <SectionTitle>Make a token</SectionTitle>
      <Card>
        <Field label="What is it for?" value={name} onChangeText={setName} maxLength={60} placeholder="Claude Code on my laptop" error={make.fields?.name} />
        <Select
          label="Access"
          value={access}
          options={[
            { value: "read", label: "Read only" },
            { value: "write", label: "Read and make changes" },
          ]}
          onChange={setAccess}
        />
        <Select label="Stops working after" value={expires} options={data.expiry_choices.map((c) => ({ value: c.days, label: c.label }))} onChange={setExpires} />
        {make.error ? <ErrorBox message={make.error} /> : null}
        <Button label="Make token" busy={make.busy} disabled={!name.trim()} onPress={create} />
        <Muted style={{ marginTop: 10 }}>
          You can have {data.limit} active tokens. Start with read only; switch to making changes when you trust the assistant with it. What it reads (your CV and notes) goes to the AI company behind that assistant, so use one you are comfortable with.
        </Muted>
      </Card>

      <SectionTitle>Your tokens</SectionTitle>
      {revoke.error ? <ErrorBox message={revoke.error} /> : null}
      {data.tokens.length === 0 ? (
        <Empty title="No tokens yet" hint="Make one above, then paste the command it gives you into Claude Code." />
      ) : (
        data.tokens.map((t) => (
          <Card key={t.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <Text style={{ fontWeight: "700", flex: 1 }}>{t.name}</Text>
              {t.state !== "Active" ? <Badge label={t.state} /> : null}
            </View>
            <Muted>Starts with {t.hint}…</Muted>
            <Muted>
              {t.can_write ? "Read and change" : "Read only"} · last used {lastUsed(t.last_used_at)}
            </Muted>
            <Muted>{t.expires_at ? `Stops working ${dayText(t.expires_at)}` : "Does not expire"}</Muted>
            {!t.revoked ? (
              <Button
                variant="danger"
                label="Revoke"
                busy={revoke.busy}
                style={{ marginTop: 8 }}
                onPress={async () => {
                  if (!(await confirm(`Revoke ${t.name}?`, "It stops working straight away.", "Revoke"))) return;
                  const ok = await revoke.run(() => accountApi.revokeToken(t.id));
                  if (ok) {
                    notify(`Revoked ${t.name}.`, "It stops working straight away.");
                    await reload();
                  }
                }}
              />
            ) : null}
          </Card>
        ))
      )}
      <Body style={{ marginTop: 8 }}>What to try</Body>
      <Muted>Once connected, ask your assistant things like: &ldquo;Give me a summary of my job search and what to apply to next.&rdquo; or &ldquo;Tailor my CV for the Acme role, using only what my CV says.&rdquo;</Muted>
      <Muted style={{ marginTop: 8 }}>
        Lost a phone or shared a token by mistake? Revoke it above and it stops working immediately. The address the assistant connects to is {data.endpoint}.
      </Muted>
    </Screen>
  );
}
