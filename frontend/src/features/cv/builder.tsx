"use client";

import { useState } from "react";
import { Button, Card, PageHeader } from "@/components/ui";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cvApi, type BuildCvIn, type EducationIn, type ExperienceIn, type ProjectIn } from "./api";

const lines = (text: string): string[] => text.split("\n").map((l) => l.trim()).filter(Boolean);

const BLANK_EXPERIENCE: ExperienceIn = { company: "", role: "", start: "", end: "", bullets: [] };
const BLANK_EDUCATION: EducationIn = { school: "", degree: "", start: "", end: "" };
const BLANK_PROJECT: ProjectIn = { name: "", description: "" };

function RemoveRow({ onRemove }: { onRemove: () => void }) {
  return (
    <div className="mt-2 flex justify-end">
      <Button variant="outline" small type="button" onClick={onRemove}>
        Remove
      </Button>
    </div>
  );
}

function ExperienceEditor({ items, onChange }: { items: ExperienceIn[]; onChange: (next: ExperienceIn[]) => void }) {
  const update = (i: number, patch: Partial<ExperienceIn>) => onChange(items.map((item, j) => (j === i ? { ...item, ...patch } : item)));
  return (
    <>
      {items.map((item, i) => (
        <Card key={i} className="mb-3 bg-bg">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Company" value={item.company} onChange={(e) => update(i, { company: e.target.value })} />
            <TextField label="Role" value={item.role} onChange={(e) => update(i, { role: e.target.value })} />
            <TextField label="Start" placeholder="2021" value={item.start} onChange={(e) => update(i, { start: e.target.value })} />
            <TextField label="End" placeholder="Present" value={item.end} onChange={(e) => update(i, { end: e.target.value })} />
          </div>
          <TextAreaField
            label="What you did"
            hint="One point per line. Be specific -- numbers and outcomes read better than duties."
            rows={3}
            value={item.bullets.join("\n")}
            onChange={(e) => update(i, { bullets: lines(e.target.value) })}
          />
          <RemoveRow onRemove={() => onChange(items.filter((_, j) => j !== i))} />
        </Card>
      ))}
      <Button variant="outline" type="button" onClick={() => onChange([...items, { ...BLANK_EXPERIENCE }])}>
        Add a role
      </Button>
    </>
  );
}

function EducationEditor({ items, onChange }: { items: EducationIn[]; onChange: (next: EducationIn[]) => void }) {
  const update = (i: number, patch: Partial<EducationIn>) => onChange(items.map((item, j) => (j === i ? { ...item, ...patch } : item)));
  return (
    <>
      {items.map((item, i) => (
        <Card key={i} className="mb-3 bg-bg">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="School" value={item.school} onChange={(e) => update(i, { school: e.target.value })} />
            <TextField label="Degree" value={item.degree} onChange={(e) => update(i, { degree: e.target.value })} />
            <TextField label="Start" placeholder="2015" value={item.start} onChange={(e) => update(i, { start: e.target.value })} />
            <TextField label="End" placeholder="2019" value={item.end} onChange={(e) => update(i, { end: e.target.value })} />
          </div>
          <RemoveRow onRemove={() => onChange(items.filter((_, j) => j !== i))} />
        </Card>
      ))}
      <Button variant="outline" type="button" onClick={() => onChange([...items, { ...BLANK_EDUCATION }])}>
        Add a school
      </Button>
    </>
  );
}

function ProjectEditor({ items, onChange }: { items: ProjectIn[]; onChange: (next: ProjectIn[]) => void }) {
  const update = (i: number, patch: Partial<ProjectIn>) => onChange(items.map((item, j) => (j === i ? { ...item, ...patch } : item)));
  return (
    <>
      {items.map((item, i) => (
        <Card key={i} className="mb-3 bg-bg">
          <TextField label="Project name" value={item.name} onChange={(e) => update(i, { name: e.target.value })} />
          <TextAreaField label="What it is" rows={2} value={item.description} onChange={(e) => update(i, { description: e.target.value })} />
          <RemoveRow onRemove={() => onChange(items.filter((_, j) => j !== i))} />
        </Card>
      ))}
      <Button variant="outline" type="button" onClick={() => onChange([...items, { ...BLANK_PROJECT }])}>
        Add a project
      </Button>
    </>
  );
}

/** A short, free, guided Q&A that assembles a first CV -- for someone who does not already have one to paste.
 * No AI: it only arranges what is typed here. The result becomes a normal CV version, same as pasting one by hand. */
export function CvBuilder() {
  const form = useSubmit();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [location, setLocation] = useState("");
  const [links, setLinks] = useState("");
  const [summary, setSummary] = useState("");
  const [skills, setSkills] = useState("");
  const [certifications, setCertifications] = useState("");
  const [experience, setExperience] = useState<ExperienceIn[]>([]);
  const [education, setEducation] = useState<EducationIn[]>([]);
  const [projects, setProjects] = useState<ProjectIn[]>([]);

  const submit = form.handle(async () => {
    const payload: BuildCvIn = {
      full_name: fullName, email, phone, location, links: lines(links), summary, skills: lines(skills),
      experience, education, projects, certifications: lines(certifications),
    };
    const made = await cvApi.build(payload);
    notify("Your CV is ready. Review it, then tailor it for a job whenever you like.");
    navigate(`/cv/${made.id}`);
  });

  return (
    <>
      <PageHeader title="Build your CV" subtitle={<Link to="/cv" className="text-brand underline">All CVs</Link>} />
      <p className="mb-4 text-sm text-muted">
        A few questions instead of a blank page. Nothing is invented -- it only arranges what you type here. You can edit every word afterwards, and{" "}
        <Link to="/profile" className="text-brand underline">paste a CV you already have</Link> instead, if you&apos;d rather.
      </p>
      <form onSubmit={submit}>
        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">You</h2>
          <TextField label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} errors={form.fields.full_name} />
          <div className="grid gap-3 sm:grid-cols-3">
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <TextField label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <TextField label="Location" placeholder="Dhaka, Bangladesh" value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
          <TextAreaField label="Links" hint="One per line -- LinkedIn, GitHub, a portfolio." rows={2} value={links} onChange={(e) => setLinks(e.target.value)} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Summary</h2>
          <TextAreaField label="A few sentences about you" hint="Optional. Leave blank to skip this section entirely." rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Skills</h2>
          <TextAreaField label="Your skills" hint="One per line." rows={3} value={skills} onChange={(e) => setSkills(e.target.value)} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Experience</h2>
          <ExperienceEditor items={experience} onChange={setExperience} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Education</h2>
          <EducationEditor items={education} onChange={setEducation} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Projects</h2>
          <p className="mb-2 text-sm text-muted">Optional.</p>
          <ProjectEditor items={projects} onChange={setProjects} />
        </Card>

        <Card className="mb-4">
          <h2 className="mb-2 font-semibold">Certifications</h2>
          <TextAreaField label="Certifications" hint="Optional. One per line." rows={2} value={certifications} onChange={(e) => setCertifications(e.target.value)} />
        </Card>

        <FormError message={form.error} />
        <Button type="submit" disabled={form.busy}>
          {form.busy ? "Building…" : "Build my CV"}
        </Button>
      </form>
    </>
  );
}
