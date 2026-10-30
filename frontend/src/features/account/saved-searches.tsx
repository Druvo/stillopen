"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { accountApi } from "./api";

const KEY = ["account", "saved-searches"] as const;

export function SavedSearchesPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: accountApi.savedSearches });
  const [name, setName] = useState("");
  const [roles, setRoles] = useState("");
  const [rowError, setRowError] = useState("");
  const form = useSubmit();
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
    onError: (e) => setRowError(errorText(e)),
  });

  if (query.isPending) return <Loading what="your saved searches" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your saved searches.")} onRetry={() => query.refetch()} />;
  const searches = query.data.saved_searches;

  const add = form.handle(async () => {
    await accountApi.addSavedSearch({ name, target_roles: roles });
    setName("");
    setRoles("");
    await client.invalidateQueries({ queryKey: KEY });
    notify(`Saved "${name}".`);
  });

  return (
    <>
      <PageHeader title="Saved searches" />
      <p className="mb-4 text-sm text-muted">
        Extra, named lists of roles searched alongside the roles on your profile &mdash; &ldquo;Remote Backend Roles&rdquo; as well as &ldquo;Dhaka On-site, Any Role&rdquo;, say. Each is included in your search and scheduled digest only
        while it is on; turn one off without losing it.
      </p>
      <div className="space-y-4">
        <Card>
          <h2 className="mb-3 font-semibold">Add a saved search</h2>
          <form onSubmit={add}>
            <TextField label="Name" hint="A short name for this search." value={name} onChange={(e) => setName(e.target.value)} errors={form.fields.name} required />
            <TextAreaField
              label="Roles (one per line)"
              rows={3}
              placeholder={"Senior Backend Engineer\nSolutions Architect"}
              value={roles}
              onChange={(e) => setRoles(e.target.value)}
              errors={form.fields.target_roles}
              required
            />
            <FormError message={form.error} />
            <Button type="submit" disabled={form.busy}>
              {form.busy ? "Saving…" : "Save search"}
            </Button>
            <p className="mt-2 text-xs text-muted">You can have up to 10.</p>
          </form>
        </Card>

        <section aria-label="Your saved searches">
          <h2 className="mb-2 font-semibold">Your saved searches</h2>
          {rowError && <div className="mb-2"><Notice tone="error">{rowError}</Notice></div>}
          {searches.length === 0 ? (
            <p className="text-sm text-muted">None yet. Your profile&apos;s own roles are still searched either way.</p>
          ) : (
            <ul className="space-y-2">
              {searches.map((s) => (
                <li key={s.id}>
                  <Card className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <strong>{s.name}</strong> {!s.enabled && <Badge tone="warn">off</Badge>}
                      <p className="whitespace-pre-line text-sm text-muted">{s.target_roles}</p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        small
                        disabled={act.isPending}
                        onClick={() => {
                          setRowError("");
                          act.mutate(() => accountApi.toggleSavedSearch(s.id, !s.enabled));
                        }}
                      >
                        {s.enabled ? "Turn off" : "Turn on"}
                      </Button>
                      <Button
                        variant="danger"
                        small
                        disabled={act.isPending}
                        onClick={() => {
                          if (!window.confirm(`Delete "${s.name}"?`)) return;
                          setRowError("");
                          act.mutate(async () => {
                            await accountApi.removeSavedSearch(s.id);
                            notify("Deleted.");
                          });
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
