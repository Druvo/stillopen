"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { googleApi } from "./api";

/** On the Interviews screen when Google Calendar sync is on: pulls changes made in Google (short server cache on open) and a "Sync now" button. */
export function CalendarSync({ sync, connected }: { sync: boolean; connected: boolean }) {
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!sync) return;
    googleApi
      .syncCalendar(false)
      .then((r) => {
        setNote(r.note);
        if (r.changed) {
          notify(`${r.changed} interview${r.changed === 1 ? "" : "s"} changed in Google Calendar.`);
          client.invalidateQueries({ queryKey: ["pipeline", "interviews"] });
        }
      })
      .catch((e) => setNote(errorText(e)));
  }, [sync, client]);
  if (!connected) return null;
  if (!sync) return <p className="mb-3 text-sm text-muted">Want these on your Google Calendar too? Switch it on under Profile &gt; Connections.</p>;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        small
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await googleApi.syncCalendar(true);
            setNote(r.note);
            notify(r.changed ? `${r.changed} changed in Google Calendar.` : "Your calendar is in step.");
            await client.invalidateQueries({ queryKey: ["pipeline", "interviews"] });
          } catch (e) {
            setNote(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Syncing…" : "Sync now with Google Calendar"}
      </Button>
      {note && <Notice tone="error">{note}</Notice>}
    </div>
  );
}
