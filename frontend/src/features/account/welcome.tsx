"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { CheckField, FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { accountApi, type WelcomeData } from "./api";
import { toFormData } from "./logic";

export function WelcomePage() {
  const query = useQuery({ queryKey: ["account", "welcome"], queryFn: accountApi.welcome });
  if (query.isPending) return <Loading what="the first questions" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load the first questions.")} onRetry={() => query.refetch()} />;
  return <WelcomeForm data={query.data} />;
}

function WelcomeForm({ data }: { data: WelcomeData }) {
  const [values, setValues] = useState({
    target_roles: data.target_roles, home_country: data.home_country, open_remote: data.open_remote, other_places: data.other_places, profile_cv: data.profile_cv,
  });
  const [file, setFile] = useState<File | null>(null);
  const form = useSubmit();
  const skip = useSubmit();
  const save = form.handle(async () => {
    await accountApi.saveWelcome(file ? toFormData({ ...values }, file) : { ...values });
    notify("Lovely, that helps. We are searching for jobs that fit you now; they will appear here in a minute.");
    navigate("/"); // the search starts on the dashboard
  });
  const leave = skip.handle(async () => {
    await accountApi.skipWelcome();
    navigate("/");
  });
  const set = (key: keyof typeof values, value: string | boolean) => setValues((v) => ({ ...v, [key]: value }));

  return (
    <>
      <PageHeader title="Welcome to StillOpen" subtitle="Three quick questions so your first matches fit you. Everything can be changed later in your profile." />
      <form onSubmit={save} className="space-y-4">
        <Card>
          <TextAreaField
            label="What kind of work are you looking for?"
            hint="One role per line. It is fine to be rough, you can change it any time."
            rows={3}
            placeholder={"Senior Backend Engineer\nSolutions Architect"}
            value={values.target_roles}
            onChange={(e) => set("target_roles", e.target.value)}
            errors={form.fields.target_roles}
          />
          <TextField
            label="Where do you live?"
            hint="So we can tell you whether a job is open to someone there. A country name is enough."
            value={values.home_country}
            onChange={(e) => set("home_country", e.target.value)}
            errors={form.fields.home_country}
          />
          <CheckField
            label="I am happy to work remotely, from anywhere"
            hint="Untick if you only want work in a place you name below."
            checked={values.open_remote}
            onChange={(e) => set("open_remote", e.target.checked)}
          />
          <TextAreaField
            label="Anywhere else you would work in person?"
            hint="A country like Malaysia, or a region like Gulf or Europe, one per line. Leave it empty to look only where you live, plus remote."
            rows={2}
            placeholder={"Malaysia\nGulf"}
            value={values.other_places}
            onChange={(e) => set("other_places", e.target.value)}
            errors={form.fields.other_places}
          />
        </Card>
        <Card>
          <div className="mb-3">
            <label htmlFor="welcome-cv-file" className="mb-1 block text-sm font-medium">
              Your CV
            </label>
            <input id="welcome-cv-file" type="file" accept=".pdf,.txt,.md,.markdown" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
            <p className="mt-1 text-xs text-muted">PDF, .txt or .md. We read the text and keep that, not the file.</p>
            {form.fields.cv_file?.map((m) => (
              <p key={m} role="alert" className="mt-1 text-xs text-bad">
                {m}
              </p>
            ))}
          </div>
          <TextAreaField label="Or paste your CV here" rows={8} value={values.profile_cv} onChange={(e) => set("profile_cv", e.target.value)} errors={form.fields.profile_cv} />
        </Card>
        <FormError message={form.error || skip.error} />
        <p className="text-sm text-muted">Your answers stay private to you. Nothing is ever sent to an employer, and we never apply for you.</p>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={form.busy || skip.busy}>
            {form.busy ? "Saving…" : "Save and see my jobs"}
          </Button>
          <Button variant="ghost" onClick={leave} disabled={form.busy || skip.busy}>
            Skip for now
          </Button>
        </div>
      </form>
    </>
  );
}
