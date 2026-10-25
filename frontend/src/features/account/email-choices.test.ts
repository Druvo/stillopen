import { describe, expect, it } from "vitest";
import type { ProfileData } from "./api";
import { addressLine, choicesOf, emailRows, emailsChanged, withoutEmails } from "./email-choices";

const profile = (over: Partial<ProfileData["profile"]> = {}): ProfileData["profile"] => ({
  target_roles: "", home_country: "", employment_types: [], seniority_levels: [], industries: "", languages: "", notice_period: "", salary_floor: "", deal_breakers: "",
  about: "", profile_cv: "", scan_digest_enabled: false, timezone: "", email_followups: true, email_interviews: true, email_weekly: false, ...over,
});
const site = (over: Partial<ProfileData["site"]> = {}): ProfileData["site"] => ({ scan_emails_enabled: false, assistant_enabled: true, timezone: "UTC", ...over });
const byKey = (rows: ReturnType<typeof emailRows>) => Object.fromEntries(rows.map((r) => [r.key, r.state]));

describe("emailRows", () => {
  it("says which are on, which the site owner has not switched on and which are off", () => {
    const rows = emailRows(profile({ email_weekly: true }), site({ followup_emails_enabled: true, weekly_emails_enabled: false }));
    expect(byKey(rows)).toEqual({ followups: "on", interviews: "on", weekly: "owner_off", alerts: "off" });
    expect(rows.find((r) => r.key === "weekly")?.line).toContain("site owner has not switched it on");
  });

  it("an off choice is plain off whatever the owner did; nothing is on until the owner has switched it on", () => {
    expect(byKey(emailRows(profile({ email_followups: false }), site({ followup_emails_enabled: true }))).followups).toBe("off");
    expect(byKey(emailRows(profile(), site())).followups).toBe("owner_off");
    expect(byKey(emailRows(profile({ scan_digest_enabled: true }), site({ scan_emails_enabled: true }))).alerts).toBe("on");
  });

  it("reads the draft ticks, not only what is saved", () => {
    const rows = emailRows(profile(), site({ followup_emails_enabled: true, weekly_emails_enabled: true }), { email_followups: false, email_interviews: true, email_weekly: true });
    expect(byKey(rows)).toMatchObject({ followups: "off", weekly: "on" });
  });

  it("older answers without the fields count as the defaults", () => {
    const old = profile();
    delete old.email_followups;
    delete old.email_interviews;
    delete old.email_weekly;
    expect(choicesOf(old)).toEqual({ email_followups: true, email_interviews: true, email_weekly: false });
  });
});

describe("emailsChanged and withoutEmails", () => {
  it("only reports a change when a tick differs", () => {
    expect(emailsChanged(profile(), choicesOf(profile()))).toBe(false);
    expect(emailsChanged(profile(), { ...choicesOf(profile()), email_weekly: true })).toBe(true);
  });
  it("leaves the email choices out of the big profile save", () => {
    const rest = withoutEmails(profile());
    expect(rest).not.toHaveProperty("email_weekly");
    expect(rest).not.toHaveProperty("email_followups");
    expect(rest).not.toHaveProperty("email_interviews");
    expect(rest).toHaveProperty("target_roles");
  });
});

describe("addressLine", () => {
  it("says nothing is sent to an address that is not confirmed", () => {
    expect(addressLine("a@b.co", true)).toBe("Emails go to a@b.co.");
    expect(addressLine("a@b.co", false)).toContain("nothing is sent until you confirm");
    expect(addressLine("a@b.co", undefined)).toContain("not confirmed");
    expect(addressLine("", false)).toContain("no email address");
  });
});
