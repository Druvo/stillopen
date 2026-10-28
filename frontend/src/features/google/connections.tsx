"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { CheckField } from "@/components/form";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { googleApi } from "./api";

const KEY = ["google", "status"] as const;

/** Profile > Connections: connect your own Google account for sending from Gmail, replies and Calendar. Off until the site's admin sets it up. */
export function ConnectionsPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: googleApi.status, staleTime: 0 });
  const message = query.data?.message;
  useEffect(() => {
    if (message) notify(message);
  }, [message]);
  const connect = useMutation({ mutationFn: googleApi.connect, onSuccess: (r) => window.location.assign(r.url) });
  const disconnect = useMutation({
    mutationFn: googleApi.disconnect,
    onSuccess: (s) => {
      client.setQueryData(KEY, s);
      notify("Disconnected. Google no longer lets StillOpen in, and the saved permissions are deleted.");
    },
  });
  const sync = useMutation({
    mutationFn: (on: boolean) => googleApi.setCalendarSync(on),
    onSuccess: (s) => client.setQueryData(KEY, s),
  });
  if (query.isPending) return <Loading what="your connections" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load this page.")} onRetry={() => query.refetch()} />;
  const s = query.data;
  const error = connect.error || disconnect.error || sync.error;
  return (
    <>
      <PageHeader
        title="Connections"
        subtitle="Optional. Connect your own Google account so StillOpen can help with the email and calendar side of a job search."
        actions={
          <Link to="/profile" className={buttonClass("ghost")}>
            ← Profile
          </Link>
        }
      />
      <Card className="mb-4">
        <h2 className="mb-1 text-lg font-semibold">
          Google {s.connected && <Badge tone="good">Connected</Badge>}
        </h2>
        {!s.available ? (
          <Notice>Not set up on this site. The site&apos;s admin can switch it on in Site configuration, under Google connection.</Notice>
        ) : (
          <>
            {s.connected && (
              <p className="mb-2 text-sm">
                Connected as <strong>{s.email || "your Google account"}</strong>.
              </p>
            )}
            {s.problem && (
              <p role="alert" className="mb-2 text-sm text-bad">
                {s.problem}
              </p>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="font-semibold">What it can do</h3>
                <ul className="ml-5 list-disc text-sm">
                  <li>Send an application from your own Gmail, but only when you press Send on a message you have seen in full.</li>
                  <li>Show the replies in that one conversation next to the job, and help you draft an answer you edit yourself.</li>
                  <li>Look at when you are free, to suggest three interview times you can paste into a reply.</li>
                  <li>Keep your Google Calendar in step with your interviews, if you switch that on below.</li>
                </ul>
              </div>
              <div>
                <h3 className="font-semibold">What it never does</h3>
                <ul className="ml-5 list-disc text-sm">
                  <li>It never sends anything by itself, on a schedule, or for an AI assistant.</li>
                  <li>It never reads the rest of your mail, only the conversation of a job you applied to from here.</li>
                  <li>It never keeps whole emails: only who wrote, when, and a short snippet.</li>
                  <li>It never touches calendar events it did not create.</li>
                </ul>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {s.connected ? (
                <Button
                  variant="danger"
                  disabled={disconnect.isPending}
                  onClick={() => {
                    if (window.confirm("Disconnect your Google account? StillOpen will lose its permission and forget it.")) disconnect.mutate();
                  }}
                >
                  {disconnect.isPending ? "Disconnecting…" : "Disconnect Google"}
                </Button>
              ) : (
                <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
                  {connect.isPending ? "Opening Google…" : "Connect my Google account"}
                </Button>
              )}
            </div>
            {s.connected && (
              <div className="mt-4 border-t border-border pt-3">
                <CheckField
                  label="Keep my Google Calendar in step with my interviews"
                  hint="Adds, moves and removes the events StillOpen made. A time you move in Google comes back here."
                  checked={s.calendar_sync}
                  disabled={sync.isPending}
                  onChange={(e) => sync.mutate(e.target.checked)}
                />
              </div>
            )}
          </>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm text-bad">
            {errorText(error)}
          </p>
        )}
      </Card>
    </>
  );
}
