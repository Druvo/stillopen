"use client";

import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "outline" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-brand-contrast hover:opacity-90",
  outline: "border border-border bg-surface hover:bg-surface-2",
  danger: "border border-bad text-bad hover:bg-surface-2",
  ghost: "text-muted hover:bg-surface-2 hover:text-fg",
};

export function buttonClass(variant: Variant = "primary", small = false) {
  return cn("inline-flex items-center justify-center gap-1 rounded-sm font-medium disabled:opacity-60", small ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm", VARIANTS[variant]);
}

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; small?: boolean }>(function Button(
  { variant = "primary", small, className, type = "button", ...props },
  ref,
) {
  return <button ref={ref} type={type} className={cn(buttonClass(variant, small), className)} {...props} />;
});

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-md border border-border bg-surface p-4 sm:p-5", className)} {...props} />;
}

export function Badge({ children, tone = "muted", className }: { children: ReactNode; tone?: "muted" | "good" | "warn" | "bad" | "brand"; className?: string }) {
  const tones = { muted: "text-muted", good: "text-good", warn: "text-warn", bad: "text-bad", brand: "text-brand" };
  return <span className={cn("inline-block rounded bg-surface-2 px-1.5 py-0.5 text-xs", tones[tone], className)}>{children}</span>;
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" | "success" }) {
  const tones = { info: "border-border", error: "border-bad", success: "border-good" };
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("rounded-md border bg-surface p-3 text-sm", tones[tone])}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-[2rem] font-light tracking-tight">{title}</h1>
        {subtitle && <div className="text-sm text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Progress({ value, label }: { value: number; label: string }) {
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} className="h-2 overflow-hidden rounded-full bg-surface-2">
      <div className="h-full bg-brand" style={{ width: `${value}%` }} />
    </div>
  );
}

export function Loading({ what = "this page" }: { what?: string }) {
  return <p className="text-muted">Loading {what}…</p>;
}

export function ErrorBox({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-border bg-surface p-4">
      <p className="font-medium">{message || "We could not load this."}</p>
      {onRetry && (
        <Button className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function SourceLinks({ sources }: { sources: { title: string; url: string; checked?: boolean | null }[] }) {
  return (
    <>
      {sources.map((s, i) => (
        <span key={s.url}>
          {i > 0 && " · "}
          <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand underline">
            {s.title}
          </a>
          {s.checked === false && <Badge tone="warn" className="ml-1">not checked</Badge>}
        </span>
      ))}
    </>
  );
}
