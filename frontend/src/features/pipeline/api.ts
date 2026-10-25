import { request } from "@/lib/api";

export type JobRef = { id: number; role: string; company: string };
export type JobChoice = { id: number; label: string };
export type Choice = { value: string; label: string };

export type Interview = {
  id: number; job: JobRef; scheduled_at: string; scheduled_local: string; kind: string; kind_label: string; where: string; notes: string;
  outcome: string; outcome_label: string; upcoming: boolean;
};
export type InterviewList = { upcoming: Interview[]; past: Interview[]; jobs: JobChoice[]; kinds: Choice[]; outcomes: Choice[] };
export type InterviewValues = { application: string; scheduled_at: string; kind: string; where: string; notes: string };

export type Referral = { id: number; job: JobRef; status: string; status_label: string; note: string };
export type Contact = {
  id: number; name: string; company: string; title: string; email: string; link: string; notes: string; last_contacted: string; referrals: Referral[];
};
export type ContactList = { contacts: Contact[]; jobs: JobChoice[]; referral_statuses: Choice[] };
export type ContactValues = { name: string; company: string; title: string; email: string; link: string; last_contacted: string; notes: string };
export type ReferralValues = { contact: string; application: string; status: string; note: string };

export type Offer = {
  id: number; job: JobRef; base: string; period: string; period_label: string; currency: string; bonus: string; equity: string; signing: string;
  other_benefits: string; deadline: string; status: string; status_label: string; notes: string; yearly_total: string; first_year_total: string;
};
export type OfferGroup = { currency: string; rows: { offer: Offer; behind: string; best: boolean }[] };
export type OfferList = { offers: Offer[]; groups: OfferGroup[]; jobs: JobChoice[]; periods: Choice[]; statuses: Choice[] };
export type OfferValues = {
  application: string; base: string; period: string; currency: string; bonus: string; equity: string; other_benefits: string; signing: string; deadline: string; notes: string;
};

export type Insights = {
  tracked: number; applied: number; interviewed: number; offered: number; interview_rate: number | null; offer_rate: number | null;
  median_days_to_interview: number | null; channels: { label: string; applied: number; interviews: number; offers: number }[];
  referred_applied: number; referred_interviewed: number;
};

type Ok = { ok: true };

export const pipelineApi = {
  interviews: () => request<InterviewList>("GET", "/interviews"),
  addInterview: (v: InterviewValues) => request<{ id: number }>("POST", "/interviews", v),
  editInterview: (id: number, v: InterviewValues) => request<{ id: number }>("PATCH", `/interviews/${id}`, v),
  interviewOutcome: (id: number, outcome: string) => request<Ok>("POST", `/interviews/${id}/outcome`, { outcome }),
  deleteInterview: (id: number) => request<Ok>("DELETE", `/interviews/${id}`),

  contacts: () => request<ContactList>("GET", "/contacts"),
  addContact: (v: ContactValues) => request<{ id: number }>("POST", "/contacts", v),
  editContact: (id: number, v: ContactValues) => request<{ id: number }>("PATCH", `/contacts/${id}`, v),
  deleteContact: (id: number) => request<Ok>("DELETE", `/contacts/${id}`),
  addReferral: (v: ReferralValues) => request<{ id: number }>("POST", "/referrals", v),
  referralStatus: (id: number, status: string) => request<Ok>("POST", `/referrals/${id}/status`, { status }),
  deleteReferral: (id: number) => request<Ok>("DELETE", `/referrals/${id}`),

  offers: () => request<OfferList>("GET", "/offers"),
  addOffer: (v: OfferValues) => request<{ id: number }>("POST", "/offers", v),
  editOffer: (id: number, v: OfferValues) => request<{ id: number }>("PATCH", `/offers/${id}`, v),
  offerStatus: (id: number, status: string) => request<Ok>("POST", `/offers/${id}/status`, { status }),
  deleteOffer: (id: number) => request<Ok>("DELETE", `/offers/${id}`),

  insights: () => request<Insights>("GET", "/insights"),
};
