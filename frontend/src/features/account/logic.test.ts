import { describe, expect, it } from "vitest";
import { applyPreset, areaPayload, BLANK_AREA, canConfirmDelete, claudeCommand, lastUsed, mcpConfig, toFormData, toggleValue } from "./logic";

describe("toggleValue", () => {
  it("adds and removes", () => {
    expect(toggleValue(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleValue(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("toFormData", () => {
  it("repeats list keys, writes booleans as words and attaches the file", () => {
    const file = new File(["cv"], "cv.txt");
    const form = toFormData({ about: "hi", employment_types: ["full_time", "contract"], use_new_app: false, skip: null }, file);
    expect(form.getAll("employment_types")).toEqual(["full_time", "contract"]);
    expect(form.get("use_new_app")).toBe("false");
    expect(form.get("about")).toBe("hi");
    expect(form.has("skip")).toBe(false);
    expect((form.get("cv_file") as File).name).toBe("cv.txt");
  });
});

describe("areaPayload", () => {
  it("sends no minimum pay as null", () => {
    expect(areaPayload({ ...BLANK_AREA, place: "Malaysia" }).min_salary).toBeNull();
    expect(areaPayload({ ...BLANK_AREA, min_salary: " 8000 " }).min_salary).toBe("8000");
  });
});

describe("applyPreset", () => {
  it("fills provider, address and model and never a key", () => {
    const filled = applyPreset({ key: "groq", label: "Groq", provider: "openai", base_url: "https://api.groq.com/openai/v1", model: "m" });
    expect(filled).toEqual({ ai_provider: "openai", ai_base_url: "https://api.groq.com/openai/v1", ai_model: "m" });
  });
});

describe("assistant connection text", () => {
  it("builds the Claude Code command and the config block from the token", () => {
    expect(claudeCommand("https://x.test/mcp/", "so_abc")).toBe('claude mcp add --transport http stillopen https://x.test/mcp/ --header "Authorization: Bearer so_abc"');
    expect(JSON.parse(mcpConfig("https://x.test/mcp/", "so_abc")).mcpServers.stillopen.headers.Authorization).toBe("Bearer so_abc");
  });
});

describe("lastUsed", () => {
  const now = new Date("2026-10-25T12:00:00Z");
  it("says never, minutes, hours and days", () => {
    expect(lastUsed(null, now)).toBe("Never");
    expect(lastUsed("2026-10-25T11:30:00Z", now)).toBe("30 minutes ago");
    expect(lastUsed("2026-10-25T09:00:00Z", now)).toBe("3 hours ago");
    expect(lastUsed("2026-10-22T12:00:00Z", now)).toBe("3 days ago");
  });
});

describe("canConfirmDelete", () => {
  it("needs the exact username", () => {
    expect(canConfirmDelete("alice", "alice")).toBe(true);
    expect(canConfirmDelete("Alice", "alice")).toBe(false);
    expect(canConfirmDelete("", "")).toBe(false);
  });
});
