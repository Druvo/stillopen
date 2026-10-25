"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { FormError, useSubmit } from "@/components/form";
import { accountApi } from "@/features/account/api";
import { useMe } from "@/lib/me";
import { deviceZone, effectiveZone, shouldSuggestZone } from "@/lib/timezone";
import { notify } from "@/lib/toast";
import { usePreferences } from "@/lib/use-preferences";

/**
 * A gentle, one-time suggestion: this device is in a different time zone from the one StillOpen uses for the person's days. "Keep it" is
 * remembered on the account (`tz_prompt_dismissed`), so it is not asked again on any device. Nothing changes unless they press the button.
 */
export function TimezonePrompt() {
  const me = useMe();
  const client = useQueryClient();
  const { prefs, update } = usePreferences();
  const form = useSubmit();
  const [device, setDevice] = useState("");
  useEffect(() => setDevice(deviceZone()), []); // after the first render, so the build-time page and the browser agree
  const saved = me.data?.timezone ?? "";
  const site = me.data?.site_timezone ?? "";
  if (!me.data || !shouldSuggestZone({ device, saved, site, dismissed: prefs.tz_prompt_dismissed })) return null;

  const use = form.handle(async () => {
    await accountApi.saveProfile({ timezone: device });
    update({ tz_prompt_dismissed: true });
    await client.invalidateQueries();
    notify(`Time zone set to ${device}.`);
  });

  return (
    <section aria-labelledby="tz-prompt-h" className="rounded-2xl border border-border bg-surface p-4">
      <h2 id="tz-prompt-h" className="font-semibold">
        Is this the right time zone for you?
      </h2>
      <p className="mt-1 text-theme-sm">
        This device says {device}, but your days (today&apos;s date, follow-ups, deadlines, your practice streak) follow {effectiveZone(saved, site)}. Switch if you want them to follow where you are.
      </p>
      <FormError message={form.error} />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={use} disabled={form.busy}>
          {form.busy ? "Saving…" : `Use ${device}`}
        </Button>
        <Button variant="outline" onClick={() => update({ tz_prompt_dismissed: true })} disabled={form.busy}>
          Keep {effectiveZone(saved, site)}
        </Button>
      </div>
    </section>
  );
}
