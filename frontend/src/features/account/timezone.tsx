"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useState } from "react";
import { Button } from "@/components/ui";
import { FormError, useSubmit } from "@/components/form";
import { notify } from "@/lib/toast";
import { allZones, deviceZone, isZoneName } from "@/lib/timezone";
import { accountApi, type ProfileData } from "./api";

/**
 * "Time zone" in the Display card. Today's date, practice streaks, follow-ups and deadlines turn over at this zone's midnight. Empty means the
 * site's zone. Saved on its own (not with the big profile form), so changing it never needs the rest of the form to be valid.
 */
export function TimeZoneField({ data, onSaved }: { data: ProfileData; onSaved: (next: ProfileData) => void }) {
  const client = useQueryClient();
  const listId = useId();
  const inputId = useId();
  const form = useSubmit();
  const [value, setValue] = useState(data.profile.timezone);
  const [device, setDevice] = useState("");
  useEffect(() => setDevice(deviceZone()), []); // read after the first render so the build-time page and the browser agree
  const zones = useMemo(() => allZones(data.choices.timezones), [data.choices.timezones]);
  const site = data.site.timezone;
  const unknown = value !== "" && !isZoneName(value);

  const save = (zone: string) =>
    form.handle(async () => {
      const next = await accountApi.saveProfile({ timezone: zone.trim() });
      onSaved(next);
      setValue(next.profile.timezone);
      await client.invalidateQueries(); // the greeting, the dashboard's days and the stats all read the zone
      notify(next.profile.timezone ? `Time zone set to ${next.profile.timezone}.` : "Using the site's time zone.");
    });

  return (
    <form onSubmit={save(value)} className="mt-4 border-t border-border pt-3">
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
        Time zone
      </label>
      <p className="mb-2 text-sm text-muted">
        Your day starts at your midnight: what counts as today, your practice streak, follow-ups and &ldquo;due in 3 days&rdquo;. Leave it empty to use the site&apos;s ({site}).
      </p>
      <input
        id={inputId}
        list={listId}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={`${site} (the site's)`}
        autoComplete="off"
        spellCheck={false}
        aria-invalid={unknown || form.fields.timezone?.length ? true : undefined}
        aria-describedby={`${inputId}-hint`}
        className="w-full max-w-sm rounded-md border border-border bg-surface px-3 py-2 text-sm"
      />
      <datalist id={listId}>
        {zones.map((z) => (
          <option key={z} value={z} />
        ))}
      </datalist>
      <p id={`${inputId}-hint`} className="mt-1 text-xs text-muted">
        {unknown ? "That is not a time zone we know. Start typing a city, for example Asia/Dhaka or America/Los_Angeles, and pick from the list." : "Start typing to search, for example Dhaka or Los_Angeles."}
      </p>
      {form.fields.timezone?.map((m) => (
        <p key={m} role="alert" className="mt-1 text-sm text-bad">
          {m}
        </p>
      ))}
      <FormError message={form.fields.timezone?.length ? "" : form.error} />
      <div className="mt-2 flex flex-wrap gap-2">
        <Button type="submit" small disabled={form.busy || unknown || value === data.profile.timezone}>
          {form.busy ? "Saving…" : "Save time zone"}
        </Button>
        {device && (
          <Button
            type="button"
            variant="outline"
            small
            disabled={form.busy}
            onClick={() => {
              setValue(device);
              void save(device)();
            }}
          >
            Use this device&apos;s time zone ({device})
          </Button>
        )}
      </div>
    </form>
  );
}
