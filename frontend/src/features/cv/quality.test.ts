import { describe, expect, it } from "vitest";
import {
  applySuggestion, countsText, emptyAnswers, groupChecks, lineLabel, parseDraft, readinessText, readinessTone, stepProgress, STEPS, toApiAnswers, validateStep,
} from "./quality";

describe("groupChecks", () => {
  it("orders the groups fix, look, good and the heaviest check first", () => {
    const checks = [
      { id: "a", status: "pass" as const, weight: 3, lines: [] },
      { id: "b", status: "warn" as const, weight: 2, lines: [] },
      { id: "c", status: "fail" as const, weight: 1, lines: [] },
      { id: "d", status: "fail" as const, weight: 8, lines: [] },
    ];
    const groups = groupChecks(checks);
    expect(groups.map((g) => g.label)).toEqual(["Needs fixing", "Worth a look", "Looks good"]);
    expect(groups[0].items.map((c) => c.id)).toEqual(["d", "c"]);
  });
  it("leaves out an empty group", () => {
    expect(groupChecks([{ id: "a", status: "pass", weight: 1, lines: [] }]).map((g) => g.status)).toEqual(["pass"]);
  });
});

describe("wording", () => {
  it("never relies on colour alone", () => {
    expect(readinessText(78, "Good start")).toBe("78 out of 100: Good start");
    expect(countsText({ fail: 1, warn: 2, pass: 3 })).toBe("1 to fix, 2 worth a look, 3 fine");
    expect(lineLabel([])).toBe("");
    expect(lineLabel([4])).toBe("line 4");
    expect(lineLabel([4, 7])).toBe("lines 4, 7");
    expect(readinessTone(90)).toBe("good");
    expect(readinessTone(60)).toBe("warn");
    expect(readinessTone(10)).toBe("bad");
  });
});

describe("applySuggestion", () => {
  const cv = "# Jane\n\n## My Journey\n- Wrote the guide.\n- Built things.";
  it("replaces the line", () => {
    const r = applySuggestion(cv, { original: "- Wrote the guide.", replacement: "- Authored the guide." });
    expect(r.applied).toBe(true);
    expect(r.text).toBe("# Jane\n\n## My Journey\n- Authored the guide.\n- Built things.");
  });
  it("finds the line even with spaces at the ends", () => {
    expect(applySuggestion(cv, { original: "  - Built things.  ", replacement: "- Built many things." }).applied).toBe(true);
  });
  it("does not touch the text when the line is gone", () => {
    const r = applySuggestion(cv, { original: "- Not there.", replacement: "- x" });
    expect(r).toEqual({ text: cv, applied: false });
  });
  it("adds a missing summary under the name", () => {
    const r = applySuggestion(cv, { original: "", replacement: "Backend engineer." });
    expect(r.text).toBe("# Jane\n\n## Summary\nBackend engineer.\n\n## My Journey\n- Wrote the guide.\n- Built things.");
  });
  it("adds a summary at the top when there is no name heading", () => {
    expect(applySuggestion("Just text", { original: "", replacement: "Hi." }).text).toBe("## Summary\nHi.\n\nJust text");
  });
});

describe("validateStep", () => {
  it("asks for a name and a real email on the first step", () => {
    expect(Object.keys(validateStep(0, emptyAnswers()))).toEqual(["name", "email"]);
    const a = { ...emptyAnswers(), name: "Sam", email: "sam@example.com" };
    expect(validateStep(0, a)).toEqual({});
    expect(validateStep(0, { ...a, email: "sam@" }).email).toContain("name@example.com");
  });
  it("needs title, company and a start date only for a role that was started", () => {
    const a = emptyAnswers();
    expect(validateStep(2, a)).toEqual({});
    a.roles[0].bullets[0] = "did a thing";
    expect(Object.keys(validateStep(2, a))).toEqual(["roles.0.title", "roles.0.company", "roles.0.start"]);
    Object.assign(a.roles[0], { title: "Engineer", company: "Acme", start: "last spring" });
    expect(validateStep(2, a)["roles.0.start"]).toContain("Jan 2022");
    a.roles[0].start = "Jan 2022";
    a.roles[0].end = "tomorrow";
    expect(validateStep(2, a)["roles.0.end"]).toContain("leave it empty");
    a.roles[0].end = "Present";
    expect(validateStep(2, a)).toEqual({});
  });
  it("needs one job, school or project before building", () => {
    const last = STEPS.length - 1;
    const a = emptyAnswers();
    expect(validateStep(last, a).form).toContain("at least one");
    a.projects[0].name = "Help centre";
    expect(validateStep(last, a)).toEqual({});
  });
});

describe("toApiAnswers", () => {
  it("drops empty rows and trims", () => {
    const a = emptyAnswers();
    a.name = " Sam ";
    a.roles[0] = { title: " Eng ", company: "Acme", location: "", start: "2020", end: "", bullets: [" did x ", "", ""] };
    a.skills[0].items = "SQL, Excel";
    const out = toApiAnswers(a);
    expect(out.name).toBe("Sam");
    expect(out.roles).toHaveLength(1);
    expect(out.roles[0].bullets).toEqual(["did x"]);
    expect(out.skills).toEqual([{ group: "Tools", items: "SQL, Excel" }]);
    expect(out.links).toEqual([]);
    expect(out.education).toEqual([]);
    expect(out.projects).toEqual([]);
  });
});

describe("parseDraft", () => {
  it("round-trips a saved draft and clamps the step", () => {
    const answers = { ...emptyAnswers(), name: "Sam" };
    const read = parseDraft(JSON.stringify({ step: 99, answers }));
    expect(read?.answers.name).toBe("Sam");
    expect(read?.step).toBe(STEPS.length - 1);
  });
  it("ignores anything broken", () => {
    expect(parseDraft(null)).toBeNull();
    expect(parseDraft("{not json")).toBeNull();
    expect(parseDraft(JSON.stringify({ step: "1", answers: {} }))).toBeNull();
    const read = parseDraft(JSON.stringify({ step: 0, answers: { name: 5, roles: "x", unknown: 1 } }));
    expect(read?.answers.name).toBe("");
    expect(read?.answers.roles).toHaveLength(1);
  });
});

describe("stepProgress", () => {
  it("says where the person is", () => {
    expect(stepProgress(0)).toEqual({ label: "Step 1 of 8: Contact", percent: 13 });
    expect(stepProgress(7).percent).toBe(100);
  });
});

describe("publications and references", () => {
  it("checks the year and listed reference names", () => {
    const a = emptyAnswers();
    a.publications = [{ title: "T", venue: "", year: "soon", link: "" }];
    expect(validateStep(6, a)["publications.0.year"]).toBeTruthy();
    a.publications[0].year = "2023";
    a.references_mode = "listed";
    a.references = [{ name: "", role: "Boss", contact: "" }];
    expect(validateStep(6, a)["references.0.name"]).toBeTruthy();
  });
  it("sends no references unless they are listed", () => {
    const a = emptyAnswers();
    a.references = [{ name: "Bo", role: "", contact: "" }];
    expect(toApiAnswers(a).references).toEqual([]);
    a.references_mode = "listed";
    expect(toApiAnswers(a).references).toHaveLength(1);
  });
});
