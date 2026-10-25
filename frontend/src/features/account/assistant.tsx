"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, SelectField, TextField, useSubmit } from "@/components/form";
import { ApiError, errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { accountApi, type NewToken } from "./api";
import { claudeCommand, formatDate, lastUsed, mcpConfig } from "./logic";

const KEY = ["account", "assistant"] as const;

function CopyBlock({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{label}</p>
        <Button
          variant="outline"
          small
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
            } catch {
              setCopied(false); // the text is selectable below; copying by hand still works
            }
          }}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-md border border-border bg-surface-2 p-2 text-xs break-all whitespace-pre-wrap select-all">
        <code>{text}</code>
      </pre>
    </div>
  );
}

/** The one place the raw token is ever shown. It lives in this component's state only and is gone when the person leaves or closes it. */
function NewTokenCard({ made, onClose }: { made: NewToken; onClose: () => void }) {
  return (
    <Card className="border-good">
      <h2 className="font-semibold">Your new token: {made.record.name}</h2>
      <p className="my-2 text-sm font-medium text-bad">Copy it now. It is shown only once and cannot be recovered. Treat it like a password.</p>
      <CopyBlock label="Token" text={made.token} />
      <CopyBlock label="Claude Code: paste this in a terminal (one line)" text={claudeCommand(made.endpoint, made.token)} />
      <CopyBlock label="Other assistants (Cursor, Windsurf and similar): add this to their MCP settings" text={mcpConfig(made.endpoint, made.token)} />
      <p className="mb-3 text-sm text-muted">
        {made.record.can_write ? "This token can read and make changes (add jobs, notes, interviews, saved evaluations and tailored CVs)." : "This token is read-only."}{" "}
        {made.record.expires_at ? `It stops working on ${formatDate(made.record.expires_at)}.` : "It does not expire."}
      </p>
      <Button onClick={onClose}>I have copied it</Button>
    </Card>
  );
}

export function AssistantPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: accountApi.assistant, retry: false });
  const [name, setName] = useState("");
  const [access, setAccess] = useState("read");
  const [expires, setExpires] = useState(90);
  const [made, setMade] = useState<NewToken | null>(null);
  const [rowError, setRowError] = useState("");
  const form = useSubmit();
  const revoke = useMutation({
    mutationFn: (token: { id: number; name: string }) => accountApi.revokeToken(token.id),
    onSuccess: (_, token) => {
      notify(`Revoked ${token.name}. It stops working straight away.`);
      return client.invalidateQueries({ queryKey: KEY });
    },
    onError: (e) => setRowError(errorText(e)),
  });

  if (query.isPending) return <Loading what="your assistant tokens" />;
  if (query.isError) {
    const off = query.error instanceof ApiError && query.error.status === 404;
    return (
      <>
        <PageHeader title="Connect an AI assistant" />
        {off ? (
          <Card>
            <p className="text-sm">Connecting an AI assistant is not switched on for this site. Ask the person who runs it to turn it on.</p>
            <Link to="/profile" className={`${buttonClass("outline")} mt-3`}>
              Back to your profile
            </Link>
          </Card>
        ) : (
          <ErrorBox message={errorText(query.error, "We could not load your tokens.")} onRetry={() => query.refetch()} />
        )}
      </>
    );
  }
  const data = query.data;

  const make = form.handle(async () => {
    const result = await accountApi.makeToken({ name, access, expires });
    setMade(result);
    setName("");
    await client.invalidateQueries({ queryKey: KEY });
  });

  return (
    <>
      <PageHeader title="Connect an AI assistant" />
      <p className="mb-4 text-sm text-muted">
        Make a private token and give it to Claude Code or any other AI assistant that supports MCP. The assistant can then read and update <strong>your</strong> job search here: list your jobs, judge fit from your CV, tailor a CV, add notes and
        track interviews. It never sees anyone else&apos;s data, it can never delete anything, and it never applies to a job or sends a message for you.
      </p>
      <div className="space-y-4">
        {made && <NewTokenCard made={made} onClose={() => setMade(null)} />}

        <Card>
          <h2 className="mb-3 font-semibold">Make a token</h2>
          <form onSubmit={make} className="grid items-end gap-x-3 sm:grid-cols-4">
            <div className="sm:col-span-2">
              <TextField label="What is it for?" maxLength={60} placeholder="Claude Code on my laptop" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <SelectField label="Access" value={access} onChange={(e) => setAccess(e.target.value)}>
              <option value="read">Read only</option>
              <option value="write">Read and make changes</option>
            </SelectField>
            <SelectField label="Stops working after" value={expires} onChange={(e) => setExpires(Number(e.target.value))}>
              {data.expiry_choices.map((c) => (
                <option key={c.days} value={c.days}>
                  {c.label}
                </option>
              ))}
            </SelectField>
            <div className="sm:col-span-4">
              <FormError message={form.error} />
              <Button type="submit" disabled={form.busy}>
                {form.busy ? "Making…" : "Make token"}
              </Button>
            </div>
          </form>
          <p className="mt-3 text-xs text-muted">
            You can have {data.limit} active tokens. Start with read only; switch to making changes when you trust the assistant with it. What it reads (your CV and notes) goes to the AI company behind that assistant, so use one you are comfortable
            with.
          </p>
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Your tokens</h2>
          {rowError && <div className="mb-2"><Notice tone="error">{rowError}</Notice></div>}
          {data.tokens.length === 0 ? (
            <p className="text-sm text-muted">No tokens yet. Make one above, then paste the command it gives you into Claude Code.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Name</th>
                    <th className="py-1 pr-3 font-medium">Starts with</th>
                    <th className="py-1 pr-3 font-medium">Access</th>
                    <th className="py-1 pr-3 font-medium">Last used</th>
                    <th className="py-1 pr-3 font-medium">Stops working</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.tokens.map((t) => (
                    <tr key={t.id} className="border-t border-border">
                      <td className="py-2 pr-3">
                        {t.name} {t.state !== "Active" && <Badge>{t.state}</Badge>}
                      </td>
                      <td className="py-2 pr-3">
                        <code>{t.hint}…</code>
                      </td>
                      <td className="py-2 pr-3">{t.can_write ? "Read and change" : "Read only"}</td>
                      <td className="py-2 pr-3">{lastUsed(t.last_used_at)}</td>
                      <td className="py-2 pr-3">{formatDate(t.expires_at)}</td>
                      <td className="py-2 text-right">
                        {!t.revoked && (
                          <Button
                            variant="danger"
                            small
                            disabled={revoke.isPending}
                            onClick={() => {
                              if (!window.confirm(`Revoke ${t.name}? It stops working straight away.`)) return;
                              setRowError("");
                              revoke.mutate({ id: t.id, name: t.name });
                            }}
                          >
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <h2 className="mb-2 font-semibold">What to try</h2>
          <p className="mb-2 text-sm">Once connected, ask your assistant things like:</p>
          <ul className="mb-2 list-disc pl-5 text-sm">
            <li>&ldquo;Give me a summary of my job search and what to apply to next.&rdquo;</li>
            <li>&ldquo;Look at my saved jobs, judge each against my CV and save an honest match.&rdquo;</li>
            <li>&ldquo;Tailor my CV for the Acme role, using only what my CV says.&rdquo;</li>
            <li>&ldquo;Add a note that I had a phone screen on Tuesday, and record the interview.&rdquo;</li>
          </ul>
          <p className="text-xs text-muted">
            Lost a laptop or shared a token by mistake? Revoke it above and it stops working immediately. The address the assistant connects to is <code>{data.endpoint}</code>.
          </p>
        </Card>
      </div>
    </>
  );
}
