"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, Notice, Button } from "@/components/ui";
import { FormError, TextField, useSubmit } from "@/components/form";
import { accountApi } from "./api";

/**
 * "Add a company's careers page": the address of a page that lists a company's openings. We read it once to check it works, then it is
 * searched with your other boards. Only the person's own list changes.
 */
export function CareerPageCard({ queryKey, limit }: { queryKey: readonly unknown[]; limit: number }) {
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [done, setDone] = useState("");
  const [info, setInfo] = useState("");
  const form = useSubmit();

  const add = form.handle(async () => {
    setDone("");
    setInfo("");
    const result = await accountApi.addCareerPage({ url, name });
    if (result.info) {
      setInfo(result.info);
      return;
    }
    setDone(result.message);
    setUrl("");
    setName("");
    await client.invalidateQueries({ queryKey: [...queryKey] });
  });

  return (
    <Card role="region" aria-labelledby="careerpage-title">
      <h2 id="careerpage-title" className="mb-1 font-semibold">
        Add a company&apos;s careers page
      </h2>
      <p className="mb-3 text-sm text-muted">
        Many companies list their openings on their own website, on no job board we read. Paste the address of the page that lists them and we will read it the way a search engine does.
      </p>
      <form onSubmit={add}>
        <TextField label="Address of the careers page" type="url" autoComplete="off" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} errors={form.fields.board_token} required />
        <TextField label="Company name (optional)" value={name} onChange={(e) => setName(e.target.value)} errors={form.fields.name} />
        <FormError message={form.error} />
        {info && !form.error && (
          <div className="mb-3">
            <Notice tone="info">{info}</Notice>
          </div>
        )}
        {done && !form.error && !info && (
          <div className="mb-3">
            <Notice tone="success">{done}</Notice>
          </div>
        )}
        <Button type="submit" disabled={form.busy}>
          {form.busy ? "Checking…" : "Check and add"}
        </Button>
      </form>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer">What happens, and what we will not do</summary>
        <ul className="mt-2 list-disc pl-5 text-muted">
          <li>We open the page you gave once to check it lists jobs, then again at your searches. We only look for the standard job information companies publish for Google.</li>
          <li>We say who we are (StillOpen) and keep to one request a second, so we never overload their site.</li>
          <li>We obey the site&apos;s robots.txt and skip any page that asks not to be indexed. If it says no, we stop and tell you.</li>
          <li>We only follow links to pages on the same site (at most 25 of them), never log in, and never run the page&apos;s scripts.</li>
          <li>Page must start with https:// and be a public website. The jobs are shown only to you. You can have up to {limit} boards and pages in all.</li>
        </ul>
        <p className="mt-2 text-muted">If we cannot find a list of openings, paste single job links into Add job instead.</p>
      </details>
    </Card>
  );
}
