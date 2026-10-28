"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { Bar, Chart } from "@/features/stats/charts";
import { errorText, request } from "@/lib/api";
import { Link } from "@/lib/router";

export type AiUsage = {
  month: string;
  calls: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  costs: { currency: string; amount: number }[];
  any_estimated: boolean;
  unpriced_calls: number;
  latency: { samples: number; p50_ms: number | null; p95_ms: number | null };
  models: { provider: string; model: string; currency: string; calls: number; input_tokens: number; output_tokens: number; cost: number | null; unpriced_calls: number; estimated: boolean }[];
  purposes: { purpose: string; label: string; calls: number; failed: number; input_tokens: number; output_tokens: number }[];
  recent: { id: number; at: string; purpose: string; provider: string; model: string; input_tokens: number | null; output_tokens: number | null; cost: number | null; currency: string; duration_ms: number | null; ok: boolean }[];
};

export function seconds(ms: number | null): string {
  if (ms === null) return "not recorded";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function money(amount: number, currency: string): string {
  return `${currency === "USD" ? "$" : `${currency} `}${amount.toFixed(amount < 1 ? 4 : 2)}`;
}

const n = (value: number | null) => (value === null ? "not reported" : value.toLocaleString());

export function UsagePage() {
  const query = useQuery({ queryKey: ["account", "ai-usage"], queryFn: () => request<AiUsage>("GET", "/ai-usage") });
  if (query.isPending) return <Loading what="your AI usage" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your AI usage.")} onRetry={() => query.refetch()} />;
  const u = query.data;
  const max = Math.max(1, ...u.purposes.map((p) => p.calls));
  return (
    <>
      <PageHeader title="AI usage" subtitle={`This month (${u.month}). Only numbers are kept here, never what you asked or what came back.`} actions={<Link to="/profile/ai" className="link-target text-brand underline">Back to AI settings</Link>} />
      {u.calls === 0 && u.recent.length === 0 ? (
        <Card>
          <p className="text-theme-sm">No AI calls yet. When you check a fit, tailor a CV or ask for changes with your own AI, each call shows here. The free keyword match never does.</p>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card>
            <h2 className="font-semibold">This month</h2>
            <ul className="mt-2 grid gap-3 sm:grid-cols-3">
              <li><span className="block text-2xl font-semibold tabular-nums">{u.calls}</span>calls{u.failed > 0 && <>, <Badge tone="bad">{u.failed} failed</Badge></>}</li>
              <li><span className="block text-2xl font-semibold tabular-nums">{u.input_tokens.toLocaleString()}</span>tokens sent</li>
              <li><span className="block text-2xl font-semibold tabular-nums">{u.output_tokens.toLocaleString()}</span>tokens received</li>
            </ul>
            <p className="mt-3 text-theme-sm">
              {u.costs.length ? (
                <>About {u.costs.map((c) => money(c.amount, c.currency)).join(" and ")}{u.any_estimated ? " (an estimate: provider prices change)" : ""}.</>
              ) : (
                "No cost to show: none of the models used has a known price."
              )}
              {u.unpriced_calls > 0 && ` ${u.unpriced_calls} call${u.unpriced_calls === 1 ? "" : "s"} used a model with no known price, so no cost is guessed for ${u.unpriced_calls === 1 ? "it" : "them"}.`}
            </p>
            <p className="mt-1 text-theme-sm text-muted">
              {u.latency.samples ? `Time to answer: typically ${seconds(u.latency.p50_ms)}, slowest 1 in 20 about ${seconds(u.latency.p95_ms)} (${u.latency.samples} timed calls).` : "Time to answer is only recorded for newer calls."}
            </p>
          </Card>

          <Card>
            <Chart
              caption="Calls by what they were for"
              table={
                <table>
                  <caption>Calls by purpose</caption>
                  <thead><tr><th scope="col">Purpose</th><th scope="col">Calls</th><th scope="col">Failed</th></tr></thead>
                  <tbody>{u.purposes.map((p) => <tr key={p.purpose}><th scope="row">{p.label}</th><td>{p.calls}</td><td>{p.failed}</td></tr>)}</tbody>
                </table>
              }
            >
              <div className="space-y-1">{u.purposes.map((p) => <Bar key={p.purpose} label={p.label} value={p.calls} max={max} />)}</div>
            </Chart>
          </Card>

          <Card>
            <h2 className="font-semibold">By model</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-theme-sm">
                <caption className="sr-only">Calls, tokens and cost for each model this month</caption>
                <thead><tr><th scope="col" className="py-1 pr-3">Model</th><th scope="col" className="pr-3">Calls</th><th scope="col" className="pr-3">Tokens in / out</th><th scope="col">Cost</th></tr></thead>
                <tbody>
                  {u.models.map((m) => (
                    <tr key={`${m.provider}/${m.model}`} className="border-t border-border">
                      <th scope="row" className="py-1 pr-3 font-normal">{m.model || m.provider}</th>
                      <td className="pr-3 tabular-nums">{m.calls}</td>
                      <td className="pr-3 tabular-nums">{m.input_tokens.toLocaleString()} / {m.output_tokens.toLocaleString()}</td>
                      <td>{m.cost === null ? "no known price" : `${money(m.cost, m.currency)}${m.estimated ? " (estimate)" : ""}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h2 className="font-semibold">Your last {u.recent.length} calls</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-theme-sm">
                <caption className="sr-only">Your most recent AI calls</caption>
                <thead><tr><th scope="col" className="py-1 pr-3">When</th><th scope="col" className="pr-3">For</th><th scope="col" className="pr-3">Model</th><th scope="col" className="pr-3">Tokens in / out</th><th scope="col" className="pr-3">Took</th><th scope="col">Result</th></tr></thead>
                <tbody>
                  {u.recent.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-1 pr-3 whitespace-nowrap">{new Date(r.at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                      <td className="pr-3">{r.purpose}</td>
                      <td className="pr-3">{r.model || r.provider}</td>
                      <td className="pr-3 tabular-nums">{n(r.input_tokens)} / {n(r.output_tokens)}</td>
                      <td className="pr-3">{seconds(r.duration_ms)}</td>
                      <td>{r.ok ? <Badge tone="good">Worked</Badge> : <Badge tone="bad">Failed</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
