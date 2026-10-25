"use client";

import { useState } from "react";
import { Badge, Button, Card, Notice } from "@/components/ui";
import { CheckField, FormError, useSubmit } from "@/components/form";
import { notify } from "@/lib/toast";
import { accountApi, type ProfileData } from "./api";
import { addressLine, choicesOf, emailRows, emailsChanged, type EmailChoices, type EmailState } from "./email-choices";

const TONE: Record<EmailState, "good" | "muted" | "warn"> = { on: "good", off: "muted", owner_off: "warn" };
const WORD: Record<EmailState, string> = { on: "On", off: "Off", owner_off: "Not switched on by the site owner" };

/**
 * "Emails" on the profile: which emails the person gets, which the site owner has not switched on yet, and the address they go to.
 * Saved on its own (like the time zone), so it never needs the rest of the profile form to be valid.
 */
export function EmailsCard({ data, onSaved }: { data: ProfileData; onSaved: (next: ProfileData) => void }) {
  const form = useSubmit();
  const [draft, setDraft] = useState<EmailChoices>(choicesOf(data.profile));
  const rows = emailRows(data.profile, data.site, draft);
  const tick: Record<string, keyof EmailChoices | null> = { followups: "email_followups", interviews: "email_interviews", weekly: "email_weekly", alerts: null };
  const save = form.handle(async () => {
    const next = await accountApi.saveProfile({ ...draft });
    onSaved(next);
    setDraft(choicesOf(next.profile));
    notify("Your email choices are saved.");
  });
  const verified = data.account.email_verified;
  return (
    <Card id="emails" className="scroll-mt-20" aria-labelledby="emails-heading">
      <h2 id="emails-heading" className="font-semibold">
        Emails
      </h2>
      <p className="my-2 text-sm text-muted">Choose which emails you get. StillOpen never writes to an employer for you; these only go to you.</p>
      <div className="mb-3">
        <Notice tone={verified ? "info" : "error"}>{addressLine(data.account.email, verified)}</Notice>
      </div>
      <form onSubmit={save}>
        <ul className="space-y-1">
          {rows.map((row) => {
            const field = tick[row.key];
            return (
              <li key={row.key} className="border-b border-border pb-2 last:border-0">
                {field ? (
                  <CheckField label={row.label} hint={row.hint} checked={draft[field]} onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.checked }))} />
                ) : (
                  <div className="mb-1">
                    <p className="text-sm">{row.label}</p>
                    <p className="text-xs text-muted">{row.hint}</p>
                  </div>
                )}
                <p className="text-xs" data-testid={`email-state-${row.key}`}>
                  <Badge tone={TONE[row.state]}>{WORD[row.state]}</Badge> <span className="text-muted">{row.line}</span>
                </p>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-xs text-muted">Every email ends with a line telling you where to change these choices.</p>
        <FormError message={form.error} />
        <Button type="submit" className="mt-2" disabled={form.busy || !emailsChanged(data.profile, draft)}>
          {form.busy ? "Saving…" : "Save email choices"}
        </Button>
      </form>
    </Card>
  );
}
