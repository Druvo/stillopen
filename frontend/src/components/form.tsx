"use client";

import { useId, useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ApiError, errorText } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Notice } from "./ui";

const CONTROL = "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm";

/** A labelled control with its hint and the server's messages for it. `errors` is `fields[name]` from a refused form. */
export function Field({ label, hint, errors, children, htmlFor }: { label: ReactNode; hint?: ReactNode; errors?: string[]; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="mb-3">
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {errors?.map((message) => (
        <p key={message} role="alert" className="mt-1 text-xs text-bad">
          {message}
        </p>
      ))}
    </div>
  );
}

type Common = { label: ReactNode; hint?: ReactNode; errors?: string[] };

export function TextField({ label, hint, errors, className, ...props }: Common & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Field label={label} hint={hint} errors={errors} htmlFor={id}>
      <input id={id} className={cn(CONTROL, className)} aria-invalid={errors?.length ? true : undefined} {...props} />
    </Field>
  );
}

export function TextAreaField({ label, hint, errors, className, ...props }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Field label={label} hint={hint} errors={errors} htmlFor={id}>
      <textarea id={id} className={cn(CONTROL, className)} aria-invalid={errors?.length ? true : undefined} {...props} />
    </Field>
  );
}

export function SelectField({ label, hint, errors, className, children, ...props }: Common & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Field label={label} hint={hint} errors={errors} htmlFor={id}>
      <select id={id} className={cn(CONTROL, className)} aria-invalid={errors?.length ? true : undefined} {...props}>
        {children}
      </select>
    </Field>
  );
}

export function CheckField({ label, hint, errors, ...props }: Common & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const id = useId();
  return (
    <div className="mb-3">
      <label htmlFor={id} className="flex items-start gap-2 text-sm">
        <input id={id} type="checkbox" className="mt-0.5" {...props} />
        <span>{label}</span>
      </label>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {errors?.map((message) => (
        <p key={message} role="alert" className="mt-1 text-xs text-bad">
          {message}
        </p>
      ))}
    </div>
  );
}

/** A few choices of which exactly one applies, as radio buttons (better than a dropdown for two or three options). */
export function RadioGroup<T extends string>({ legend, hint, name, value, options, onChange }: { legend: ReactNode; hint?: ReactNode; name: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <fieldset className="mb-4">
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <label key={o.value} className={cn("flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm sm:min-h-9", o.value === value ? "border-brand bg-brand-soft font-medium" : "border-border")}>
            <input type="radio" name={name} value={o.value} checked={o.value === value} onChange={() => onChange(o.value)} />
            {o.label}
          </label>
        ))}
      </div>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </fieldset>
  );
}

/**
 * Holds the busy flag, the overall error and the per-field messages of a form that posts to the API.
 *
 *   const form = useSubmit();
 *   <form onSubmit={form.handle(async () => { await request("POST", "/x", values); navigate("/done"); })}>
 *     <TextField errors={form.fields.company} … /> <FormError message={form.error} /> <Button disabled={form.busy}>Save</Button>
 */
export function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const handle = (action: () => Promise<unknown>) => async (event?: { preventDefault: () => void }) => {
    event?.preventDefault();
    setBusy(true);
    setError("");
    setFields({});
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError) setFields(e.fields);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, fields, handle, clear: () => { setError(""); setFields({}); } };
}

export function FormError({ message }: { message: string }) {
  return message ? <Notice tone="error">{message}</Notice> : null;
}
