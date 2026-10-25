import type { ProfileData } from "./api";

export type EmailKey = "followups" | "interviews" | "weekly" | "alerts";
export type EmailState = "on" | "off" | "owner_off";
export type EmailRow = { key: EmailKey; label: string; hint: string; chosen: boolean; state: EmailState; line: string };

export type EmailChoices = { email_followups: boolean; email_interviews: boolean; email_weekly: boolean };

/** The email choices as the profile holds them (older answers without the fields count as the defaults). */
export function choicesOf(profile: ProfileData["profile"]): EmailChoices {
  return { email_followups: profile.email_followups ?? true, email_interviews: profile.email_interviews ?? true, email_weekly: profile.email_weekly ?? false };
}

const LINES: Record<EmailState, string> = {
  on: "On. You will get this.",
  off: "Off. You will not get this.",
  owner_off: "You have this on, but the site owner has not switched it on yet, so nothing is sent for now.",
};

function stateOf(chosen: boolean, ownerOn: boolean): EmailState {
  if (!chosen) return "off";
  return ownerOn ? "on" : "owner_off";
}

/**
 * The four kinds of email, each with the person's own choice and whether the site owner has switched that kind on. A choice only matters once
 * the owner has; an "off" is always plain "off". `site` values the server did not send count as not switched on.
 */
export function emailRows(profile: ProfileData["profile"], site: ProfileData["site"], draft: EmailChoices = choicesOf(profile)): EmailRow[] {
  const mk = (key: EmailKey, label: string, hint: string, chosen: boolean, ownerOn: boolean): EmailRow => {
    const state = stateOf(chosen, ownerOn);
    return { key, label, hint, chosen, state, line: LINES[state] };
  };
  return [
    mk("followups", "Follow-up reminders", "One email a day at most, listing follow-ups that have just become due.", draft.email_followups, !!site.followup_emails_enabled),
    mk("interviews", "Interview reminders", "A reminder the day before an interview.", draft.email_interviews, !!site.followup_emails_enabled),
    mk("weekly", "Your week, once a week", "What is due, what is coming up and your best new matches. Never more than one a week, and none when there is nothing to say.", draft.email_weekly, !!site.weekly_emails_enabled),
    mk("alerts", "New job alerts", "Changed in the Job alerts card above.", !!profile.scan_digest_enabled, !!site.scan_emails_enabled),
  ];
}

/** True when saving would change something (so the Save button can stay quiet until then). */
export function emailsChanged(profile: ProfileData["profile"], draft: EmailChoices): boolean {
  const now = choicesOf(profile);
  return now.email_followups !== draft.email_followups || now.email_interviews !== draft.email_interviews || now.email_weekly !== draft.email_weekly;
}

/** A profile payload without the email choices: the big profile form leaves them to the Emails card, so saving it never undoes them. */
export function withoutEmails<T extends Partial<EmailChoices>>(values: T): Omit<T, keyof EmailChoices> {
  const rest = { ...values };
  delete rest.email_followups;
  delete rest.email_interviews;
  delete rest.email_weekly;
  return rest;
}

/** The sentence about the address: nothing is ever sent to one the person has not confirmed. */
export function addressLine(email: string, verified: boolean | undefined): string {
  if (!email) return "You have no email address on your account yet, so nothing can be sent. Add one under Your account below.";
  if (verified) return `Emails go to ${email}.`;
  return `Your address ${email} is not confirmed yet, so nothing is sent until you confirm it. Look for our email, or add it again under Your account below.`;
}
