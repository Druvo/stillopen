"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Short messages that outlive a screen change ("Saved Acme - Backend Engineer. Next, press Check my fit."), the new app's version of
 * the classic pages' flash messages. Call `notify(...)` from anywhere (also right before `navigate`); the shell shows them.
 */
export type Toast = { id: number; text: string; tone: "success" | "error" | "info" };

const EVENT = "so-toast";
let counter = 0;

export function notify(text: string, tone: Toast["tone"] = "success") {
  window.dispatchEvent(new CustomEvent<Toast>(EVENT, { detail: { id: ++counter, text, tone } }));
}

export function Toasts() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    const onToast = (e: Event) => {
      const toast = (e as CustomEvent<Toast>).detail;
      setItems((list) => [...list.slice(-2), toast]);
      window.setTimeout(() => setItems((list) => list.filter((t) => t.id !== toast.id)), toast.tone === "error" ? 9000 : 6000);
    };
    window.addEventListener(EVENT, onToast);
    return () => window.removeEventListener(EVENT, onToast);
  }, []);
  if (items.length === 0) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4" role="region" aria-label="Messages">
      {items.map((t) => (
        <div
          key={t.id}
          role={t.tone === "error" ? "alert" : "status"}
          className={cn(
            "pointer-events-auto flex max-w-xl items-start gap-3 rounded-xl border bg-white px-4 py-3 text-theme-sm shadow-theme-lg dark:bg-gray-900",
            t.tone === "error" ? "border-error-500" : t.tone === "success" ? "border-success-500" : "border-gray-200 dark:border-gray-800",
          )}
        >
          <span className="flex-1">{t.text}</span>
          <button type="button" aria-label="Dismiss" onClick={() => setItems((list) => list.filter((x) => x.id !== t.id))} className="text-gray-500 hover:text-gray-700">
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
