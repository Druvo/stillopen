// The step-by-step CV builder (website: features/cv/builder.tsx). The answers stay on the phone until the person finishes.
import { useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { cvApi, type AiInfo } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Button, Card, Choice, confirm, Field, Muted, notify, Text, Toggle } from "../../ui";
import { errorText } from "../../ui/useApi";
import {
  emptyAnswers, emptyPublication, emptyReference, emptyRole, MAX_PUBLICATIONS, MAX_REFERENCES, MAX_ROLES, STEPS, stepProgress, toApiAnswers, validateStep,
  type BuilderAnswers,
} from "./logic/quality";

function set<T>(list: T[], index: number, patch: Partial<T>): T[] {
  return list.map((item, i) => (i === index ? { ...item, ...patch } : item));
}

const Group = ({ title, children }: { title: string; children: React.ReactNode }) => {
  const { colors } = useTheme();
  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, marginBottom: 12 }}>
      <Text style={{ fontWeight: "700", marginBottom: 8 }}>{title}</Text>
      {children}
    </View>
  );
};

export function CvBuilder({ answers, setAnswers, step, setStep, ai }: { answers: BuilderAnswers; setAnswers: (a: BuilderAnswers) => void; step: number; setStep: (s: number) => void; ai: AiInfo | null }) {
  const router = useRouter();
  const { colors } = useTheme();
  const a = answers;
  const setA = setAnswers;
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [polish, setPolish] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const progress = stepProgress(step);
  const last = step === STEPS.length - 1;
  const err = (key: string) => errors[key];

  function next() {
    const found = validateStep(step, a);
    setErrors(found);
    if (Object.keys(found).length === 0) setStep(step + 1);
  }

  async function build() {
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
    setBusy(true);
    setFailure("");
    try {
      const built = await cvApi.build(toApiAnswers(a), polish);
      const extra = polish ? ` ${built.polished} bullet${built.polished === 1 ? "" : "s"} reworded.${built.kept_as_written ? ` ${built.kept_as_written} kept as you wrote them because the rewording added something new.` : ""}` : "";
      notify("Your CV is saved", `Its ATS readiness is ${built.readiness} out of 100.${extra}`);
      setA(emptyAnswers());
      setStep(0);
      router.replace({ pathname: "/cv/[id]", params: { id: String(built.id) } });
    } catch (e) {
      setFailure(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View>
      <Muted style={{ marginBottom: 10 }}>
        A few short questions, about five minutes. We turn your answers into a clean one-column CV that applicant tracking systems can read. We only use what you type: nothing is added for you. Your answers stay on this phone until you finish.
      </Muted>
      <Text style={{ fontWeight: "600", marginBottom: 4 }}>{progress.label}</Text>
      <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceAlt, overflow: "hidden", marginBottom: 14 }}>
        <View style={{ width: `${progress.percent}%`, height: 8, backgroundColor: colors.accent }} />
      </View>

      <Card>
        <Text style={{ fontWeight: "700", fontSize: 18, marginBottom: 10 }}>{STEPS[step]}</Text>

        {step === 0 && (
          <>
            <Field label="Your name" value={a.name} maxLength={80} error={err("name")} autoComplete="name" onChangeText={(v) => setA({ ...a, name: v })} />
            <Field label="Email" value={a.email} maxLength={120} error={err("email")} keyboardType="email-address" autoCapitalize="none" autoComplete="email" onChangeText={(v) => setA({ ...a, email: v })} />
            <Field label="Phone (optional)" value={a.phone} maxLength={30} keyboardType="phone-pad" hint="With the country code, such as +60 12 345 6789." onChangeText={(v) => setA({ ...a, phone: v })} />
            <Field label="City and country (optional)" value={a.location} maxLength={80} hint="For example Kuala Lumpur, Malaysia." onChangeText={(v) => setA({ ...a, location: v })} />
            <Field label="Profile link (optional)" value={a.links[0] ?? ""} maxLength={120} autoCapitalize="none" keyboardType="url" hint="LinkedIn, GitHub or a portfolio, written in full, such as linkedin.com/in/yourname." onChangeText={(v) => setA({ ...a, links: [v, ...a.links.slice(1)] })} />
          </>
        )}

        {step === 1 && (
          <Field label="One or two sentences about you (optional)" value={a.summary} multiline maxLength={450} hint="What you do and what you are good at, in your own words. You can skip this." onChangeText={(v) => setA({ ...a, summary: v })} />
        )}

        {step === 2 && (
          <>
            <Muted style={{ marginBottom: 10 }}>Newest job first. Add up to {MAX_ROLES}. Three bullets each is plenty: what you did and, where you know it, a real number. Skip this step if you have no paid work yet and add a project later.</Muted>
            {a.roles.map((r, i) => (
              <Group key={i} title={`Job ${i + 1}`}>
                <Field label="Job title" value={r.title} maxLength={80} error={err(`roles.${i}.title`)} onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { title: v }) })} />
                <Field label="Company" value={r.company} maxLength={80} error={err(`roles.${i}.company`)} onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { company: v }) })} />
                <Field label="Started" value={r.start} maxLength={20} placeholder="Jan 2022" error={err(`roles.${i}.start`)} onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { start: v }) })} />
                <Field label="Ended" value={r.end} maxLength={20} placeholder="Leave empty if you still work here" error={err(`roles.${i}.end`)} onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { end: v }) })} />
                <Field label="Place (optional)" value={r.location} maxLength={60} onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { location: v }) })} />
                {r.bullets.map((b, n) => (
                  <Field
                    key={n}
                    label={`What you did, point ${n + 1}${n === 0 ? "" : " (optional)"}`}
                    value={b}
                    maxLength={300}
                    multiline
                    onChangeText={(v) => setA({ ...a, roles: set(a.roles, i, { bullets: r.bullets.map((x, k) => (k === n ? v : x)) }) })}
                  />
                ))}
                {a.roles.length > 1 ? <Button label={`Remove job ${i + 1}`} variant="secondary" onPress={() => setA({ ...a, roles: a.roles.filter((_, k) => k !== i) })} /> : null}
              </Group>
            ))}
            {a.roles.length < MAX_ROLES ? <Button label="Add another job" variant="secondary" onPress={() => setA({ ...a, roles: [...a.roles, emptyRole()] })} /> : null}
          </>
        )}

        {step === 3 && (
          <>
            {a.education.map((e, i) => (
              <Group key={i} title={`School ${i + 1}`}>
                <Field label="School or university" value={e.school} maxLength={100} error={err(`education.${i}.school`)} onChangeText={(v) => setA({ ...a, education: set(a.education, i, { school: v }) })} />
                <Field label="Course or degree (optional)" value={e.degree} maxLength={100} onChangeText={(v) => setA({ ...a, education: set(a.education, i, { degree: v }) })} />
                <Field label="Started (optional)" value={e.start} maxLength={20} placeholder="2018" error={err(`education.${i}.start`)} onChangeText={(v) => setA({ ...a, education: set(a.education, i, { start: v }) })} />
                <Field label="Finished (optional)" value={e.end} maxLength={20} placeholder="2021" error={err(`education.${i}.end`)} onChangeText={(v) => setA({ ...a, education: set(a.education, i, { end: v }) })} />
              </Group>
            ))}
            {a.education.length < 3 ? <Button label="Add another school" variant="secondary" onPress={() => setA({ ...a, education: [...a.education, { school: "", degree: "", start: "", end: "" }] })} /> : null}
          </>
        )}

        {step === 4 && (
          <>
            <Muted style={{ marginBottom: 10 }}>List the skills you really use, separated by commas, in groups such as Tools or Languages. Only list what you could talk about in an interview.</Muted>
            {a.skills.map((g, i) => (
              <Group key={i} title={`Group ${i + 1}`}>
                <Field label="Group name" value={g.group} maxLength={40} onChangeText={(v) => setA({ ...a, skills: set(a.skills, i, { group: v }) })} />
                <Field label={`Skills in ${g.group || "this group"}`} value={g.items} placeholder="Python, SQL, Excel" onChangeText={(v) => setA({ ...a, skills: set(a.skills, i, { items: v }) })} />
              </Group>
            ))}
            {a.skills.length < 6 ? <Button label="Add a group" variant="secondary" onPress={() => setA({ ...a, skills: [...a.skills, { group: "", items: "" }] })} /> : null}
          </>
        )}

        {step === 5 && (
          <>
            <Muted style={{ marginBottom: 10 }}>Optional, but a good place to show your work if you have little paid experience.</Muted>
            {a.projects.map((p, i) => (
              <Group key={i} title={`Project ${i + 1}`}>
                <Field label="Project name" value={p.name} maxLength={80} onChangeText={(v) => setA({ ...a, projects: set(a.projects, i, { name: v }) })} />
                <Field label="What it is and what you did" value={p.description} maxLength={300} multiline onChangeText={(v) => setA({ ...a, projects: set(a.projects, i, { description: v }) })} />
                <Field label="Link (optional)" value={p.link} maxLength={120} autoCapitalize="none" onChangeText={(v) => setA({ ...a, projects: set(a.projects, i, { link: v }) })} />
              </Group>
            ))}
            {a.projects.length < 3 ? <Button label="Add another project" variant="secondary" onPress={() => setA({ ...a, projects: [...a.projects, { name: "", description: "", link: "" }] })} /> : null}
          </>
        )}

        {step === 6 && (
          <>
            <Muted style={{ marginBottom: 10 }}>Both are optional. Publications are papers, articles or talks, one plain line each.</Muted>
            {a.publications.map((p, i) => (
              <Group key={i} title={`Publication ${i + 1}`}>
                <Field label="Title" value={p.title} maxLength={200} onChangeText={(v) => setA({ ...a, publications: set(a.publications, i, { title: v }) })} />
                <Field label="Journal, publisher or event (optional)" value={p.venue} maxLength={120} onChangeText={(v) => setA({ ...a, publications: set(a.publications, i, { venue: v }) })} />
                <Field label="Year (optional)" value={p.year} maxLength={10} placeholder="2023" keyboardType="number-pad" error={err(`publications.${i}.year`)} onChangeText={(v) => setA({ ...a, publications: set(a.publications, i, { year: v }) })} />
                <Field label="Link (optional)" value={p.link} maxLength={120} autoCapitalize="none" onChangeText={(v) => setA({ ...a, publications: set(a.publications, i, { link: v }) })} />
              </Group>
            ))}
            {a.publications.length < MAX_PUBLICATIONS ? <Button label="Add another publication" variant="secondary" onPress={() => setA({ ...a, publications: [...a.publications, emptyPublication()] })} /> : null}
            <View style={{ height: 14 }} />
            <Choice
              label="How publications are written"
              value={a.citation_style}
              onChange={(v) => setA({ ...a, citation_style: v })}
              options={[
                { value: "plain", label: "Plain: Title - Journal, 2023" },
                { value: "apa", label: "APA-like: (2023). Title. Journal." },
              ]}
            />
            <Text style={{ fontWeight: "700", marginBottom: 4 }}>References</Text>
            <Muted style={{ marginBottom: 8 }}>Most employers only ask for references later, so the usual choice is one line saying they are available on request.</Muted>
            <Choice
              value={a.references_mode}
              onChange={(v) => setA({ ...a, references_mode: v })}
              options={[
                { value: "off", label: "Leave them out" },
                { value: "on_request", label: "Available on request" },
                { value: "listed", label: `List up to ${MAX_REFERENCES}` },
              ]}
            />
            {a.references_mode === "listed" &&
              a.references.map((r, i) => (
                <Group key={i} title={`Reference ${i + 1}`}>
                  <Field label="Name" value={r.name} maxLength={80} error={err(`references.${i}.name`)} onChangeText={(v) => setA({ ...a, references: set(a.references, i, { name: v }) })} />
                  <Field label="Role and company (optional)" value={r.role} maxLength={120} onChangeText={(v) => setA({ ...a, references: set(a.references, i, { role: v }) })} />
                  <Field label="Email or phone (optional)" value={r.contact} maxLength={120} onChangeText={(v) => setA({ ...a, references: set(a.references, i, { contact: v }) })} />
                </Group>
              ))}
            {a.references_mode === "listed" && a.references.length < MAX_REFERENCES ? <Button label="Add another reference" variant="secondary" onPress={() => setA({ ...a, references: [...a.references, emptyReference()] })} /> : null}
          </>
        )}

        {last && (
          <>
            <Field label="Languages you speak (optional)" value={a.languages} maxLength={200} placeholder="English, Malay" onChangeText={(v) => setA({ ...a, languages: v })} />
            <Field label="Certificates (optional)" value={a.certificates} maxLength={300} placeholder="AWS Cloud Practitioner, 2023" onChangeText={(v) => setA({ ...a, certificates: v })} />
            {ai?.available ? (
              <Toggle label="Polish my wording" value={polish} onChange={setPolish} hint="Your own AI tidies your bullets only. Any bullet that gains a number, name or skill you did not write keeps your own words." />
            ) : ai ? (
              <View style={{ marginBottom: 12 }}>
                <Muted>Want your wording polished? {ai.missing_message} Without it your CV is built from your own words.</Muted>
                <Button label="Open AI settings" variant="ghost" onPress={() => router.push("/profile/ai" as Href)} />
              </View>
            ) : null}
            {errors.form ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{errors.form}</Text> : null}
          </>
        )}
        {failure ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{failure}</Text> : null}

        <View style={{ flexDirection: "row", gap: 10, marginTop: 6 }}>
          <Button label="Back" variant="secondary" disabled={step === 0 || busy} onPress={() => { setErrors({}); setStep(step - 1); }} />
          {last ? <Button label="Build my CV" onPress={build} busy={busy} style={{ flex: 1 }} /> : <Button label="Next" onPress={next} style={{ flex: 1 }} />}
        </View>
        <View style={{ marginTop: 8 }}>
          <Button
            label="Start again"
            variant="ghost"
            onPress={async () => {
              if (!(await confirm("Clear everything you have typed here?", undefined, "Clear"))) return;
              setA(emptyAnswers());
              setStep(0);
              setErrors({});
            }}
          />
        </View>
      </Card>
    </View>
  );
}
