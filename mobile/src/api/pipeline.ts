// API calls and types for interviews, contacts, referrals, offers, companies, the question bank, "this came up", the hiring process and the
// calendar link (worker B). Shapes copied from the website's frontend/src/features/pipeline/{api,depth-api}.ts.
import { api } from "./client";

const B = "/api/v1";

export type JobRef = { id: number; role: string; company: string };
export type JobChoice = { id: number; label: string };
export type Choice = { value: string; label: string };
export type Ok = { ok: true };

export type Interview = {
  id: number; job: JobRef; scheduled_at: string; scheduled_local: string; kind: string; kind_label: string; where: string; notes: string;
  outcome: string; outcome_label: string; upcoming: boolean;
  custom_label: string; stage_name: string; interviewers: { id: number; name: string }[];
};
export type InterviewList = {
  upcoming: Interview[]; past: Interview[]; jobs: JobChoice[]; kinds: Choice[]; outcomes: Choice[]; contacts: { id: number; label: string }[];
  google: { connected: boolean; sync: boolean };
};
export type InterviewValues = { application: string; scheduled_at: string; kind: string; where: string; notes: string; custom_label: string; contacts: number[] };

export type Referral = { id: number; job: JobRef; status: string; status_label: string; note: string };
export type Contact = {
  id: number; name: string; company: string; title: string; email: string; link: string; notes: string; last_contacted: string; referrals: Referral[];
  interviewed_you_for: { id: number; job_id: number; label: string; when: string }[];
};
export type ContactList = { contacts: Contact[]; jobs: JobChoice[]; referral_statuses: Choice[] };
export type ContactValues = { name: string; company: string; title: string; email: string; link: string; last_contacted: string; notes: string };
export type ReferralValues = { contact: string; application: string; status: string; note: string };
export type Finding = { text: string };
export type ReferralDraftResult = { subject: string; body: string; to: string; method: "template" | "ai"; flagged: Finding[]; flagged_count: number; notice: string };

export type Offer = {
  id: number; job: JobRef; base: string; period: string; period_label: string; currency: string; bonus: string; equity: string; signing: string;
  other_benefits: string; deadline: string; status: string; status_label: string; notes: string; yearly_base: string; yearly_total: string; first_year_total: string;
};
export type OfferGroup = { currency: string; rows: { offer: Offer; behind: string; best: boolean }[] };
export type OfferList = { offers: Offer[]; groups: OfferGroup[]; jobs: JobChoice[]; periods: Choice[]; statuses: Choice[] };
export type OfferValues = {
  application: string; base: string; period: string; currency: string; bonus: string; equity: string; other_benefits: string; signing: string; deadline: string; notes: string;
};
export type OfferNote = {
  differences: { currency: string; lines: string[] }[]; ask_about: string[];
  counter_note: { subject: string; body: string; flagged: Finding[]; flagged_count: number } | null; ai: boolean; notice: string; counter_message: string;
};

/** Saving an interview or an offer says which status the job could move to, if it is not there yet (the person decides). */
export type SuggestStatus = { id: number; name: string; label: string };
export type Saved = { id: number; suggest_status: SuggestStatus | null; calendar_note?: string };
export type CalendarLink = { enabled: boolean; url: string; created_at: string | null; last_used_at: string | null };

export type Interviewer = { id: number; name: string; title?: string };
export type Stage = {
  id: number; kind: string; kind_label: string; name: string; custom_label: string; scheduled_at: string; scheduled_local: string;
  outcome: string; outcome_label: string; outcome_word: string; upcoming: boolean; where: string; notes: string; interviewers: Interviewer[];
};
export type Process = {
  job: { id: number; role: string; company: string; status: string };
  summary: string;
  stages: Stage[];
  offers: { id: number; status: string; status_label: string }[];
};
export type Tally = { total: number; came_up: number; ticked: (number | string)[]; text: string };

export type BankItem = {
  id: number; question: string; answer: string; tags: string[]; linked: boolean; updated_at: string;
  interviews: { id: number; label: string; job_id: number }[]; jobs: { id: number; label: string }[];
};
export type Bank = { questions: BankItem[]; tags: string[]; interviews: { id: number; label: string }[]; jobs: { id: number; label: string }[] };
export type BankValues = { question: string; answer: string; tags: string[]; interview_ids: number[]; job_ids: number[] };

export type CompanyRow = { key: string; name: string; jobs: number; contacts: number; watched: boolean };
export type CompanyPage = {
  key: string; name: string; watched: boolean; notes: string; website: string; careers: string; linkedin: string;
  jobs: { id: number; role: string; status: string; applied_date: string }[];
  contacts: { id: number; name: string; title: string }[];
  interviews: { id: number; job_id: number; role: string; name: string; when: string; outcome_label: string; interviewers: string[] }[];
  offers: { id: number; job_id: number; role: string; status_label: string; base: string; currency: string }[];
};

export type Insights = {
  tracked: number; applied: number; interviewed: number; offered: number; interview_rate: number | null; offer_rate: number | null;
  median_days_to_interview: number | null; median_days_to_offer: number | null;
  channels: { label: string; applied: number; interviews: number; offers: number }[];
  referred_applied: number; referred_interviewed: number;
  by_score: { label: string; applied: number; interviews: number; offers: number; interview_rate: number | null; offer_rate: number | null }[];
  monthly_trend: { month: string; applied: number; interviews: number; offers: number; interview_rate: number | null; offer_rate: number | null }[];
  rejection_patterns: { term: string; count: number }[];
};

export type PrepQuestion = { id: string; question: string; testing: string; outline: string[]; flags: string[] };
export type PrepGroup = { key: string; title: string; questions: PrepQuestion[] };
export type StoredPrep = { prep: { groups: PrepGroup[] } | null; ai: boolean };

const key = (k: string) => `key=${encodeURIComponent(k)}`;

export const pipelineApi = {
  interviews: () => api.get<InterviewList>(`${B}/interviews`),
  addInterview: (v: InterviewValues) => api.post<Saved>(`${B}/interviews`, v),
  editInterview: (id: number, v: InterviewValues) => api.patch<Saved>(`${B}/interviews/${id}`, v),
  interviewOutcome: (id: number, outcome: string) => api.post<Ok & { suggest_status?: SuggestStatus | null }>(`${B}/interviews/${id}/outcome`, { outcome }),
  deleteInterview: (id: number) => api.delete<Ok>(`${B}/interviews/${id}`),

  calendarLink: () => api.get<CalendarLink>(`${B}/calendar-link`),
  makeCalendarLink: () => api.post<CalendarLink>(`${B}/calendar-link`),
  stopCalendarLink: () => api.delete<CalendarLink>(`${B}/calendar-link`),

  contacts: () => api.get<ContactList>(`${B}/contacts`),
  addContact: (v: ContactValues) => api.post<{ id: number }>(`${B}/contacts`, v),
  editContact: (id: number, v: ContactValues) => api.patch<{ id: number }>(`${B}/contacts/${id}`, v),
  deleteContact: (id: number) => api.delete<Ok>(`${B}/contacts/${id}`),
  addReferral: (v: ReferralValues) => api.post<{ id: number }>(`${B}/referrals`, v),
  referralStatus: (id: number, status: string) => api.post<Ok>(`${B}/referrals/${id}/status`, { status }),
  deleteReferral: (id: number) => api.delete<Ok>(`${B}/referrals/${id}`),
  referralDraft: (contactId: number, jobId: number, polish: boolean) => api.post<ReferralDraftResult>(`${B}/contacts/${contactId}/referral-draft`, { job_id: jobId, polish }),
  assistStatus: () => api.get<{ ai: boolean }>(`${B}/assist/status`),

  offers: () => api.get<OfferList>(`${B}/offers`),
  addOffer: (v: OfferValues) => api.post<Saved>(`${B}/offers`, v),
  editOffer: (id: number, v: OfferValues) => api.patch<Saved>(`${B}/offers/${id}`, v),
  offerStatus: (id: number, status: string) => api.post<Ok>(`${B}/offers/${id}/status`, { status }),
  deleteOffer: (id: number) => api.delete<Ok>(`${B}/offers/${id}`),
  compareOffers: (offerIds: number[], counterOfferId?: number | null) =>
    api.post<OfferNote>(`${B}/offers/compare-note`, counterOfferId ? { offer_ids: offerIds, counter_offer_id: counterOfferId } : { offer_ids: offerIds }),

  insights: () => api.get<Insights>(`${B}/insights`),

  process: (jobId: number) => api.get<Process>(`${B}/jobs/${jobId}/process`),
  jobTally: (jobId: number) => api.get<Tally>(`${B}/jobs/${jobId}/came-up`),
  setJobCameUp: (jobId: number, k: string, value: boolean) => api.post<Tally>(`${B}/jobs/${jobId}/came-up`, { key: k, value }),
  storedPrep: (jobId: number) => api.get<StoredPrep>(`${B}/jobs/${jobId}/interview-prep`),

  bank: (search: string, tag: string) => api.get<Bank>(`${B}/bank?q=${encodeURIComponent(search)}&tag=${encodeURIComponent(tag)}`),
  addBank: (v: Partial<BankValues>) => api.post<BankItem>(`${B}/bank`, v),
  editBank: (id: number, v: Partial<BankValues>) => api.patch<BankItem>(`${B}/bank/${id}`, v),
  deleteBank: (id: number, confirm = false) => api.delete<Ok>(`${B}/bank/${id}${confirm ? "?confirm=true" : ""}`),

  companies: () => api.get<{ companies: CompanyRow[] }>(`${B}/companies`),
  company: (name: string) => api.get<CompanyPage>(`${B}/companies/page?${key(name)}`),
  editCompany: (name: string, v: Partial<Pick<CompanyPage, "notes" | "website" | "careers" | "linkedin" | "watched">>) =>
    api.patch<CompanyPage>(`${B}/companies/page?${key(name)}`, v),

  /** Move a job to another status (the person confirmed it). */
  setStatus: (jobId: number, statusId: number) => api.patch<{ ok: true; label: string }>(`${B}/jobs/${jobId}/status`, { status: statusId }),
};
