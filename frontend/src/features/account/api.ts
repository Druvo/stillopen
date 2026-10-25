import { request } from "@/lib/api";

export type Choice = { value: string; label: string };

export type Area = {
  id: number; place: string; city: string; allow_remote: boolean; allow_hybrid: boolean; allow_onsite: boolean; needs_visa_sponsorship: boolean;
  needs_relocation_support: boolean; min_salary: number | null; salary_currency: string; salary_period: string; description: string;
};
export type AreaValues = Omit<Area, "id" | "description" | "min_salary"> & { min_salary: string };

export type ProfileValues = {
  target_roles: string; home_country: string; employment_types: string[]; seniority_levels: string[]; industries: string; languages: string; notice_period: string;
  salary_floor: string; deal_breakers: string; about: string; profile_cv: string; scan_digest_enabled: boolean;
};
export type ProfileData = {
  profile: ProfileValues;
  choices: { employment_types: Choice[]; seniority_levels: Choice[]; salary_periods: Choice[] };
  areas: Area[]; max_areas: number;
  site: { scan_emails_enabled: boolean; assistant_enabled: boolean };
  account: {
    username: string; email: string; is_staff: boolean; can_delete: boolean; google: boolean;
    counts: { jobs: number; cv_versions: number; documents: number; search_areas: number };
    classic: { email: string; password: string; two_step: string; connections: string; export: string; privacy: string };
  };
};

export type AiSettingsValues = {
  ai_provider: string; ai_model: string; ai_base_url: string; ai_custom_headers: string; ai_custom_body: string; ai_custom_response_path: string;
  ai_timeout: number | string; ai_max_input_chars: number | string; rag_enabled: boolean; rag_mode: string; rag_top_k: number | string;
  rag_chunk_chars: number | string; rag_always_chars: number | string; rag_embedding_base_url: string; rag_embedding_model: string;
};
export type Preset = { key: string; label: string; provider: string; base_url: string; model: string };
export type AiSettings = {
  settings: AiSettingsValues; has_key: boolean; has_rag_key: boolean; providers: Choice[]; rag_modes: Choice[]; presets: Preset[]; provider_label: string;
  usage: { calls: number; total_tokens: number; cost_usd: number | null; any_estimated: boolean };
  limits: Record<string, [number, number]>;
};
/** What goes to the server: the settings, plus keys that are only ever sent, never received. */
export type AiSave = Partial<AiSettingsValues> & { ai_api_key?: string; rag_embedding_key?: string; clear_ai_key?: boolean; clear_rag_key?: boolean };

export type OwnSource = { id: number; name: string; connector: string; connector_label: string; board_token: string; enabled: boolean };
export type SourcesData = { mine: OwnSource[]; shared: string[]; limit: number; connectors: Choice[]; help: Record<string, string> };

export type Token = {
  id: number; name: string; hint: string; can_write: boolean; state: string; created_at: string; last_used_at: string | null; expires_at: string | null; revoked: boolean;
};
export type AssistantData = { tokens: Token[]; endpoint: string; limit: number; active: number; expiry_choices: { days: number; label: string }[] };
export type NewToken = { token: string; record: Token; endpoint: string };

export type WelcomeData = { done: boolean; target_roles: string; home_country: string; profile_cv: string; open_remote: boolean; other_places: string };

type Payload = Record<string, unknown> | FormData;

export const accountApi = {
  profile: () => request<ProfileData>("GET", "/profile"),
  saveProfile: (values: Payload) => (values instanceof FormData ? request<ProfileData>("POST", "/profile", values) : request<ProfileData>("PUT", "/profile", values)),
  addArea: (values: Record<string, unknown>) => request<{ area: Area; warning?: string }>("POST", "/profile/areas", values),
  changeArea: (id: number, values: Record<string, unknown>) => request<{ area: Area; warning?: string }>("PATCH", `/profile/areas/${id}`, values),
  removeArea: (id: number) => request<{ ok: true }>("DELETE", `/profile/areas/${id}`),
  deleteAccount: (confirm: string) => request<{ ok: true }>("POST", "/account/delete", { confirm }),

  ai: () => request<AiSettings>("GET", "/ai-settings"),
  saveAi: (values: AiSave) => request<AiSettings>("PUT", "/ai-settings", values),

  sources: () => request<SourcesData>("GET", "/sources"),
  addSource: (values: { connector: string; board_token: string; name: string }) => request<{ source: OwnSource | null; openings: number; message: string; info: string }>("POST", "/sources", values),
  toggleSource: (id: number) => request<{ source: OwnSource }>("POST", `/sources/${id}/toggle`),
  removeSource: (id: number) => request<{ ok: true }>("DELETE", `/sources/${id}`),

  assistant: () => request<AssistantData>("GET", "/assistant"),
  makeToken: (values: { name: string; access: string; expires: number }) => request<NewToken>("POST", "/assistant/tokens", values),
  revokeToken: (id: number) => request<{ token: Token }>("POST", `/assistant/tokens/${id}/revoke`),

  welcome: () => request<WelcomeData>("GET", "/welcome"),
  saveWelcome: (values: Payload) => request<{ ok: true }>("POST", "/welcome", values),
  skipWelcome: () => request<{ ok: true }>("POST", "/welcome/skip"),
};
