"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { pipelineApi, type CalendarLink } from "./api";

const KEY = ["pipeline", "calendar-link"] as const;

/** A private address a calendar app (Google, Apple, Outlook, Thunderbird) can subscribe to. Dates only, read-only. */
export function CalendarLinkCard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: pipelineApi.calendarLink });
  const [confirming, setConfirming] = useState(false);
  const save = (data: CalendarLink) => client.setQueryData(KEY, data);
  const make = useMutation({
    mutationFn: pipelineApi.makeCalendarLink,
    onSuccess: (data) => {
      save(data);
      setConfirming(false);
      notify(confirming ? "New link made. The old one no longer works." : "Calendar link made.");
    },
  });
  const stop = useMutation({
    mutationFn: pipelineApi.stopCalendarLink,
    onSuccess: (data) => {
      save(data);
      notify("Calendar link turned off.");
    },
  });
  const error = query.error || make.error || stop.error;
  const link = query.data;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link?.url ?? "");
      notify("Link copied.");
    } catch {
      notify("Select the link and copy it by hand."); // the field below is selectable
    }
  };
  return (
    <Card className="mt-4" aria-labelledby="calendar-link-title">
      <h2 id="calendar-link-title" className="mb-1 font-semibold">
        Show these dates in your calendar
      </h2>
      <p className="mb-3 text-sm text-muted">
        Add one link to Google Calendar, Apple Calendar or Outlook (look for “subscribe” or “add from web”) and your interviews, follow-up days and apply-by days appear there and stay up to date.
      </p>
      {!link ? (
        <p className="text-sm text-muted">{query.isPending ? "Loading…" : ""}</p>
      ) : link.enabled ? (
        <>
          <label className="mb-1 block text-sm font-medium" htmlFor="calendar-link-url">
            Your private link
          </label>
          <input
            id="calendar-link-url"
            readOnly
            value={link.url}
            onFocus={(e) => e.currentTarget.select()}
            className="w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-xs"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <Button small onClick={copy}>
              Copy link
            </Button>
            {confirming ? (
              <>
                <Button small variant="danger" disabled={make.isPending} onClick={() => make.mutate()}>
                  Yes, make a new link
                </Button>
                <Button small variant="ghost" onClick={() => setConfirming(false)}>
                  Keep the current one
                </Button>
              </>
            ) : (
              <Button small variant="outline" onClick={() => setConfirming(true)}>
                Make a new link
              </Button>
            )}
            <Button small variant="ghost" disabled={stop.isPending} onClick={() => stop.mutate()}>
              Turn off
            </Button>
          </div>
          {confirming && <p className="mt-2 text-sm text-muted">The old link stops working straight away, so you will need to subscribe again with the new one.</p>}
        </>
      ) : (
        <Button small disabled={make.isPending} onClick={() => make.mutate()}>
          {make.isPending ? "Making…" : "Make my calendar link"}
        </Button>
      )}
      <p className="mt-3 text-xs text-muted">
        Anyone who has this link can read these dates, so keep it to yourself. It shows only the day or time, the company and the role: never your notes, the job text, meeting links or contacts. If it leaks, make a new link.
      </p>
      {error && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {errorText(error)}
        </p>
      )}
    </Card>
  );
}
