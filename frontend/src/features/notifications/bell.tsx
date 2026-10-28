"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "@/lib/router";
import { announce } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { LIST_KEY, SUMMARY_KEY, noticeApi } from "./api";
import { announcement, badgeText, timeText, unreadText } from "./logic";

const POLL_MS = 60_000;

/** The bell in the header: an unread count (one tiny answer, polled once a minute while the tab is visible), and the latest notices. */
export function NotificationBell() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const byKeyboard = useRef(false);
  const seen = useRef<number | null>(null);
  const panelId = useId();

  const summary = useQuery({ queryKey: SUMMARY_KEY, queryFn: noticeApi.summary, refetchInterval: POLL_MS, refetchIntervalInBackground: false, staleTime: 15_000 });
  const unread = summary.data?.unread ?? 0;
  const list = useQuery({ queryKey: [...LIST_KEY, "latest"], queryFn: () => noticeApi.list(8), enabled: open });

  // Said once when the count goes up, never on every poll and never for the first reading.
  useEffect(() => {
    if (!summary.data) return;
    const say = announcement(seen.current, unread);
    seen.current = unread;
    if (say) announce(say);
  }, [summary.data, unread]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  useEffect(() => {
    if (open && byKeyboard.current && list.data) {
      panel.current?.querySelector<HTMLElement>("a, button")?.focus();
      byKeyboard.current = false;
    }
  }, [open, list.data]);

  const refresh = () => client.invalidateQueries({ queryKey: ["notifications"] });
  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) button.current?.focus();
  };
  const items = list.data?.items ?? [];
  const row = "block min-h-11 w-full rounded-lg px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-white/5";

  return (
    <div
      className="relative"
      ref={box}
      onKeyDown={(e) => {
        if (open && e.key === "Escape") {
          e.preventDefault();
          close(true);
        }
      }}
      onBlur={(e) => {
        const next = e.relatedTarget as Node | null;
        if (open && next && !box.current?.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={button}
        type="button"
        onClick={(e) => {
          byKeyboard.current = e.detail === 0;
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Notifications. ${unreadText(unread)}`}
        className="relative flex size-11 items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-white/5"
      >
        <Bell className="size-5" aria-hidden />
        {unread > 0 && (
          <span aria-hidden data-testid="bell-count" className="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full bg-brand-600 px-1 text-[11px] font-semibold leading-5 text-white">
            {badgeText(unread)}
          </span>
        )}
      </button>
      <div ref={panel} id={panelId} hidden={!open} role="region" aria-label="Latest notifications" className="absolute right-0 z-50 mt-3 w-80 max-w-[calc(100vw-1.5rem)] rounded-2xl border border-gray-200 bg-white p-3 shadow-theme-lg dark:border-gray-800 dark:bg-gray-900">
        {list.isPending ? (
          <p className="px-3 py-2 text-theme-sm text-muted">Loading...</p>
        ) : items.length === 0 ? (
          <p className="px-3 py-2 text-theme-sm text-muted">Nothing new. Notices about your searches, deadlines and follow-ups will show up here.</p>
        ) : (
          <ul className="max-h-96 space-y-0.5 overflow-y-auto">
            {items.map((n) => {
              const body = (
                <>
                  <span className={cn("block text-theme-sm", n.read ? "font-normal" : "font-semibold")}>
                    {!n.read && <span className="sr-only">Unread: </span>}
                    {n.title}
                  </span>
                  {n.text && <span className="block text-theme-xs text-muted">{n.text}</span>}
                  <span className="block text-theme-xs text-muted">{timeText(n.created_at)}</span>
                </>
              );
              return (
                <li key={n.id}>
                  {n.link ? (
                    <Link
                      to={n.link}
                      className={row}
                      onClick={() => {
                        setOpen(false);
                        void noticeApi.read(n.id).then(refresh);
                      }}
                    >
                      {body}
                    </Link>
                  ) : (
                    <button type="button" className={row} onClick={() => void noticeApi.read(n.id).then(refresh)}>
                      {body}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <div className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-800">
          <Link to="/notifications" onClick={() => setOpen(false)} className="flex min-h-11 items-center rounded-lg px-3 text-theme-sm font-medium text-brand hover:bg-gray-100 dark:hover:bg-white/5">
            See all notifications
          </Link>
        </div>
      </div>
    </div>
  );
}
