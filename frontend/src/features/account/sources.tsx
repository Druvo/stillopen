"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, SelectField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { accountApi } from "./api";

const KEY = ["account", "sources"] as const;

export function SourcesPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: accountApi.sources });
  const [connector, setConnector] = useState("");
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [done, setDone] = useState("");
  const [rowError, setRowError] = useState("");
  const form = useSubmit();
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
    onError: (e) => setRowError(errorText(e)),
  });

  if (query.isPending) return <Loading what="your job sources" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your job sources.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const chosen = connector || data.connectors[0]?.value || "";

  const add = form.handle(async () => {
    setDone("");
    const result = await accountApi.addSource({ connector: chosen, board_token: token, name });
    setDone(result.message);
    setToken("");
    setName("");
    await client.invalidateQueries({ queryKey: KEY });
  });

  return (
    <>
      <PageHeader title="Where we look for jobs" />
      <p className="mb-4 text-sm text-muted">
        You do not need to set anything up. We already search {data.shared.length} job sources for you automatically, whenever you open your dashboard, and keep the openings that match what you are looking for and where you would work. Add a
        company below only if you want one we do not cover. Your own list is private to you.
      </p>
      <div className="space-y-4">
        <Card>
          <h2 className="mb-3 font-semibold">Add a company</h2>
          <form onSubmit={add}>
            <SelectField label="Which hiring system does the company use?" hint={data.help.connector} value={chosen} onChange={(e) => setConnector(e.target.value)} errors={form.fields.connector}>
              {data.connectors.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </SelectField>
            <TextField
              label="The company's name in that address, or paste the careers page address"
              hint={data.help.board_token}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              errors={form.fields.board_token}
              required
            />
            <TextField label="Company name (optional)" hint="Shown in your search log. Defaults to the name from the address." value={name} onChange={(e) => setName(e.target.value)} errors={form.fields.name} />
            <FormError message={form.error} />
            {done && !form.error && <div className="mb-3"><Notice tone="success">{done}</Notice></div>}
            <Button type="submit" disabled={form.busy}>
              {form.busy ? "Checking…" : "Check and add"}
            </Button>
            <p className="mt-2 text-xs text-muted">We read that company&apos;s public job list once to make sure it works. You can have up to {data.limit}.</p>
          </form>
        </Card>

        <section aria-label="Your companies">
          <h2 className="mb-2 font-semibold">Your companies</h2>
          {rowError && <div className="mb-2"><Notice tone="error">{rowError}</Notice></div>}
          {data.mine.length === 0 ? (
            <p className="text-sm text-muted">None yet. Add a company whose careers page you check often.</p>
          ) : (
            <ul className="space-y-2">
              {data.mine.map((s) => (
                <li key={s.id}>
                  <Card className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <strong>{s.name}</strong> {!s.enabled && <Badge tone="warn">paused</Badge>}
                      <p className="text-sm text-muted">
                        {s.connector_label} · {s.board_token}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        small
                        disabled={act.isPending}
                        onClick={() => {
                          setRowError("");
                          act.mutate(() => accountApi.toggleSource(s.id));
                        }}
                      >
                        {s.enabled ? "Pause" : "Resume"}
                      </Button>
                      <Button
                        variant="danger"
                        small
                        disabled={act.isPending}
                        onClick={() => {
                          if (!window.confirm("Remove this company from your searches?")) return;
                          setRowError("");
                          act.mutate(() => accountApi.removeSource(s.id));
                        }}
                      >
                        Remove
                      </Button>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>

        {data.shared.length > 0 && (
          <details>
            <summary className="cursor-pointer text-sm text-muted">Already searched for everyone ({data.shared.length}). Show the list</summary>
            <p className="mt-2 text-sm text-muted">{data.shared.join(", ")}</p>
          </details>
        )}
      </div>
    </>
  );
}
