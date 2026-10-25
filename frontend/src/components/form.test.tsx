import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { Toasts } from "@/lib/toast";
import { CheckField, RadioGroup, SelectField, TextAreaField, TextField, useSubmit } from "./form";

afterEach(cleanup);

describe("form fields", () => {
  it("points each control at its hint and its error messages", () => {
    render(
      <>
        <TextField label="Company" hint="As written on the posting." errors={["This field is required."]} />
        <TextAreaField label="Notes" hint="Optional." />
        <SelectField label="Per" errors={["Pick one."]}>
          <option>a</option>
        </SelectField>
        <CheckField label="Remote" hint="Anywhere." />
      </>,
    );
    const company = screen.getByLabelText("Company");
    const ids = company.getAttribute("aria-describedby")!.split(" ");
    expect(ids).toHaveLength(2);
    expect(document.getElementById(ids[0])!.textContent).toBe("As written on the posting.");
    expect(document.getElementById(ids[1])!.textContent).toBe("This field is required.");
    expect(company.getAttribute("aria-invalid")).toBe("true");

    const notes = screen.getByLabelText("Notes");
    expect(document.getElementById(notes.getAttribute("aria-describedby")!)!.textContent).toBe("Optional.");
    expect(notes.getAttribute("aria-invalid")).toBeNull();
    expect(document.getElementById(screen.getByLabelText("Per").getAttribute("aria-describedby")!)!.textContent).toBe("Pick one.");
    expect(document.getElementById(screen.getByLabelText("Remote").getAttribute("aria-describedby")!)!.textContent).toBe("Anywhere.");
  });

  it("has no aria-describedby when there is nothing to describe, and keeps one the caller gave", () => {
    render(
      <>
        <TextField label="Plain" />
        <TextField label="Own" aria-describedby="elsewhere" hint="Hint" />
      </>,
    );
    expect(screen.getByLabelText("Plain").getAttribute("aria-describedby")).toBeNull();
    expect(screen.getByLabelText("Own").getAttribute("aria-describedby")!.split(" ")[0]).toBe("elsewhere");
  });

  it("describes a group of radio buttons by its hint", () => {
    render(<RadioGroup legend="Theme" hint="Pick one." name="t" value="a" options={[{ value: "a", label: "A" }]} onChange={() => undefined} />);
    const group = screen.getByRole("group", { name: "Theme" });
    expect(document.getElementById(group.getAttribute("aria-describedby")!)!.textContent).toBe("Pick one.");
  });

  it("makes the whole checkbox row a target of at least 44 px on a phone", () => {
    render(<CheckField label="Remote" />);
    expect(screen.getByText("Remote").closest("label")!.className).toContain("min-h-11");
  });
});

function Demo({ fields }: { fields: Record<string, string[]> }) {
  const form = useSubmit();
  return (
    <form onSubmit={form.handle(async () => Promise.reject(new ApiError("Refused", 400, fields)))}>
      <TextField label="Company" errors={form.fields.company} />
      <TextField label="Role" errors={form.fields.role} />
      <button type="submit">Save</button>
    </form>
  );
}

describe("a refused form", () => {
  it("announces how many problems there are and moves focus to the first control that needs fixing", async () => {
    render(
      <>
        <Demo fields={{ role: ["Required."], company: ["Required.", "Too short."] }} />
        <Toasts />
      </>,
    );
    await act(async () => screen.getByRole("button", { name: "Save" }).click());
    await waitFor(() => expect(screen.getByTestId("announcer").textContent).toContain("3 problems to fix"));
    // the first control in the page that is marked invalid, not the first key the server listed
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Company")));
  });
});
