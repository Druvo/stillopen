"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef } from "react";
import { Button, buttonClass } from "@/components/ui";
import { csrfToken } from "@/lib/api";
import { cvApi } from "./api";
import type { BuilderAnswers } from "./quality";

/** Built-in looks -- labels kept in sync by hand with tracker/services/cvexport.py TEMPLATES. */
export const CV_TEMPLATES: { value: string; label: string }[] = [
  { value: "classic", label: "Classic" },
  { value: "modern", label: "Modern" },
  { value: "compact", label: "Compact" },
  { value: "serif", label: "Serif" },
  { value: "forest", label: "Forest" },
  { value: "slate", label: "Slate" },
];

export type PreviewSource = { kind: "saved"; id: number } | { kind: "answers"; answers: BuilderAnswers };

/**
 * The CV as it will print, in a dialog. The page comes from the server (the same template as Print / save as PDF) and is shown in a frame with
 * no permissions at all: no scripts, no access to this site. The page carries its own policy that allows nothing but its inline style.
 * Choosing another look loads it again. Closing puts the focus back where it was.
 */
export function PreviewDialog({ source, template, onTemplate, onClose }: { source: PreviewSource; template: string; onTemplate: (value: string) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const titleId = useId();
  const frame = "cv-preview-frame";

  useEffect(() => {
    const el = dialog.current;
    const opener = document.activeElement as HTMLElement | null;
    if (el) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
    return () => {
      if (el?.open && typeof el.close === "function") el.close();
      opener?.focus?.();
    };
  }, []);

  const answers = source.kind === "answers" ? JSON.stringify(source.answers) : "";
  useEffect(() => {
    if (source.kind === "answers") form.current?.submit(); // a form post into the frame, so nothing personal is ever in an address
  }, [source.kind, template, answers]);

  const src = source.kind === "saved" ? `/cv/${source.id}/preview/?template=${encodeURIComponent(template)}` : undefined;

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto h-[min(46rem,calc(100vh-2rem))] w-[min(52rem,calc(100vw-2rem))] rounded-2xl border border-border bg-surface p-4 text-theme-sm text-fg shadow-theme-lg backdrop:bg-black/40"
    >
      <div className="flex h-full flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={titleId} className="mr-auto text-lg font-semibold">CV preview</h2>
          <label htmlFor="preview-look" className="text-sm">Look</label>
          <select id="preview-look" value={template} onChange={(e) => onTemplate(e.target.value)} className="rounded-lg border border-border bg-surface px-2 py-1 text-theme-xs">
            {CV_TEMPLATES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <Button variant="outline" onClick={onClose} autoFocus>Close</Button>
        </div>
        <p className="text-xs text-muted">This is the page that Print / save as PDF produces for this look. Nothing is saved by looking.</p>
        {source.kind === "answers" && (
          <form ref={form} method="post" action={`/cv/builder/preview/?template=${encodeURIComponent(template)}`} target={frame} className="hidden">
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken()} />
            <input type="hidden" name="answers" value={answers} readOnly />
          </form>
        )}
        <iframe name={frame} title="Preview of your CV" sandbox="" src={src} referrerPolicy="no-referrer" className="min-h-0 w-full flex-1 rounded-lg border border-border bg-white" />
      </div>
    </dialog>
  );
}

/** One button for a job's approved CV and cover letter together (DOCX, plain text and Markdown in a zip), or the plain reason it is not ready. */
export function DownloadAll({ jobId }: { jobId: number }) {
  const info = useQuery({ queryKey: ["cv", "documents", jobId], queryFn: () => cvApi.documents(jobId), staleTime: 0 });
  if (!info.data) return null;
  if (!info.data.ready || !info.data.url) return <span className="text-sm text-muted">{info.data.reason}</span>;
  return (
    <a className={buttonClass("outline")} href={info.data.url}>
      {info.data.has_cv && info.data.has_cover ? "Download CV and cover letter (zip)" : info.data.has_cv ? "Download CV (zip)" : "Download cover letter (zip)"}
    </a>
  );
}
