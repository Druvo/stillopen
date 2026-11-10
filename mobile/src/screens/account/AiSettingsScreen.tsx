import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";

import { accountApi, type AiSettings, type AiSettingsValues, type Preset } from "../../api/account";
import { Badge, Body, Button, Card, ErrorBox, Field, Loading, Muted, Screen, SectionTitle, Select, Text, Toggle } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";

const AI_STUDIO_KEYS = "https://aistudio.google.com/apikey";
const GOOGLE_HOST = "generativelanguage.googleapis.com";

/** Quick setup: the provider, address and model a preset fills in. The key is never part of it. */
function applyPreset(preset: Preset) {
  return { ai_provider: preset.provider, ai_base_url: preset.base_url, ai_model: preset.model };
}

export default function AiSettingsScreen() {
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => accountApi.ai());
  return (
    <Screen title="AI settings" onRefresh={refresh} refreshing={refreshing}>
      {loading ? <Loading /> : error && !data ? <ErrorBox message={error} onRetry={reload} /> : data ? <AiForm initial={data} /> : null}
    </Screen>
  );
}

function AiForm({ initial }: { initial: AiSettings }) {
  const router = useRouter();
  const [current, setCurrent] = useState(initial);
  const [values, setValues] = useState<AiSettingsValues>(initial.settings);
  // Keys live only in these boxes while they are typed. They are cleared on every save and never read back from the server.
  const [aiKey, setAiKey] = useState("");
  const [ragKey, setRagKey] = useState("");
  const [clearAi, setClearAi] = useState(false);
  const [clearRag, setClearRag] = useState(false);
  const [saved, setSaved] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [presetKey, setPresetKey] = useState<string | null>(null);
  const action = useAction();
  const usesGoogle = values.ai_base_url.includes(GOOGLE_HOST);
  const limit = (key: string): [number, number] => current.limits[key] ?? [0, 0];
  const fieldError = (key: string) => action.fields?.[key];

  useEffect(() => {
    if (action.fields && Object.keys(action.fields).some((k) => k !== "ai_api_key")) setAdvanced(true); // a refused advanced field must not stay hidden
  }, [action.fields]);

  const set = <K extends keyof AiSettingsValues>(key: K, value: AiSettingsValues[K]) => {
    setSaved(false);
    setValues((v) => ({ ...v, [key]: value }));
  };
  const text = (key: keyof AiSettingsValues) => ({ value: String(values[key]), onChangeText: (t: string) => set(key, t as never), error: fieldError(key) });

  const save = async () => {
    const body: Record<string, unknown> = { ...values };
    if (aiKey) body.ai_api_key = aiKey;
    if (ragKey) body.rag_embedding_key = ragKey;
    if (clearAi) body.clear_ai_key = true;
    if (clearRag) body.clear_rag_key = true;
    const next = await action.run(() => accountApi.saveAi(body));
    if (!next) return;
    setCurrent(next);
    setValues(next.settings);
    setAiKey("");
    setRagKey("");
    setClearAi(false);
    setClearRag(false);
    setSaved(true);
  };

  const numberField = (key: keyof AiSettingsValues, label: string, limitKey: string) => {
    const [low, high] = limit(limitKey);
    return <Field label={label} keyboardType="numeric" hint={`Between ${low.toLocaleString()} and ${high.toLocaleString()}.`} {...text(key)} />;
  };

  return (
    <>
      <Muted style={{ marginBottom: 14 }}>
        You do not need to set anything up here. Without an AI, StillOpen does a quick keyword check of each job against your CV, and that is free. If you would like a more careful read, connect your own AI account below. When you press Check my fit, the job
        text and the relevant parts of your CV are sent to that provider, and only then.
      </Muted>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 4 }}>AI usage this month</Text>
        {current.usage.calls ? (
          <>
            <Body>
              {current.usage.calls} paid-provider call{current.usage.calls === 1 ? "" : "s"}
              {current.usage.total_tokens ? ` · about ${current.usage.total_tokens.toLocaleString()} tokens` : ""}
              {current.usage.cost_usd ? ` · about $${current.usage.cost_usd}` : ""}
              {current.usage.cost_usd && current.usage.any_estimated ? " (estimated for some calls; provider prices change)" : ""}
            </Body>
            <Button variant="ghost" label="See the details" onPress={() => router.push("/profile/usage")} />
            <Muted>The free keyword match never appears here. It costs nothing and makes no network call.</Muted>
          </>
        ) : (
          <Muted>No paid AI calls yet this month. The free keyword match does not count; it is always free.</Muted>
        )}
      </Card>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 6 }}>Connect an AI (optional)</Text>
        <Muted style={{ marginBottom: 8 }}>Easiest start: a free Google AI Studio key. Create one with any Google account, choose Google AI Studio (Gemini) below, paste the key and press Save.</Muted>
        <Button variant="secondary" label="Open Google AI Studio" icon="open-outline" onPress={() => void Linking.openURL(AI_STUDIO_KEYS)} style={{ marginBottom: 14 }} />
        <Select
          label="1. Quick setup: choose your provider"
          placeholder={current.provider_label ? `Now using: ${current.provider_label}. Choose another to switch…` : "Choose a provider…"}
          value={presetKey}
          options={current.presets.map((p) => ({ value: p.key, label: p.label }))}
          onChange={(key) => {
            const preset = current.presets.find((p) => p.key === key);
            if (!preset) return;
            setPresetKey(key); // a one-shot helper: nothing is stored until Save
            setSaved(false);
            setValues((v) => ({ ...v, ...applyPreset(preset) }));
          }}
        />
        <Field
          label={current.has_key ? "2. Paste your API key (one is saved)" : "2. Paste your API key"}
          hint="You get this from your provider's website. It is stored encrypted and never shown again. Leave it blank to keep the saved one."
          value={aiKey}
          onChangeText={setAiKey}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="off"
          textContentType="none"
          error={fieldError("ai_api_key")}
        />
        {current.has_key ? <Badge label="Key saved" /> : null}
        {usesGoogle ? (
          <Muted style={{ marginTop: 10 }}>
            With this key, the job text and the parts of your CV needed for a check are sent to Google, and only when you press Check my fit. On Google&apos;s free tier, Google may use what you send to improve its products, so choose a paid key or another
            provider if that matters to you.
          </Muted>
        ) : null}
      </Card>

      <Button variant="secondary" label={advanced ? "Hide advanced options" : "Show advanced options"} onPress={() => setAdvanced((a) => !a)} style={{ marginBottom: 12 }} />
      {advanced ? (
        <Card>
          <Muted style={{ marginBottom: 10 }}>Most people never need these. They set how StillOpen talks to the provider, how much of your CV the AI sees and how long it may take.</Muted>
          <SectionTitle>How it connects</SectionTitle>
          <Select label="AI provider" value={values.ai_provider} options={current.providers.map((p) => ({ value: p.value, label: p.label }))} onChange={(v) => set("ai_provider", v)} />
          <Field label="AI model" hint="Leave blank for the provider's default." autoCapitalize="none" autoCorrect={false} {...text("ai_model")} />
          <Field label="AI base URL" hint="OpenAI-compatible: the API base, for example https://openrouter.ai/api/v1. Custom HTTP: the full endpoint address." autoCapitalize="none" autoCorrect={false} keyboardType="url" {...text("ai_base_url")} />
          <Toggle label="Delete the saved AI key" value={clearAi} onChange={setClearAi} />
          <Field label="Custom HTTP headers" hint="Custom HTTP only. One header per line, for example Authorization: Bearer {{api_key}}." multiline autoCapitalize="none" autoCorrect={false} {...text("ai_custom_headers")} />
          <Field label="Custom HTTP body" hint="Custom HTTP only. A JSON request body. Use {{system}}, {{prompt}} and {{model}} where the text goes." multiline autoCapitalize="none" autoCorrect={false} {...text("ai_custom_body")} />
          <Field label="Custom HTTP response path" hint="Custom HTTP only. Where the reply text is in the answer, for example choices.0.message.content." autoCapitalize="none" autoCorrect={false} {...text("ai_custom_response_path")} />

          <SectionTitle>Which parts of your CV the AI sees</SectionTitle>
          <Toggle label="Send the AI only the parts of your CV and documents that are relevant to each job" value={values.rag_enabled} onChange={(v) => set("rag_enabled", v)} />
          <Select label="How to pick the parts" value={values.rag_mode} options={current.rag_modes.map((m) => ({ value: m.value, label: m.label }))} onChange={(v) => set("rag_mode", v)} />
          {numberField("rag_top_k", "How many passages per job", "rag_top_k")}
          {numberField("rag_chunk_chars", "Size of one passage (characters)", "rag_chunk_chars")}
          {numberField("rag_always_chars", "Always include the opening of your CV (characters)", "rag_always_chars")}
          <Field label="Embeddings base URL" hint="Embeddings mode only. Blank uses the AI base URL." autoCapitalize="none" autoCorrect={false} {...text("rag_embedding_base_url")} />
          <Field label="Embeddings model" hint="For example text-embedding-3-small." autoCapitalize="none" autoCorrect={false} {...text("rag_embedding_model")} />
          <Field
            label={current.has_rag_key ? "Embeddings API key (one is saved)" : "Embeddings API key"}
            hint="Optional. If empty, your AI key is used for embeddings too. Stored encrypted and never shown again."
            value={ragKey}
            onChangeText={setRagKey}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            textContentType="none"
            error={fieldError("rag_embedding_key")}
          />
          <Toggle label="Delete the saved embeddings key" value={clearRag} onChange={setClearRag} />

          <SectionTitle>Limits</SectionTitle>
          {numberField("ai_timeout", "Seconds to wait for one answer", "ai_timeout")}
          {numberField("ai_max_input_chars", "Longest job text sent (characters)", "ai_max_input_chars")}
        </Card>
      ) : null}

      {action.error ? <ErrorBox message={action.error} /> : null}
      {saved && !action.error ? <Muted style={{ marginBottom: 10 }}>AI settings saved.</Muted> : null}
      <Button label="Save AI settings" busy={action.busy} onPress={save} />
    </>
  );
}
