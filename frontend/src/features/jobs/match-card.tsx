"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { jobsApi, type MatchCardData, type MatchRow } from "./api";
import { matchMark } from "./match-logic";

export const matchKey = (jobId: number) => ["match-card", jobId] as const;

function AddFact({ jobId, row, onDone }: { jobId: number; row: MatchRow; onDone: (card: MatchCardData) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  if (!open) {
    return (
      <Button variant="outline" small onClick={() => setOpen(true)} aria-label={`Add to my profile: ${row.text}`}>
        Add to my profile
      </Button>
    );
  }
  const id = `fact-${jobId}-${row.id}`;
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!text.trim()) {
          setProblem("Write the fact in your own words first.");
          return;
        }
        setBusy(true);
        setProblem("");
        try {
          const done = await jobsApi.addFact(jobId, text);
          notify(done.message);
          onDone(done.card);
        } catch (e) {
          setProblem(errorText(e, "We could not save that. Please try again."));
        } finally {
          setBusy(false);
        }
      }}
    >
      <label htmlFor={id} className="block text-theme-xs text-muted">
        Only add something that is true. It is saved in your notes, under &quot;Facts I added from job matches&quot;, and you can delete it any time.
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        maxLength={300}
        placeholder="In your own words, for example: I have run this in production for two years."
        className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-theme-sm"
        aria-describedby={problem ? `${id}-problem` : undefined}
      />
      {problem && (
        <p id={`${id}-problem`} role="alert" className="text-theme-xs text-bad">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" small disabled={busy}>
          {busy ? "Saving…" : "Save to my notes"}
        </Button>
        <Button type="button" variant="ghost" small onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** How you match this job: what the posting asks for, each ask ticked only when the person's own material says it (with where), else a gap. */
export default function MatchCard({ jobId, heading = true }: { jobId: number; heading?: boolean }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: matchKey(jobId), queryFn: () => jobsApi.matchCard(jobId), staleTime: 60_000 });
  const [reading, setReading] = useState(false);
  const [problem, setProblem] = useState("");
  if (query.isPending) return <p className="text-theme-sm text-muted">Reading the posting…</p>;
  if (query.isError) return <p role="alert" className="text-theme-sm text-bad">{errorText(query.error, "We could not read this posting.")}</p>;
  const card = query.data;
  const set = (next: MatchCardData) => client.setQueryData(matchKey(jobId), next);

  const readWithAi = async () => {
    setReading(true);
    setProblem("");
    try {
      set(await jobsApi.matchCardAi(jobId));
    } catch (e) {
      setProblem(errorText(e, "That did not work. Please try again."));
    } finally {
      setReading(false);
    }
  };

  return (
    <section aria-label="How you match" className="text-theme-sm">
      {heading && <h3 className="font-semibold">How you match</h3>}
      <p className="mb-2 text-muted" role="status">
        {card.summary}
      </p>
      {card.empty === "no_material" && (
        <p className="mb-2 text-muted">
          <Link to="/profile" className="text-brand underline">
            Add your CV
          </Link>{" "}
          and these tick themselves.
        </p>
      )}
      {card.requirements.length > 0 && (
        <ul className="space-y-2">
          {card.requirements.map((row) => {
            const mark = matchMark(row.state);
            return (
              <li key={row.id} className="rounded-lg border border-border p-2">
                <p>
                  <span className={cn("mr-1.5 font-semibold", mark.tone)} aria-hidden>
                    {mark.icon}
                  </span>
                  <span className="sr-only">{mark.words}: </span>
                  {row.text}
                </p>
                {row.state === "covered" && row.source && (
                  <p className="mt-1 text-theme-xs text-muted">
                    <span className="font-medium text-good">{row.source.label}</span>
                    {row.snippet && <> · &ldquo;{row.snippet}&rdquo;</>}
                  </p>
                )}
                {row.state === "gap" && (
                  <div className="mt-1">
                    <p className="mb-1 text-theme-xs text-muted">{row.hint || "Nothing in your material says this yet."}</p>
                    <AddFact jobId={jobId} row={row} onDone={set} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {card.excerpt && <p className="mt-2 text-theme-xs text-muted">This is only the start of the posting, so some requirements may be missing.</p>}
      {card.can_ai && card.method === "keywords" && card.empty !== "no_description" && (
        <div className="mt-2">
          <Button variant="outline" small onClick={readWithAi} disabled={reading}>
            {reading ? "Reading…" : "Read it with my AI"}
          </Button>
          <span className="ml-2 text-theme-xs text-muted">Uses your own AI key. The list always comes from the posting&apos;s own words.</span>
        </div>
      )}
      {problem && (
        <p role="alert" className="mt-2 text-theme-xs text-bad">
          {problem}
        </p>
      )}
    </section>
  );
}
