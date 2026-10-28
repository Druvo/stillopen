import { request } from "@/lib/api";

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

const q = (key: string) => `key=${encodeURIComponent(key)}`;

export const depthApi = {
  process: (jobId: number) => request<Process>("GET", `/jobs/${jobId}/process`),
  jobTally: (jobId: number) => request<Tally>("GET", `/jobs/${jobId}/came-up`),
  setJobCameUp: (jobId: number, key: string, value: boolean) => request<Tally>("POST", `/jobs/${jobId}/came-up`, { key, value }),
  planTally: (planId: number) => request<Tally>("GET", `/prep/plans/${planId}/came-up`),
  setPlanCameUp: (questionId: number, value: boolean) => request<Tally>("POST", `/prep/questions/${questionId}/came-up`, { value }),

  bank: (search: string, tag: string) => request<Bank>("GET", `/bank?q=${encodeURIComponent(search)}&tag=${encodeURIComponent(tag)}`),
  addBank: (v: Partial<BankValues>) => request<BankItem>("POST", "/bank", v),
  editBank: (id: number, v: Partial<BankValues>) => request<BankItem>("PATCH", `/bank/${id}`, v),
  deleteBank: (id: number, confirm = false) => request<{ ok: true }>("DELETE", `/bank/${id}${confirm ? "?confirm=true" : ""}`),

  companies: () => request<{ companies: CompanyRow[] }>("GET", "/companies"),
  company: (key: string) => request<CompanyPage>("GET", `/companies/page?${q(key)}`),
  editCompany: (key: string, v: Partial<Pick<CompanyPage, "notes" | "website" | "careers" | "linkedin" | "watched">>) =>
    request<CompanyPage>("PATCH", `/companies/page?${q(key)}`, v),
};

/** The address of a company's page. The name is the key; the server matches it ignoring capitals. */
export const companyPath = (name: string) => `/companies/${encodeURIComponent(name)}`;
