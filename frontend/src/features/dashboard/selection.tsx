"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import { ActionMenu, type MenuItem } from "@/components/menu";
import { Button } from "@/components/ui";
import type { StatusInfo } from "@/lib/types";
import { selectedText, statusLabel } from "./jobmgmt";

/**
 * The bar that appears while the person is choosing several jobs: how many, "select all in this tab", and what to do with them.
 * Everything is a real button or a keyboard-friendly menu; the count is announced as it changes.
 */
export function SelectionBar({
  count, total, allChecked, onToggleAll, statuses, canNotForMe, onNotForMe, onSetStatus, onArchive, onRemove, onCancel, busy,
}: {
  count: number;
  /** How many jobs the list holds (the chosen tab with its filters). */
  total: number;
  allChecked: boolean;
  onToggleAll: () => void;
  statuses: StatusInfo[];
  canNotForMe: boolean;
  onNotForMe: () => void;
  onSetStatus: (statusId: number) => void;
  onArchive: () => void;
  onRemove: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const items: MenuItem[] = statuses.map((s) => ({ key: String(s.id), label: statusLabel(s), onSelect: () => onSetStatus(s.id), disabled: busy }));
  const none = count === 0 || busy;
  return (
    <section aria-label="Actions for the chosen jobs" className="so-card sticky top-2 z-30 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-brand bg-surface p-3 shadow-theme-md">
      <label className="flex min-h-11 items-center gap-2 text-theme-sm sm:min-h-9">
        <input type="checkbox" checked={allChecked} onChange={onToggleAll} disabled={total === 0 || busy} />
        <span>Select all in this tab ({total})</span>
      </label>
      <p role="status" aria-live="polite" className="text-theme-sm font-medium">
        {selectedText(count)}
      </p>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {canNotForMe && (
          <Button variant="outline" onClick={onNotForMe} disabled={none} className="min-h-11 sm:min-h-9">
            Not for me
          </Button>
        )}
        {none ? (
          <Button variant="outline" disabled className="min-h-11 sm:min-h-9">
            Set status…
          </Button>
        ) : (
          <ActionMenu label="Set status for the chosen jobs" text="Set status…" variant="chevron" items={items} />
        )}
        <Button variant="outline" onClick={onArchive} disabled={none} className="min-h-11 sm:min-h-9">
          Archive
        </Button>
        <Button variant="danger" onClick={onRemove} disabled={none} className="min-h-11 sm:min-h-9">
          Remove…
        </Button>
        <Button variant="ghost" onClick={onCancel} className="min-h-11 sm:min-h-9">
          Cancel
        </Button>
      </div>
    </section>
  );
}

/**
 * A short message with Undo after a status change. It stays for a few seconds (the server allows five minutes, but a bar that never goes
 * away would be in the way). Remount it with a new `key` for each change.
 */
export function UndoBar({ text, onUndo, onDismiss, busy, seconds = 12 }: { text: string; onUndo: () => void; onDismiss: () => void; busy: boolean; seconds?: number }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, seconds * 1000);
    return () => window.clearTimeout(timer);
    // The bar is remounted for each change, so the timer starts once per message.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[95] flex justify-center px-4">
      <div role="status" className="pointer-events-auto flex max-w-xl items-center gap-3 rounded-xl border border-success-500 bg-white px-4 py-3 text-theme-sm shadow-theme-lg dark:bg-gray-900">
        <span className="flex-1">{text}</span>
        <Button variant="outline" small onClick={onUndo} disabled={busy}>
          {busy ? "Undoing…" : "Undo"}
        </Button>
        <button type="button" aria-label="Dismiss" onClick={onDismiss} className="text-gray-500 hover:text-gray-700">
          <X className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}
