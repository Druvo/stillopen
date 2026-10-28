"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { announce, notify } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { LIST_KEY, SETTINGS_KEY, noticeApi } from "./api";
import { groupByDay, timeText, unreadText } from "./logic";

function Kinds() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: SETTINGS_KEY, queryFn: noticeApi.settings });
  const save = useMutation({
    mutationFn: (muted: string[]) => noticeApi.saveSettings(muted),
    onSuccess: (data) => {
      client.setQueryData(SETTINGS_KEY, data);
      notify("Saved. You will only get the notices that are ticked.");
    },
    onError: (e) => notify(errorText(e), "error"),
  });
  if (!query.data) return null;
  const kinds = query.data.kinds;
  return (
    <Card>
      <fieldset>
        <legend className="font-semibold">Which notices do you want?</legend>
        <p className="mt-1 text-theme-sm text-muted">Untick one to stop getting that kind. Notices you already have stay until you clear them.</p>
        <ul className="mt-2">
          {kinds.map((k) => (
            <li key={k.key}>
              <label className="flex min-h-11 items-center gap-3 text-theme-sm">
                <input
                  type="checkbox"
                  checked={k.on}
                  disabled={save.isPending}
                  onChange={(e) => save.mutate(kinds.filter((x) => (x.key === k.key ? !e.target.checked : !x.on)).map((x) => x.key))}
                  className="size-5"
                />
                {k.label}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
    </Card>
  );
}

export function NotificationsPage() {
  const client = useQueryClient();
  const [now] = useState(() => new Date());
  const query = useQuery({ queryKey: [...LIST_KEY, "all"], queryFn: () => noticeApi.list(200) });
  const refresh = () => client.invalidateQueries({ queryKey: ["notifications"] });
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: refresh,
    onError: (e) => notify(errorText(e), "error"),
  });
  if (query.isPending) return <Loading what="your notifications" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your notifications.")} onRetry={() => query.refetch()} />;
  const { items, unread } = query.data;
  const groups = groupByDay(items, now);
  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={unreadText(unread)}
        actions={
          items.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" disabled={unread === 0 || act.isPending} onClick={() => act.mutate(() => noticeApi.readAll().then(() => announce("All marked as read")))}>
                Mark all as read
              </Button>
              <Button variant="outline" disabled={act.isPending} onClick={() => act.mutate(() => noticeApi.clearAll().then(() => announce("All cleared")))}>
                Clear all
              </Button>
            </div>
          )
        }
      />
      <div className="space-y-6">
        {items.length === 0 ? (
          <Card>
            <p className="text-theme-sm">You have no notifications. When a search finds new jobs, a deadline gets close or a follow-up is due, it will show here. Start a search from your dashboard.</p>
            <Link to="/" className="link-target mt-2 inline-block text-brand underline">
              Go to your dashboard
            </Link>
          </Card>
        ) : (
          groups.map((g) => (
            <section key={g.label} aria-labelledby={`day-${g.label.replace(/\W+/g, "-")}`}>
              <h2 id={`day-${g.label.replace(/\W+/g, "-")}`} className="mb-2 text-theme-sm font-semibold text-muted">
                {g.label}
              </h2>
              <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
                {g.items.map((n) => (
                  <li key={n.id} className="flex items-start gap-3 p-3">
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-theme-sm", n.read ? "font-normal" : "font-semibold")}>
                        {!n.read && <span className="sr-only">Unread: </span>}
                        {n.link ? (
                          <Link to={n.link} className="link-target text-brand underline" onClick={() => void noticeApi.read(n.id).then(refresh)}>
                            {n.title}
                          </Link>
                        ) : (
                          n.title
                        )}
                      </p>
                      {n.text && <p className="text-theme-xs text-muted">{n.text}</p>}
                      <p className="text-theme-xs text-muted">{timeText(n.created_at)}</p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {!n.read && (
                        <Button small variant="outline" aria-label={`Mark as read: ${n.title}`} disabled={act.isPending} onClick={() => act.mutate(() => noticeApi.read(n.id))}>
                          Mark read
                        </Button>
                      )}
                      <Button small variant="outline" aria-label={`Clear: ${n.title}`} disabled={act.isPending} onClick={() => act.mutate(() => noticeApi.clearOne(n.id))}>
                        Clear
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
        <Kinds />
      </div>
    </>
  );
}
