"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { CheckField, FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";
import { accountApi, type Area, type AreaValues, type ProfileData, type ProfileValues } from "./api";
import { areaPayload, areaToValues, BLANK_AREA, canConfirmDelete, toFormData, toggleValue } from "./logic";

export const PROFILE_KEY = ["account", "profile"] as const;

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function ProfilePage() {
  const query = useQuery({ queryKey: PROFILE_KEY, queryFn: accountApi.profile });
  if (query.isPending) return <Loading what="your profile" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your profile.")} onRetry={() => query.refetch()} />;
  return <ProfileScreen data={query.data} />;
}

function ProfileScreen({ data }: { data: ProfileData }) {
  const client = useQueryClient();
  const [version, setVersion] = useState(0); // a new number re-seeds the form from what the server saved (for example the CV read from a file)
  const [saved, setSaved] = useState(false);
  const [current, setCurrent] = useState(data);
  const welcome = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("welcome");
  return (
    <>
      <PageHeader title="Your profile" subtitle="This is what your matches are based on. Only you can see it. Changes apply to your next fit check." />
      {welcome && (
        <div className="mb-3">
          <Notice>
            <strong>Welcome.</strong> Tell us the roles you want, where you would work, and add your CV. Then add a job and check how well it fits.
          </Notice>
        </div>
      )}
      <div className="space-y-4">
        <ProfileForm
          key={version}
          data={current}
          onSaved={(next) => {
            setCurrent(next);
            client.setQueryData(PROFILE_KEY, next);
            setSaved(true);
            setVersion((v) => v + 1);
          }}
          saved={saved}
          onEdit={() => setSaved(false)}
        />
        <AreasEditor data={current} />
        <Card>
          <h2 className="font-semibold">More about you</h2>
          <p className="my-2 text-sm text-muted">
            Projects, work history details, certificates and cover letters help the AI judge fit. You have {plural(current.account.counts.documents, "extra document")}.
          </p>
          <Link to="/knowledge" className={buttonClass("outline")}>
            Manage documents
          </Link>
        </Card>
        <AccountCard data={current} />
        <DataCard data={current} />
      </div>
    </>
  );
}

function ProfileForm({ data, onSaved, saved, onEdit }: { data: ProfileData; onSaved: (next: ProfileData) => void; saved: boolean; onEdit: () => void }) {
  const [values, setValues] = useState<ProfileValues>(data.profile);
  const [file, setFile] = useState<File | null>(null);
  const form = useSubmit();
  const set = <K extends keyof ProfileValues>(key: K, value: ProfileValues[K]) => {
    onEdit();
    setValues((v) => ({ ...v, [key]: value }));
  };
  const text = (key: keyof ProfileValues) => ({ value: values[key] as string, onChange: (e: { target: { value: string } }) => set(key, e.target.value as never), errors: form.fields[key] });
  const save = form.handle(async () => {
    const next = await accountApi.saveProfile(file ? toFormData({ ...values }, file) : { ...values });
    onSaved(next);
  });

  return (
    <form onSubmit={save} className="space-y-4">
      <Card>
        <h2 className="mb-3 font-semibold">What you are looking for</h2>
        <TextAreaField label="The roles you want" hint="One role per line, for example Senior Backend Engineer." rows={3} placeholder={"Senior Backend Engineer\nSolutions Architect"} {...text("target_roles")} />
        <TextField label="The country you live in" hint="A name like Bangladesh or a code like BD. Remote jobs limited to one country only fit you if it is this one." {...text("home_country")} />
        <fieldset className="mb-3">
          <legend className="mb-1 text-sm font-medium">Kinds of employment you want</legend>
          <div className="flex flex-wrap gap-x-4">
            {data.choices.employment_types.map((c) => (
              <CheckField key={c.value} label={c.label} checked={values.employment_types.includes(c.value)} onChange={() => set("employment_types", toggleValue(values.employment_types, c.value))} />
            ))}
          </div>
          <p className="text-xs text-muted">Leave all unticked for no preference.</p>
        </fieldset>
        <fieldset className="mb-3">
          <legend className="mb-1 text-sm font-medium">Seniority you want</legend>
          <div className="flex flex-wrap gap-x-4">
            {data.choices.seniority_levels.map((c) => (
              <CheckField key={c.value} label={c.label} checked={values.seniority_levels.includes(c.value)} onChange={() => set("seniority_levels", toggleValue(values.seniority_levels, c.value))} />
            ))}
          </div>
          <p className="text-xs text-muted">Leave all unticked for no preference.</p>
        </fieldset>
        <TextAreaField label="Industries you want" hint="One per line, or leave blank for any." rows={2} placeholder={"Fintech\nE-commerce"} {...text("industries")} />
        <TextAreaField label="Languages you can work in" hint="One per line." rows={2} placeholder={"English\nBangla"} {...text("languages")} />
        <TextField label="Notice period" hint="For example 30 days, or available now." {...text("notice_period")} />
        <TextField label="Your minimum pay" hint="With currency and period, for example 100,000 BDT/month." {...text("salary_floor")} />
        <TextAreaField label="Things you will not accept" hint="One per line." rows={2} {...text("deal_breakers")} />
        <TextAreaField label="Anything else the AI should know" rows={3} {...text("about")} />
      </Card>

      <Card>
        <h2 className="mb-2 font-semibold">Job alerts</h2>
        <CheckField
          label="Search for new jobs for me and email me what is found"
          hint={`Runs your saved search on a schedule and emails one short list of new matches. Off until you turn it on.${data.site.scan_emails_enabled ? "" : " The site owner has not switched scheduled emails on yet, so nothing is sent for now."}`}
          checked={values.scan_digest_enabled}
          onChange={(e) => set("scan_digest_enabled", e.target.checked)}
        />
        <CheckField
          label="Email me a weekly summary of how my search is going"
          hint={`Applications sent, interviews, offers and follow-ups from the last 7 days. Off until you turn it on.${data.site.weekly_digest_site_enabled ? "" : " The site owner has not switched the weekly digest on yet, so nothing is sent for now."}`}
          checked={values.weekly_digest_enabled}
          onChange={(e) => set("weekly_digest_enabled", e.target.checked)}
        />
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">Your CV</h2>
        <div className="mb-3">
          <label htmlFor="cv-file" className="mb-1 block text-sm font-medium">
            Upload your CV
          </label>
          <input id="cv-file" type="file" accept=".pdf,.txt,.md,.markdown" onChange={(e) => { onEdit(); setFile(e.target.files?.[0] ?? null); }} className="block w-full text-sm" />
          <p className="mt-1 text-xs text-muted">PDF, .txt or .md, up to 2 MB. The text is read into the box below; the file itself is not kept.</p>
          {form.fields.cv_file?.map((m) => (
            <p key={m} role="alert" className="mt-1 text-xs text-bad">
              {m}
            </p>
          ))}
        </div>
        <TextAreaField label="Your CV (text)" rows={14} {...text("profile_cv")} />
      </Card>

      <FormError message={form.error} />
      {saved && !form.error && <Notice tone="success">Saved. Your next matches will use this.</Notice>}
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : "Save profile"}
      </Button>
    </form>
  );
}

// --- search areas -------------------------------------------------------------------------------

/** `/profile#areas` (also from a link inside the app) scrolls to that card once it is on the screen. */
function useScrollToHash(id: string) {
  useEffect(() => {
    const go = () => {
      if (window.location.hash === `#${id}`) document.getElementById(id)?.scrollIntoView({ block: "start" });
    };
    go();
    window.addEventListener("hashchange", go);
    return () => window.removeEventListener("hashchange", go);
  }, [id]);
}

function AreasEditor({ data }: { data: ProfileData }) {
  const [areas, setAreas] = useState<Area[]>(data.areas);
  useScrollToHash("areas");
  const [drafts, setDrafts] = useState<number[]>([]); // keys of unsaved new rows
  const [next, setNext] = useState(1);
  return (
    <Card id="areas" className="scroll-mt-20">
      <h2 className="font-semibold">Where you would work</h2>
      <p className="my-2 text-sm text-muted">
        One row per place. Say which kinds of work you accept there and what you need from the employer. Jobs are checked against these rows; a job outside them is flagged, never hidden.
      </p>
      <p className="mb-3 text-xs text-muted">
        Examples: Bangladesh, city Dhaka: on-site, hybrid. Anywhere: remote. Malaysia: on-site, hybrid, only with visa sponsorship. Gulf: on-site, sponsorship and relocation support, minimum 8,000 USD per month. A place can be a country, a
        region (Gulf, Europe, Southeast Asia) or Anywhere.
      </p>
      {areas.length === 0 && drafts.length === 0 && <p className="mb-3 text-sm">You have not added a place yet. Add one so we can tell you which jobs are within reach.</p>}
      <div className="space-y-3">
        {areas.map((area) => (
          <AreaRow
            key={area.id}
            area={area}
            salaryPeriods={data.choices.salary_periods}
            onSaved={(saved) => setAreas((list) => list.map((a) => (a.id === saved.id ? saved : a)))}
            onRemoved={() => setAreas((list) => list.filter((a) => a.id !== area.id))}
          />
        ))}
        {drafts.map((key) => (
          <AreaRow
            key={`new-${key}`}
            area={null}
            salaryPeriods={data.choices.salary_periods}
            onSaved={(saved) => {
              setAreas((list) => [...list, saved]);
              setDrafts((list) => list.filter((k) => k !== key));
            }}
            onRemoved={() => setDrafts((list) => list.filter((k) => k !== key))}
          />
        ))}
      </div>
      <div className="mt-3">
        {areas.length + drafts.length >= data.max_areas ? (
          <p className="text-sm text-muted">You can have at most {data.max_areas} places.</p>
        ) : (
          <Button
            variant="outline"
            onClick={() => {
              setDrafts((list) => [...list, next]);
              setNext((n) => n + 1);
            }}
          >
            Add a place
          </Button>
        )}
      </div>
    </Card>
  );
}

function AreaRow({ area, salaryPeriods, onSaved, onRemoved }: { area: Area | null; salaryPeriods: { value: string; label: string }[]; onSaved: (area: Area) => void; onRemoved: () => void }) {
  const [values, setValues] = useState<AreaValues>(area ? areaToValues(area) : BLANK_AREA);
  const [note, setNote] = useState("");
  const [dirty, setDirty] = useState(area === null);
  const form = useSubmit();
  const set = <K extends keyof AreaValues>(key: K, value: AreaValues[K]) => {
    setDirty(true);
    setNote("");
    setValues((v) => ({ ...v, [key]: value }));
  };
  const save = form.handle(async () => {
    const payload = areaPayload(values);
    const result = area ? await accountApi.changeArea(area.id, payload) : await accountApi.addArea(payload);
    setDirty(false);
    setNote(result.warning ?? "Saved.");
    onSaved(result.area);
  });
  const remove = form.handle(async () => {
    if (area) {
      if (!window.confirm(`Remove ${area.place} from your places?`)) return;
      await accountApi.removeArea(area.id);
    }
    onRemoved();
  });
  const box = (key: "allow_remote" | "allow_hybrid" | "allow_onsite" | "needs_visa_sponsorship" | "needs_relocation_support", label: string) => (
    <CheckField label={label} checked={values[key]} onChange={(e) => set(key, e.target.checked)} />
  );

  return (
    <div className={cn("rounded-lg border p-3", form.error ? "border-bad" : "border-border")}>
      <div className="grid gap-x-3 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <TextField label="Place" value={values.place} onChange={(e) => set("place", e.target.value)} errors={form.fields.place} />
        </div>
        <TextField label="City (optional)" value={values.city} onChange={(e) => set("city", e.target.value)} errors={form.fields.city} />
      </div>
      <div className="flex flex-wrap gap-x-4">
        {box("allow_remote", "Remote")}
        {box("allow_hybrid", "Hybrid")}
        {box("allow_onsite", "On-site")}
        {box("needs_visa_sponsorship", "Only with visa sponsorship")}
        {box("needs_relocation_support", "Only with relocation support")}
      </div>
      <div className="grid gap-x-3 sm:grid-cols-3">
        <TextField label="Minimum pay" inputMode="numeric" value={values.min_salary} onChange={(e) => set("min_salary", e.target.value)} errors={form.fields.min_salary} />
        <TextField label="Currency" maxLength={3} placeholder="USD" value={values.salary_currency} onChange={(e) => set("salary_currency", e.target.value)} errors={form.fields.salary_currency} />
        <SelectField label="Per" value={values.salary_period} onChange={(e) => set("salary_period", e.target.value)}>
          {salaryPeriods.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </SelectField>
      </div>
      <FormError message={form.error} />
      {note && !form.error && <p className="mb-2 text-sm text-muted">{note}</p>}
      <div className="flex gap-2">
        <Button onClick={save} disabled={form.busy || !dirty}>
          {area ? "Save this place" : "Add this place"}
        </Button>
        <Button variant="danger" onClick={remove} disabled={form.busy}>
          {area ? "Remove" : "Cancel"}
        </Button>
      </div>
    </div>
  );
}

// --- account and data ---------------------------------------------------------------------------

function AccountCard({ data }: { data: ProfileData }) {
  const { account, site } = data;
  return (
    <Card>
      <h2 className="font-semibold">Your account</h2>
      <p className="my-2 text-sm">
        Signed in as <strong>{account.username}</strong>
        {account.email ? ` (${account.email})` : ""}
        {account.google ? ". Google sign-in is linked" : ""}.
      </p>
      <div className="flex flex-wrap gap-2">
        <a className={buttonClass("outline")} href={account.classic.email}>
          Change or add email
        </a>
        <a className={buttonClass("outline")} href={account.classic.password}>
          Change password
        </a>
        <a className={buttonClass("outline")} href={account.classic.two_step}>
          Two-step sign-in
        </a>
        <a className={buttonClass("outline")} href={account.classic.connections}>
          Connected accounts
        </a>
        <Link to="/profile/ai" className={buttonClass("outline")}>
          AI settings
        </Link>
        {site.assistant_enabled && (
          <Link to="/profile/assistant" className={buttonClass("outline")}>
            Connect an AI assistant
          </Link>
        )}
      </div>
      <p className="mt-3 text-sm text-muted">
        Stored about you: {plural(account.counts.jobs, "job")}, {plural(account.counts.cv_versions, "CV version")}, {plural(account.counts.documents, "document")}, {plural(account.counts.search_areas, "search area")}, and this profile. Everything is
        in the export below. See the{" "}
        <a className="underline" href={account.classic.privacy}>
          privacy policy
        </a>
        .
      </p>
    </Card>
  );
}

function DataCard({ data }: { data: ProfileData }) {
  const { account } = data;
  const [typed, setTyped] = useState("");
  const form = useSubmit();
  const remove = form.handle(async () => {
    if (!window.confirm("Delete your account and all of your data? This cannot be undone.")) return;
    await accountApi.deleteAccount(typed.trim());
    window.location.assign("/"); // the session is over: back to the public home page
  });
  return (
    <Card>
      <h2 className="font-semibold">Your data</h2>
      <p className="my-2 text-sm">Download everything stored about you, or delete your account and all of it.</p>
      <a className={buttonClass("outline")} href={account.classic.export}>
        Export my data (JSON)
      </a>
      {account.can_delete ? (
        <form onSubmit={remove} className="mt-4 max-w-sm">
          <TextField
            label={
              <>
                Delete my account. Type your username (<Badge>{account.username}</Badge>) to confirm
              </>
            }
            autoComplete="off"
            value={typed}
            onChange={(e) => {
              setTyped(e.target.value);
              form.clear();
            }}
            errors={form.fields.confirm}
          />
          <FormError message={form.error} />
          <Button type="submit" variant="danger" disabled={form.busy || !canConfirmDelete(typed, account.username)}>
            Delete account and data
          </Button>
        </form>
      ) : (
        <p className="mt-3 text-sm text-muted">Site admin accounts cannot be deleted here. Ask another admin.</p>
      )}
    </Card>
  );
}
