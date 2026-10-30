"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Button, Loading } from "@/components/ui";
import { errorText } from "@/lib/api";
import { jobsApi } from "./api";

/**
 * "Remove for good", behind a confirmation that says exactly what goes with the job (the sentence comes from the server, counted from the
 * person's own rows). The softer choice, "Not for me", is offered first because it keeps the job and can be undone. A native dialog: the page
 * behind it is inert, Tab stays inside, Escape closes it and focus goes back to where it was.
 */
export function RemoveDialog({
  ids, name, onClose, onSoft, onRemoved,
}: {
  ids: number[];
  /** "Backend Engineer at Acme" for one job; ignored for several. */
  name: string;
  onClose: () => void;
  /** Offered when given: keep the job, marked "Not for me". */
  onSoft?: () => void;
  onRemoved: (count: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const many = ids.length > 1;
  const preview = useQuery({
    queryKey: ["remove-preview", ids.join(",")],
    queryFn: () => (many ? jobsApi.bulkPreview(ids) : jobsApi.removePreview(ids[0])),
    staleTime: 0,
    gcTime: 0,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
    };
  }, []);

  async function remove() {
    setBusy(true);
    setError("");
    try {
      const done = many ? await jobsApi.bulkRemove(ids) : await jobsApi.removeJob(ids[0]);
      onRemoved(done.removed);
    } catch (e) {
      setError(errorText(e, "That did not work. Nothing was removed."));
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        if (busy) e.preventDefault();
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-md border border-border bg-surface p-5 text-theme-sm text-fg shadow-theme-lg backdrop:bg-black/40"
    >
      <h2 id={titleId} className="text-lg font-semibold">
        {many ? `Remove ${ids.length} jobs for good?` : `Remove ${name} for good?`}
      </h2>
      <div className="mt-3 space-y-2" aria-live="polite">
        {preview.isPending && <Loading what="what would be removed" />}
        {preview.isError && <p className="text-muted">We could not check what is attached to {many ? "these jobs" : "this job"}, but you can still remove {many ? "them" : "it"}.</p>}
        {preview.data && (
          <>
            <p>{preview.data.text}</p>
            <p className="text-muted">{preview.data.keeps}</p>
          </>
        )}
        <p className="font-medium">This cannot be undone.</p>
        {onSoft && (
          <p className="text-muted">
            Not sure? “Not for me” keeps {many ? "them" : "it"} on your list, out of the way, and you can bring {many ? "them" : "it"} back.
          </p>
        )}
        {error && (
          <p role="alert" className="text-bad">
            {error}
          </p>
        )}
      </div>
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={busy} autoFocus>
          Cancel
        </Button>
        {onSoft && (
          <Button variant="outline" onClick={onSoft} disabled={busy}>
            Mark as not for me instead
          </Button>
        )}
        <Button variant="danger" onClick={remove} disabled={busy}>
          {busy ? "Removing…" : "Remove for good"}
        </Button>
      </div>
    </dialog>
  );
}
