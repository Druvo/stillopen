"use client";

import { useQuery } from "@tanstack/react-query";
import { buttonClass, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { YourNumbers } from "@/features/stats/numbers";
import { pipelineApi } from "./api";

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Card>
      <p className="text-sm text-muted">{label}</p>
      <p className="text-3xl font-semibold">{value}</p>
      {note && <p className="text-sm text-muted">{note}</p>}
    </Card>
  );
}

export function Insights() {
  const query = useQuery({ queryKey: ["pipeline", "insights"], queryFn: pipelineApi.insights });
  if (query.isPending) return <Loading what="your numbers" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your numbers.")} onRetry={() => query.refetch()} />;
  const f = query.data;
  return (
    <>
      <PageHeader title="How your search is going" />
      <p className="mb-4 text-sm text-muted">Plain counts from your own tracker. They describe what happened, they do not predict anything, and small numbers say little.</p>
      {f.applied === 0 ? (
        <Card className="py-10 text-center">
          <p className="mx-auto max-w-md text-sm text-muted">
            Nothing to show yet. Once you record an application, this page shows how far your applications get and which channels lead to interviews.
          </p>
          <Link to="/" className={`${buttonClass("primary")} mt-4`}>
            Go to my dashboard
          </Link>
        </Card>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Tracked" value={f.tracked} />
            <Stat label="Applied" value={f.applied} />
            <Stat label="Reached an interview" value={f.interviewed} note={f.interview_rate !== null ? `${f.interview_rate}% of applied` : undefined} />
            <Stat label="Got an offer" value={f.offered} note={f.offer_rate !== null ? `${f.offer_rate}% of applied` : undefined} />
          </div>
          {f.median_days_to_interview !== null && (
            <p className="mb-2">
              Typically <strong>{f.median_days_to_interview} {f.median_days_to_interview === 1 ? "day" : "days"}</strong> from applying to your first interview.
            </p>
          )}
          {f.referred_applied > 0 && (
            <p className="mb-2">
              You were referred for <strong>{f.referred_applied}</strong> of the jobs you applied to; <strong>{f.referred_interviewed}</strong> of those reached an interview.
            </p>
          )}
          <h2 className="mb-2 mt-4 font-semibold">Where you applied</h2>
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted">
                  <th className="p-3 font-medium">Channel</th>
                  <th className="p-3 text-right font-medium">Applied</th>
                  <th className="p-3 text-right font-medium">Interviews</th>
                  <th className="p-3 text-right font-medium">Offers</th>
                </tr>
              </thead>
              <tbody>
                {f.channels.map((r) => (
                  <tr key={r.label} className="border-b border-border last:border-0">
                    <td className="p-3">{r.label}</td>
                    <td className="p-3 text-right">{r.applied}</td>
                    <td className="p-3 text-right">{r.interviews}</td>
                    <td className="p-3 text-right">{r.offers}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <p className="mt-2 text-sm text-muted">
            Interviews and offers count once you add them on the <Link to="/interviews" className="text-brand underline">Interviews</Link> and{" "}
            <Link to="/offers" className="text-brand underline">Offers</Link> pages.
          </p>
        </>
      )}
      <YourNumbers />
    </>
  );
}
