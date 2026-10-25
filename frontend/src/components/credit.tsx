/** "Jobs by Adzuna", linked to Adzuna: required by Adzuna's terms wherever one of its results is shown. Renders nothing for any other job. */
export type Credit = { label: string; url: string };

export function CreditLink({ credit, className }: { credit?: Credit | null; className?: string }) {
  if (!credit) return null;
  return (
    <a href={credit.url} target="_blank" rel="noopener noreferrer" className={className ?? "text-xs text-muted underline"}>
      {credit.label}
    </a>
  );
}
