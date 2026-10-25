"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { AI_SETTINGS_PATH } from "./logic";

/** Puts text on the clipboard (with an older fallback) and says so. Nothing is ever sent anywhere. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    try {
      const box = document.createElement("textarea");
      box.value = text;
      box.setAttribute("readonly", "");
      box.style.position = "fixed";
      box.style.opacity = "0";
      document.body.appendChild(box);
      box.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(box);
      if (!ok) throw new Error("copy refused");
    } catch {
      notify("We could not copy that. Select the text and copy it by hand.", "error");
      return false;
    }
  }
  notify("Copied.");
  return true;
}

export function CopyButton({ text, label = "Copy", small = true }: { text: string; label?: string; small?: boolean }) {
  return (
    <Button variant="outline" small={small} onClick={() => void copyText(text)}>
      {label}
    </Button>
  );
}

/** What replaces an AI button when the person has no AI set up: one plain line and the way to fix it. Never an error screen. */
export function NoKeyLine() {
  return (
    <p className="text-sm text-muted" data-testid="no-ai-key">
      Add your free Google AI Studio key in{" "}
      <Link to={AI_SETTINGS_PATH} className="text-brand underline">
        AI settings
      </Link>{" "}
      to use this.
    </p>
  );
}

export function AiNotice({ children }: { children?: ReactNode }) {
  return <p className="mt-2 text-xs text-muted">{children ?? "Written by AI, which can be wrong. Check it and put it in your own words."}</p>;
}

export function ProblemLine({ message }: { message: string }) {
  return message ? (
    <p role="alert" className="mt-2 text-sm text-bad">
      {message}
    </p>
  ) : null;
}
