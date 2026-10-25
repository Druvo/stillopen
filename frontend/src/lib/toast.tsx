"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Short messages that outlive a screen change ("Saved Acme - Backend Engineer. Next, press Check my fit."), the new app's version of
 * the classic pages' flash messages. Call `notify(...)` from anywhere (also right before `navigate`); the shell shows them.
 *
 * Screen readers: the three live regions below exist from the first paint and only their contents change, because a region that is
 * added together with its text is often not announced. Messages go inside them without a role of their own, so nothing is read twice.
 *   - polite, for success and info messages
 *   - alert, for errors
 *   - polite and invisible, for `announce(...)`: the name of a new screen, "2 problems to fix"
 */
export type Toast = { id: number; text: string; tone: "success" | "error" | "info" };

const EVENT = "so-toast";
const SAY = "so-announce";
let counter = 0;

export function notify(text: string, tone: Toast["tone"] = "success") {
  window.dispatchEvent(new CustomEvent<Toast>(EVENT, { detail: { id: ++counter, text, tone } }));
}

/** Says something to screen reader users without showing anything. */
export function announce(text: string) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent<string>(SAY, { detail: text }));
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex max-w-xl items-start gap-3 rounded-xl border bg-white px-4 py-3 text-theme-sm shadow-theme-lg dark:bg-gray-900",
        toast.tone === "error" ? "border-error-500" : toast.tone === "success" ? "border-success-500" : "border-gray-200 dark:border-gray-800",
      )}
    >
      <span className="flex-1">{toast.text}</span>
      <button type="button" aria-label={`Dismiss the message: ${toast.text}`} onClick={onDismiss} className="flex size-11 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:text-gray-700 sm:size-6">
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}

export function Toasts() {
  const [items, setItems] = useState<Toast[]>([]);
  const [said, setSaid] = useState({ text: "", n: 0 });
  useEffect(() => {
    const onToast = (e: Event) => {
      const toast = (e as CustomEvent<Toast>).detail;
      setItems((list) => [...list.slice(-2), toast]);
      window.setTimeout(() => setItems((list) => list.filter((t) => t.id !== toast.id)), toast.tone === "error" ? 9000 : 6000);
    };
    const onSay = (e: Event) => setSaid((s) => ({ text: (e as CustomEvent<string>).detail, n: s.n + 1 }));
    window.addEventListener(EVENT, onToast);
    window.addEventListener(SAY, onSay);
    return () => {
      window.removeEventListener(EVENT, onToast);
      window.removeEventListener(SAY, onSay);
    };
  }, []);
  const dismiss = (id: number) => setItems((list) => list.filter((x) => x.id !== id));
  const regionClass = "flex flex-col items-center gap-2";
  return (
    <>
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4" role="region" aria-label="Messages">
        <div aria-live="polite" aria-atomic="false" data-testid="toasts-polite" className={regionClass}>
          {items.filter((t) => t.tone !== "error").map((t) => (
            <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
          ))}
        </div>
        <div role="alert" aria-live="assertive" aria-atomic="false" data-testid="toasts-alert" className={regionClass}>
          {items.filter((t) => t.tone === "error").map((t) => (
            <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
          ))}
        </div>
      </div>
      {/* Alternating a no-break space makes the same words (two refused forms in a row) read again. */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" data-testid="announcer">
        {said.text}
        {said.n % 2 ? " " : ""}
      </div>
    </>
  );
}
