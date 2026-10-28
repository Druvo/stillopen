"use client";

import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button, Card, PageHeader } from "@/components/ui";
import { useMe } from "@/lib/me";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";
import { CONTACT_LINE, FAQ, SECTIONS, type HelpLink } from "./content";
import { contactAddress } from "./logic";

/** One disclosure: a real heading inside the summary, so a screen reader can list and jump between sections. */
function Disclosure({ id, title, level = 2, open, onToggle, children }: { id: string; title: string; level?: 2 | 3; open: boolean; onToggle: (open: boolean) => void; children: ReactNode }) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <details id={id} open={open} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)} className="group border-b border-border last:border-0">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 py-2 [&::-webkit-details-marker]:hidden">
        <Heading className={cn("font-semibold", level === 2 ? "text-lg" : "text-base")}>{title}</Heading>
        <ChevronDown className="size-5 shrink-0 text-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="pb-4 pr-1 text-theme-sm leading-relaxed">{children}</div>
    </details>
  );
}

function Links({ links }: { links?: HelpLink[] }) {
  if (!links?.length) return null;
  return (
    <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
      {links.map((l) => (
        <Link key={l.to + l.label} to={l.to} className="link-target text-brand underline">
          {l.label}
        </Link>
      ))}
    </p>
  );
}

export function HelpPage() {
  const me = useMe();
  const address = contactAddress(me.data?.contact_email);
  const ids = [...SECTIONS.map((s) => s.id), "faq"];
  const [open, setOpen] = useState<Record<string, boolean>>({ [SECTIONS[0].id]: true });
  const [faqOpen, setFaqOpen] = useState<Record<number, boolean>>({});
  const set = (id: string) => (value: boolean) => setOpen((o) => ({ ...o, [id]: value }));
  const all = (value: boolean) => setOpen(Object.fromEntries(ids.map((id) => [id, value])));
  return (
    <>
      <PageHeader
        title="Help"
        subtitle="How StillOpen works, in plain words."
        actions={
          <>
            <Button variant="outline" small onClick={() => all(true)}>
              Open all
            </Button>
            <Button variant="outline" small onClick={() => all(false)}>
              Close all
            </Button>
          </>
        }
      />
      <Card className="max-w-3xl">
        {SECTIONS.map((s) => (
          <Disclosure key={s.id} id={s.id} title={s.title} open={!!open[s.id]} onToggle={set(s.id)}>
            {s.intro && <p className="mb-2">{s.intro}</p>}
            {s.steps && (
              <ol className="list-decimal space-y-1.5 pl-5">
                {s.steps.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ol>
            )}
            {s.points && (
              <ul className="list-disc space-y-1.5 pl-5">
                {s.points.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            )}
            <Links links={s.links} />
          </Disclosure>
        ))}
        <Disclosure id="faq" title="Questions people ask" open={!!open.faq} onToggle={set("faq")}>
          <div className="space-y-1">
            {FAQ.map((f, i) => (
              <Disclosure key={f.question} id={`faq-${i + 1}`} level={3} title={f.question} open={!!faqOpen[i]} onToggle={(value) => setFaqOpen((o) => ({ ...o, [i]: value }))}>
                <p>{f.answer}</p>
                <Links links={f.link ? [f.link] : undefined} />
              </Disclosure>
            ))}
          </div>
        </Disclosure>
      </Card>
      {me.data?.version && (
        <p className="mt-4 max-w-3xl text-theme-sm text-muted" data-testid="help-version">
          StillOpen version {me.data.version}
        </p>
      )}
      {address && (
        <p className="mt-4 max-w-3xl text-theme-sm" data-testid="help-contact">
          {CONTACT_LINE}{" "}
          <a href={`mailto:${address}`} className="text-brand underline">
            {address}
          </a>
          .
        </p>
      )}
    </>
  );
}
