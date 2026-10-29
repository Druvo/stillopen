"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { CheckField, FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import type { AiSettings, AiSettingsValues } from "./api";
import { accountApi } from "./api";
import { applyPreset } from "./logic";

const KEY = ["account", "ai"] as const;

export function AiSettingsPage() {
  const query = useQuery({ queryKey: KEY, queryFn: accountApi.ai });
  if (query.isPending) return <Loading what="your AI settings" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your AI settings.")} onRetry={() => query.refetch()} />;
  return <AiScreen data={query.data} />;
}

function Usage({ usage }: { usage: AiSettings["usage"] }) {
  return (
    <Card>
      <h2 className="font-semibold">AI usage this month</h2>
      {usage.calls ? (
        <>
          <p className="mt-1 text-sm">
            {usage.calls} paid-provider call{usage.calls === 1 ? "" : "s"}
            {usage.total_tokens ? ` · about ${usage.total_tokens.toLocaleString()} tokens` : ""}
            {usage.cost_usd ? ` · about $${usage.cost_usd}` : ""}
            {usage.cost_usd && usage.any_estimated ? " (estimated for some calls; provider prices change, so this is approximate)" : ""}
          </p>
          <p className="text-xs text-muted">The free keyword match (no AI provider) never appears here. It costs nothing and makes no network call.</p>
        </>
      ) : (
        <p className="mt-1 text-sm text-muted">No paid AI calls yet this month. The free keyword match does not count; it is always free.</p>
      )}
    </Card>
  );
}

function AiScreen({ data }: { data: AiSettings }) {
  const client = useQueryClient();
  const [current, setCurrent] = useState(data);
  const [values, setValues] = useState<AiSettingsValues>(data.settings);
  // Keys live only in these boxes while they are typed. They are cleared on every save and never read back from the server.
  const [aiKey, setAiKey] = useState("");
  const [ragKey, setRagKey] = useState("");
  const [clearAi, setClearAi] = useState(false);
  const [clearRag, setClearRag] = useState(false);
  const [saved, setSaved] = useState(false);
  const form = useSubmit();

  const set = <K extends keyof AiSettingsValues>(key: K, value: AiSettingsValues[K]) => {
    setSaved(false);
    setValues((v) => ({ ...v, [key]: value }));
  };
  const text = (key: keyof AiSettingsValues) => ({
    value: String(values[key]),
    onChange: (e: { target: { value: string } }) => set(key, e.target.value as never),
    errors: form.fields[key],
  });
  const limit = (key: string) => current.limits[key];

  const save = form.handle(async () => {
    const body: Record<string, unknown> = { ...values };
    if (aiKey) body.ai_api_key = aiKey;
    if (ragKey) body.rag_embedding_key = ragKey;
    if (clearAi) body.clear_ai_key = true;
    if (clearRag) body.clear_rag_key = true;
    const next = await accountApi.saveAi(body);
    setCurrent(next);
    setValues(next.settings);
    client.setQueryData(KEY, next);
    setAiKey("");
    setRagKey("");
    setClearAi(false);
    setClearRag(false);
    setSaved(true);
  });

  const hasAdvancedError = Object.keys(form.fields).some((name) => name !== "ai_api_key"); // a refused advanced field must not stay hidden
  const usingProvider = current.provider_label ? `Now using: ${current.provider_label}. Choose another to switch…` : "Choose a provider…";

  return (
    <>
      <PageHeader title="AI settings" />
      <p className="mb-4 text-sm text-muted">
        You do not need to set anything up here. Without an AI, StillOpen does a quick keyword check of each job against your CV, and that is free. If you would like a more careful read, connect your own AI account below. When you press Check my
        fit, the job text and the relevant parts of your CV are sent to that provider, and only then.
      </p>
      <div className="space-y-4">
        <Usage usage={current.usage} />
        <form onSubmit={save} className="space-y-4" autoComplete="off">
          <Card>
            <h2 className="mb-3 font-semibold">
              Connect an AI <span className="text-sm font-normal text-muted">(optional)</span>
            </h2>
            <SelectField
              label="1. Choose your AI provider"
              hint="This fills in the technical details for you. Then paste your API key below and press Save."
              value=""
              onChange={(e) => {
                const preset = current.presets.find((p) => p.key === e.target.value);
                if (!preset) return;
                setSaved(false);
                setValues((v) => ({ ...v, ...applyPreset(preset) })); // a one-shot helper: nothing is stored until Save
              }}
            >
              <option value="">{usingProvider}</option>
              {current.presets.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </SelectField>
            <TextField
              label={
                <>
                  2. Paste your API key {current.has_key && <Badge tone="good">saved</Badge>}
                </>
              }
              hint="You get this from your provider's website. It is stored encrypted and never shown again. Leave it blank to keep the saved one."
              type="password"
              autoComplete="new-password"
              value={aiKey}
              onChange={(e) => setAiKey(e.target.value)}
              errors={form.fields.ai_api_key}
            />
          </Card>

          <details open={hasAdvancedError || undefined} className="rounded-xl border border-border bg-surface p-4">
            <summary className="cursor-pointer font-semibold">Advanced options</summary>
            <p className="my-2 text-sm text-muted">Most people never need these. They set how StillOpen talks to the provider, how much of your CV the AI sees and how long it may take.</p>

            <h3 className="mt-4 mb-2 font-medium">How it connects</h3>
            <SelectField label="AI provider" value={values.ai_provider} onChange={(e) => set("ai_provider", e.target.value)} errors={form.fields.ai_provider}>
              {current.providers.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </SelectField>
            <TextField label="AI model" hint="Leave blank for the provider's default." {...text("ai_model")} />
            <TextField label="AI base URL" hint="OpenAI-compatible: the API base, for example https://openrouter.ai/api/v1. Custom HTTP: the full endpoint address." {...text("ai_base_url")} />
            <CheckField label="Delete the saved AI key" checked={clearAi} onChange={(e) => setClearAi(e.target.checked)} />
            <TextAreaField label="Custom HTTP headers" hint="Custom HTTP only. One header per line, for example Authorization: Bearer {{api_key}}." rows={3} {...text("ai_custom_headers")} />
            <TextAreaField label="Custom HTTP body" hint="Custom HTTP only. A JSON request body. Use {{system}}, {{prompt}} and {{model}} where the text goes." rows={5} {...text("ai_custom_body")} />
            <TextField label="Custom HTTP response path" hint="Custom HTTP only. Where the reply text is in the answer, for example choices.0.message.content." {...text("ai_custom_response_path")} />

            <h3 className="mt-4 mb-2 font-medium">Which parts of your CV the AI sees</h3>
            <CheckField
              label="Send the AI only the parts of your CV and documents that are relevant to each job"
              checked={values.rag_enabled}
              onChange={(e) => set("rag_enabled", e.target.checked)}
              errors={form.fields.rag_enabled}
            />
            <SelectField label="How to pick the parts" value={values.rag_mode} onChange={(e) => set("rag_mode", e.target.value)} errors={form.fields.rag_mode}>
              {current.rag_modes.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </SelectField>
            <TextField label="How many passages per job" type="number" min={limit("rag_top_k")[0]} max={limit("rag_top_k")[1]} hint={`Between ${limit("rag_top_k")[0]} and ${limit("rag_top_k")[1]}.`} {...text("rag_top_k")} />
            <TextField
              label="Size of one passage (characters)"
              type="number"
              min={limit("rag_chunk_chars")[0]}
              max={limit("rag_chunk_chars")[1]}
              hint={`Between ${limit("rag_chunk_chars")[0]} and ${limit("rag_chunk_chars")[1]}.`}
              {...text("rag_chunk_chars")}
            />
            <TextField
              label="Always include the opening of your CV (characters)"
              type="number"
              min={limit("rag_always_chars")[0]}
              max={limit("rag_always_chars")[1]}
              hint={`Between ${limit("rag_always_chars")[0]} and ${limit("rag_always_chars")[1]}.`}
              {...text("rag_always_chars")}
            />
            <TextField label="Embeddings base URL" hint="Embeddings mode only. Blank uses the AI base URL." {...text("rag_embedding_base_url")} />
            <TextField label="Embeddings model" hint="For example text-embedding-3-small." {...text("rag_embedding_model")} />
            <TextField
              label={
                <>
                  Embeddings API key {current.has_rag_key && <Badge tone="good">saved</Badge>}
                </>
              }
              hint="Optional. If empty, your AI key is used for embeddings too. Stored encrypted and never shown again."
              type="password"
              autoComplete="new-password"
              value={ragKey}
              onChange={(e) => setRagKey(e.target.value)}
              errors={form.fields.rag_embedding_key}
            />
            <CheckField label="Delete the saved embeddings key" checked={clearRag} onChange={(e) => setClearRag(e.target.checked)} />

            <h3 className="mt-4 mb-2 font-medium">Limits</h3>
            <TextField
              label="Seconds to wait for one answer"
              type="number"
              min={limit("ai_timeout")[0]}
              max={limit("ai_timeout")[1]}
              hint={`Between ${limit("ai_timeout")[0]} and ${limit("ai_timeout")[1]}.`}
              {...text("ai_timeout")}
            />
            <TextField
              label="Longest job text sent (characters)"
              type="number"
              min={limit("ai_max_input_chars")[0]}
              max={limit("ai_max_input_chars")[1]}
              hint={`Between ${limit("ai_max_input_chars")[0].toLocaleString()} and ${limit("ai_max_input_chars")[1].toLocaleString()}. Longer job text is cut before it is sent.`}
              {...text("ai_max_input_chars")}
            />
          </details>

          <FormError message={form.error} />
          {saved && !form.error && <Notice tone="success">AI settings saved.</Notice>}
          <Button type="submit" disabled={form.busy}>
            {form.busy ? "Saving…" : "Save"}
          </Button>
        </form>
      </div>
    </>
  );
}
