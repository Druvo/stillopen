"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { applyHref } from "@/lib/utils";
import { jobsApi, type PostingRow } from "./api";
import { postingsQuery, readPostingsQuery, repostHint } from "./logic";

const CONTROL = "rounded-md border border-border bg-surface px-3 py-1.5 text-sm";

export function Postings() {
  const client = useQueryClient();
  const [state, setState] = useState(() => readPostingsQuery(typeof window === "undefined" ? "" : window.location.search));
  const [draft, setDraft] = useState(state.q);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const search = postingsQuery(state);

  useEffect(() => {
    window.history.replaceState(null, "", `${window.location.pathname}${search}`);
  }, [search]);

  const query = useQuery({ queryKey: ["postings", search], queryFn: () => jobsApi.postings(search), placeholderData: (previous) => previous });
  const add = useMutation({
    mutationFn: (row: PostingRow) => jobsApi.addPosting(row.id),
    onSuccess: async (made) => {
      setMessage({ tone: "success", text: made.created ? `Added ${made.company} - ${made.role}.` : "Already in your tracker." });
      await client.invalidateQueries({ queryKey: ["postings"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => setMessage({ tone: "error", text: errorText(e) }),
  });

  if (query.isPending) return <Loading what="the postings" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load the postings.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const filtered = Boolean(state.q || state.source);

  return (
    <>
      <PageHeader title="All postings" subtitle={`${data.total} posting${data.total === 1 ? "" : "s"}`} />
      <p className="mb-4 text-sm text-muted">
        Every posting any search has found, whether it matched your target roles or not. A posting is a fact about the job market, so everyone sees the same ones. Your tracker only adds the ones that match
        on their own; add any other here by hand.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setState((s) => ({ ...s, q: draft, page: 1 }));
        }}
        className="mb-3 flex flex-wrap items-center gap-2"
      >
        <label className="sr-only" htmlFor="postings-q">
          Search title or company
        </label>
        <input id="postings-q" type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search title or company" className={CONTROL} />
        <label className="sr-only" htmlFor="postings-source">
          Source
        </label>
        <select id="postings-source" value={state.source} onChange={(e) => setState((s) => ({ ...s, source: e.target.value, page: 1 }))} className={CONTROL}>
          <option value="">All sources</option>
          {data.sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.connector})
            </option>
          ))}
        </select>
        <Button type="submit">Filter</Button>
        {filtered && (
          <Button
            variant="ghost"
            onClick={() => {
              setDraft("");
              setState({ q: "", source: "", page: 1 });
            }}
          >
            Clear
          </Button>
        )}
      </form>
      {data.limit_message && <div className="mb-3"><Notice tone="error">{data.limit_message}</Notice></div>}
      <p role="status" aria-live="polite" className="min-h-5 text-sm text-muted">
        {message?.text}
      </p>

      {data.postings.length === 0 ? (
        <Card className="py-10 text-center">
          <h2 className="font-semibold">{filtered ? "Nothing matches that" : "No postings yet"}</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted">{filtered ? "Try a shorter word, or clear the filter." : "Press Search for jobs on your dashboard, and what it finds will be listed here."}</p>
          {!filtered && (
            <Link to="/" className={`${buttonClass("primary")} mt-4`}>
              Go to my dashboard
            </Link>
          )}
        </Card>
      ) : (
        <ul className="space-y-2">
          {data.postings.map((p) => (
            <li key={p.id}>
              <Card className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <h2 className="font-semibold">{p.title}</h2>
                  <p className="text-sm text-muted">
                    {p.company || "Company not named"} · {p.source.name} ({p.source.connector}){p.location ? ` · ${p.location}` : ""} · first seen {p.first_seen}, last seen {p.last_seen}
                  </p>
                  {applyHref(p.apply_address) && (
                    <p className="mt-1 text-sm">
                      Apply address:{" "}
                      <a href={applyHref(p.apply_address)} target="_blank" rel="noopener noreferrer" className="text-brand underline">
                        {p.apply_address}
                      </a>{" "}
                      <span className="text-xs text-muted">(the post publishes this; we never send anything for you)</span>
                    </p>
                  )}
                  {p.repost && (
                    <>
                      <span title={repostHint(p.repost)}>
                        <Badge tone="warn" className="mt-1">
                          Possible repost: seen as {p.repost.distinct_urls} postings on {p.repost.distinct_dates} days
                        </Badge>
                      </span>
                      <p className="mt-1 text-xs text-muted">{repostHint(p.repost)}</p>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noopener noreferrer" className={buttonClass("ghost", true)}>
                      Open
                    </a>
                  )}
                  {p.tracked ? (
                    p.job_id ? (
                      <Link to={`/jobs/${p.job_id}/edit`} className="inline-flex" aria-label={`Tracked: open ${p.title}`}>
                        <Badge tone="good">Tracked</Badge>
                      </Link>
                    ) : (
                      <Badge tone="good">Tracked</Badge>
                    )
                  ) : (
                    <Button small variant="outline" disabled={add.isPending} onClick={() => add.mutate(p)}>
                      Add to tracker
                    </Button>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {data.pages > 1 && (
        <nav aria-label="Pages" className="mt-4 flex items-center gap-3">
          <Button variant="outline" disabled={data.page <= 1} onClick={() => setState((s) => ({ ...s, page: data.page - 1 }))}>
            Previous
          </Button>
          <span className="text-sm text-muted">
            Page {data.page} of {data.pages}
          </span>
          <Button variant="outline" disabled={data.page >= data.pages} onClick={() => setState((s) => ({ ...s, page: data.page + 1 }))}>
            Next
          </Button>
        </nav>
      )}
    </>
  );
}
