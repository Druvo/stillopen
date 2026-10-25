"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Button, Card, Notice, PageHeader, Progress } from "@/components/ui";
import { CheckField, FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cvApi } from "./api";
import { DRAFT_KEY, emptyAnswers, emptyRole, MAX_ROLES, parseDraft, STEPS, stepProgress, toApiAnswers, validateStep, type BuilderAnswers } from "./quality";

// The answers live in this tab's sessionStorage until the CV is built, never on the server. Storage can be blocked, so every use is guarded.
function readDraft() {
  try {
    return parseDraft(window.sessionStorage.getItem(DRAFT_KEY));
  } catch {
    return null;
  }
}
function writeDraft(step: number, answers: BuilderAnswers) {
  try {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ step, answers }));
  } catch {
    /* the wizard still works without it */
  }
}
function clearDraft() {
  try {
    window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* nothing to clear */
  }
}

function set<T>(list: T[], index: number, patch: Partial<T>): T[] {
  return list.map((item, i) => (i === index ? { ...item, ...patch } : item));
}

export function CvBuilder() {
  const client = useQueryClient();
  const [step, setStep] = useState(0);
  const [a, setA] = useState<BuilderAnswers>(emptyAnswers);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [polish, setPolish] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const form = useSubmit();
  const choices = useQuery({ queryKey: ["cv", "job-choices"], queryFn: cvApi.jobChoices, staleTime: 60_000 });
  const existing = useQuery({ queryKey: ["cv", "list"], queryFn: cvApi.list });

  useEffect(() => {
    const draft = readDraft();
    if (draft) {
      setStep(draft.step);
      setA(draft.answers);
    }
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (loaded) writeDraft(step, a);
  }, [loaded, step, a]);
  useEffect(() => {
    if (loaded) heading.current?.focus();
  }, [step, loaded]);

  const progress = stepProgress(step);
  const last = step === STEPS.length - 1;
  const err = (key: string) => (errors[key] ? [errors[key]] : undefined);
  const next = () => {
    const found = validateStep(step, a);
    setErrors(found);
    if (Object.keys(found).length === 0) setStep(step + 1);
  };
  const ai = choices.data?.ai;
  const hasCv = (existing.data?.masters.length ?? 0) > 0;

  const submit = form.handle(async () => {
    const found = validateStep(step, a);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    for (let s = 0; s < STEPS.length - 1; s += 1) {
      const earlier = validateStep(s, a);
      if (Object.keys(earlier).length > 0) {
        setStep(s);
        setErrors(earlier);
        return;
      }
    }
    const built = await cvApi.build(toApiAnswers(a), polish);
    clearDraft();
    client.invalidateQueries({ queryKey: ["cv"] });
    const extra = polish ? ` ${built.polished} bullet${built.polished === 1 ? "" : "s"} reworded.${built.kept_as_written ? ` ${built.kept_as_written} kept as you wrote them because the rewording added something new.` : ""}` : "";
    notify(`Your CV is saved. Its ATS readiness is ${built.readiness} out of 100.${extra}`);
    navigate(`/cv/${built.id}`);
  });

  return (
    <>
      <PageHeader title="Build your CV" subtitle={<Link to="/cv" className="link-target text-brand underline">Back to your CVs</Link>} />
      <p className="mb-3 text-sm text-muted">
        A few short questions, about five minutes. We turn your answers into a clean one-column CV that applicant tracking systems can read. We only use what you type: nothing is added for you.
        Your answers stay in this tab until you finish.
      </p>
      {hasCv && (
        <div className="mb-3">
          <Notice>You already have a CV. Building a new one adds a new version and makes it your current CV. Your earlier versions are kept.</Notice>
        </div>
      )}
      <div className="mb-4" aria-live="polite">
        <p className="mb-1 text-sm font-medium">{progress.label}</p>
        <Progress value={progress.percent} label="Progress through the CV questions" />
      </div>

      <Card>
        <h2 ref={heading} tabIndex={-1} className="mb-3 text-lg font-semibold outline-none">
          {STEPS[step]}
        </h2>
        <form
          noValidate
          onSubmit={(event) => {
            if (!last) {
              event.preventDefault(); // Enter in a field means "next", never "build"
              next();
              return;
            }
            return submit(event);
          }}
        >

          {step === 0 && (
            <>
              <TextField label="Your name" autoComplete="name" value={a.name} maxLength={80} errors={err("name")} onChange={(e) => setA({ ...a, name: e.target.value })} />
              <TextField label="Email" type="email" autoComplete="email" value={a.email} maxLength={120} errors={err("email")} onChange={(e) => setA({ ...a, email: e.target.value })} />
              <TextField label="Phone (optional)" type="tel" autoComplete="tel" hint="With the country code, such as +60 12 345 6789." value={a.phone} maxLength={30} onChange={(e) => setA({ ...a, phone: e.target.value })} />
              <TextField label="City and country (optional)" autoComplete="address-level2" hint="For example Kuala Lumpur, Malaysia." value={a.location} maxLength={80} onChange={(e) => setA({ ...a, location: e.target.value })} />
              <TextField label="Profile link (optional)" hint="LinkedIn, GitHub or a portfolio, written in full, such as linkedin.com/in/yourname." value={a.links[0] ?? ""} maxLength={120} onChange={(e) => setA({ ...a, links: [e.target.value, ...a.links.slice(1)] })} />
            </>
          )}
          {step === 1 && (
            <TextAreaField label="One or two sentences about you (optional)" rows={4} maxLength={450} hint="What you do and what you are good at, in your own words. You can skip this." value={a.summary} onChange={(e) => setA({ ...a, summary: e.target.value })} />
          )}
          {step === 2 && (
            <>
              <p className="mb-3 text-sm text-muted">Newest job first. Add up to {MAX_ROLES}. Three bullets each is plenty: what you did and, where you know it, a real number. Skip this step if you have no paid work yet and add a project later.</p>
              {a.roles.map((r, i) => (
                <fieldset key={i} className="mb-4 rounded-lg border border-border p-3">
                  <legend className="px-1 text-sm font-medium">Job {i + 1}</legend>
                  <TextField label="Job title" value={r.title} maxLength={80} errors={err(`roles.${i}.title`)} onChange={(e) => setA({ ...a, roles: set(a.roles, i, { title: e.target.value }) })} />
                  <TextField label="Company" value={r.company} maxLength={80} errors={err(`roles.${i}.company`)} onChange={(e) => setA({ ...a, roles: set(a.roles, i, { company: e.target.value }) })} />
                  <div className="grid gap-x-3 sm:grid-cols-2">
                    <TextField label="Started" placeholder="Jan 2022" value={r.start} maxLength={20} errors={err(`roles.${i}.start`)} onChange={(e) => setA({ ...a, roles: set(a.roles, i, { start: e.target.value }) })} />
                    <TextField label="Ended" placeholder="Leave empty if you still work here" value={r.end} maxLength={20} errors={err(`roles.${i}.end`)} onChange={(e) => setA({ ...a, roles: set(a.roles, i, { end: e.target.value }) })} />
                  </div>
                  <TextField label="Place (optional)" value={r.location} maxLength={60} onChange={(e) => setA({ ...a, roles: set(a.roles, i, { location: e.target.value }) })} />
                  {r.bullets.map((b, n) => (
                    <TextField
                      key={n}
                      label={`What you did, point ${n + 1}${n === 0 ? "" : " (optional)"}`}
                      value={b}
                      maxLength={300}
                      onChange={(e) => setA({ ...a, roles: set(a.roles, i, { bullets: r.bullets.map((x, k) => (k === n ? e.target.value : x)) }) })}
                    />
                  ))}
                  {a.roles.length > 1 && (
                    <Button variant="outline" small onClick={() => setA({ ...a, roles: a.roles.filter((_, k) => k !== i) })}>
                      Remove job {i + 1}
                    </Button>
                  )}
                </fieldset>
              ))}
              {a.roles.length < MAX_ROLES && (
                <Button variant="outline" onClick={() => setA({ ...a, roles: [...a.roles, emptyRole()] })}>
                  Add another job
                </Button>
              )}
            </>
          )}
          {step === 3 && (
            <>
              {a.education.map((e, i) => (
                <fieldset key={i} className="mb-4 rounded-lg border border-border p-3">
                  <legend className="px-1 text-sm font-medium">School {i + 1}</legend>
                  <TextField label="School or university" value={e.school} maxLength={100} errors={err(`education.${i}.school`)} onChange={(ev) => setA({ ...a, education: set(a.education, i, { school: ev.target.value }) })} />
                  <TextField label="Course or degree (optional)" value={e.degree} maxLength={100} onChange={(ev) => setA({ ...a, education: set(a.education, i, { degree: ev.target.value }) })} />
                  <div className="grid gap-x-3 sm:grid-cols-2">
                    <TextField label="Started (optional)" placeholder="2018" value={e.start} maxLength={20} errors={err(`education.${i}.start`)} onChange={(ev) => setA({ ...a, education: set(a.education, i, { start: ev.target.value }) })} />
                    <TextField label="Finished (optional)" placeholder="2021" value={e.end} maxLength={20} errors={err(`education.${i}.end`)} onChange={(ev) => setA({ ...a, education: set(a.education, i, { end: ev.target.value }) })} />
                  </div>
                </fieldset>
              ))}
              {a.education.length < 3 && (
                <Button variant="outline" onClick={() => setA({ ...a, education: [...a.education, { school: "", degree: "", start: "", end: "" }] })}>
                  Add another school
                </Button>
              )}
            </>
          )}
          {step === 4 && (
            <>
              <p className="mb-3 text-sm text-muted">List the skills you really use, separated by commas, in groups such as Tools or Languages. Only list what you could talk about in an interview.</p>
              {a.skills.map((g, i) => (
                <div key={i} className="grid gap-x-3 sm:grid-cols-[12rem_1fr]">
                  <TextField label="Group name" value={g.group} maxLength={40} onChange={(e) => setA({ ...a, skills: set(a.skills, i, { group: e.target.value }) })} />
                  <TextField label={`Skills in ${g.group || "this group"}`} placeholder="Python, SQL, Excel" value={g.items} onChange={(e) => setA({ ...a, skills: set(a.skills, i, { items: e.target.value }) })} />
                </div>
              ))}
              {a.skills.length < 6 && (
                <Button variant="outline" onClick={() => setA({ ...a, skills: [...a.skills, { group: "", items: "" }] })}>
                  Add a group
                </Button>
              )}
            </>
          )}
          {step === 5 && (
            <>
              <p className="mb-3 text-sm text-muted">Optional, but a good place to show your work if you have little paid experience.</p>
              {a.projects.map((p, i) => (
                <fieldset key={i} className="mb-4 rounded-lg border border-border p-3">
                  <legend className="px-1 text-sm font-medium">Project {i + 1}</legend>
                  <TextField label="Project name" value={p.name} maxLength={80} onChange={(e) => setA({ ...a, projects: set(a.projects, i, { name: e.target.value }) })} />
                  <TextField label="What it is and what you did" value={p.description} maxLength={300} onChange={(e) => setA({ ...a, projects: set(a.projects, i, { description: e.target.value }) })} />
                  <TextField label="Link (optional)" value={p.link} maxLength={120} onChange={(e) => setA({ ...a, projects: set(a.projects, i, { link: e.target.value }) })} />
                </fieldset>
              ))}
              {a.projects.length < 3 && (
                <Button variant="outline" onClick={() => setA({ ...a, projects: [...a.projects, { name: "", description: "", link: "" }] })}>
                  Add another project
                </Button>
              )}
            </>
          )}
          {last && (
            <>
              <TextField label="Languages you speak (optional)" placeholder="English, Malay" value={a.languages} maxLength={200} onChange={(e) => setA({ ...a, languages: e.target.value })} />
              <TextField label="Certificates (optional)" placeholder="AWS Cloud Practitioner, 2023" value={a.certificates} maxLength={300} onChange={(e) => setA({ ...a, certificates: e.target.value })} />
              {ai?.available ? (
                <CheckField
                  label="Polish my wording"
                  hint="Your own AI tidies your bullets only. Any bullet that gains a number, name or skill you did not write keeps your own words."
                  checked={polish}
                  onChange={(e) => setPolish(e.target.checked)}
                />
              ) : (
                ai && (
                  <p className="mb-3 text-sm text-muted">
                    Want your wording polished? {ai.missing_message}{" "}
                    <Link to={ai.settings_link} className="text-brand underline">
                      Open AI settings
                    </Link>
                    . Without it your CV is built from your own words.
                  </p>
                )
              )}
              {errors.form && <Notice tone="error">{errors.form}</Notice>}
            </>
          )}
          <FormError message={form.error} />
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="outline" disabled={step === 0 || form.busy} onClick={() => { setErrors({}); setStep(step - 1); }}>
              Back
            </Button>
            {last ? (
              <Button key="build" type="submit" disabled={form.busy}>
                {form.busy ? "Building…" : "Build my CV"}
              </Button>
            ) : (
              <Button key="next" onClick={next}>Next</Button> /* a separate element from "Build my CV": the same one would turn into a submit button in the middle of the click */
            )}
            <Button
              variant="ghost"
              onClick={() => {
                if (!window.confirm("Clear everything you have typed here?")) return;
                clearDraft();
                setA(emptyAnswers());
                setStep(0);
                setErrors({});
              }}
            >
              Start again
            </Button>
          </div>
        </form>
      </Card>
    </>
  );
}
