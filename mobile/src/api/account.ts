// Account, profile, AI settings, assistant tokens, welcome questions, data import: the calls behind the screens in src/screens/account/.
// Shapes copied from the website (frontend/src/features/account/api.ts) and tracker/api/{account,ai_settings,aiusage,assistant,preferences}.py.
import { api } from "./client";

const V = "/api/v1";

export type Choice = { value: string; label: string };

export type Area = {
  id: number; place: string; city: string; allow_remote: boolean; allow_hybrid: boolean; allow_onsite: boolean; needs_visa_sponsorship: boolean;
  needs_relocation_support: boolean; min_salary: number | null; salary_currency: string; salary_period: string; description: string;
};
export type AreaValues = Omit<Area, "id" | "description" | "min_salary"> & { min_salary: string };

export type ProfileValues = {
  target_roles: string; home_country: string; employment_types: string[]; seniority_levels: string[]; industries: string; languages: string; notice_period: string;
  salary_floor: string; deal_breakers: string; about: string; profile_cv: string; scan_digest_enabled: boolean; draft_ahead_enabled: boolean; timezone: string; weekly_digest_enabled: boolean;
  email_followups?: boolean; email_interviews?: boolean; email_weekly?: boolean;
};
export type ProfileData = {
  profile: ProfileValues;
  choices: { employment_types: Choice[]; seniority_levels: Choice[]; salary_periods: Choice[]; timezones: string[] };
  areas: Area[];
  max_areas: number;
  site: {
    scan_emails_enabled: boolean; followup_emails_enabled?: boolean; weekly_emails_enabled?: boolean; weekly_digest_site_enabled: boolean;
    draft_ahead_site_enabled: boolean; assistant_enabled: boolean; timezone: string;
  };
  account: {
    username: string; email: string; email_verified?: boolean; is_staff: boolean; can_delete: boolean; google: boolean;
    counts: { jobs: number; cv_versions: number; documents: number; search_areas: number };
    classic: { email: string; password: string; two_step: string; connections: string; export: string; privacy: string };
  };
};

export type Preferences = {
  theme: "light" | "dark";
  text_size: "normal" | "large" | "larger";
  density: "comfortable" | "compact";
  quiet_days: number;
  goal_daily: number;
  goal_weekly: number;
  [key: string]: unknown;
};

export type Strength = { percent: number; complete: boolean; missing: { key: string; label: string; why: string; to: string }[] };
export type Suggestions = { roles: string[]; places: string[]; method: "ai" | "rules"; notice: string };

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

export type AiUsage = {
  month: string; calls: number; failed: number; input_tokens: number; output_tokens: number;
  costs: { currency: string; amount: number }[]; any_estimated: boolean; unpriced_calls: number;
  latency: { samples: number; p50_ms: number | null; p95_ms: number | null };
  models: { provider: string; model: string; currency: string; calls: number; input_tokens: number; output_tokens: number; cost: number | null; unpriced_calls: number; estimated: boolean }[];
  purposes: { purpose: string; label: string; calls: number; failed: number; input_tokens: number; output_tokens: number }[];
  recent: { id: number; at: string; purpose: string; provider: string; model: string; input_tokens: number | null; output_tokens: number | null; cost: number | null; currency: string; duration_ms: number | null; ok: boolean }[];
};

export type Token = {
  id: number; name: string; hint: string; can_write: boolean; state: string; created_at: string; last_used_at: string | null; expires_at: string | null; revoked: boolean;
};
export type AssistantData = { tokens: Token[]; endpoint: string; limit: number; active: number; expiry_choices: { days: number; label: string }[] };
export type NewToken = { token: string; record: Token; endpoint: string };

export type WelcomeData = { done: boolean; target_roles: string; home_country: string; profile_cv: string; open_remote: boolean; other_places: string };

export type DataImportReport = {
  preview: boolean; nothing: boolean; left_out: number;
  profile: { filled: string[]; kept: string[] };
  cvs: { add: number; have: number; left_out: number; stopped: string };
  covers: { add: number; have: number; no_job: number; stopped: string };
  notes: { add: number; have: number; kept: number; no_job: number };
};

/** A file picked on the phone, ready to be sent as multipart form data. */
export type PickedFile = { uri: string; name: string; mimeType?: string | null; size?: number | null };

function filePart(file: PickedFile): Blob {
  // React Native's FormData takes an object with a uri in place of a Blob.
  return { uri: file.uri, name: file.name, type: file.mimeType || "application/octet-stream" } as unknown as Blob;
}

/** Lists repeat the key, booleans are "true"/"false", and the file goes in under `fileField` (its text is read on the server; the file is not kept). */
export function toFormData(values: Record<string, unknown>, file: PickedFile | null, fileField: string): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) value.forEach((item) => form.append(key, String(item)));
    else form.append(key, String(value));
  }
  if (file) form.append(fileField, filePart(file));
  return form;
}

export const accountApi = {
  profile: () => api.get<ProfileData>(`${V}/profile`),
  saveProfile: (values: Record<string, unknown>) => api.put<ProfileData>(`${V}/profile`, values),
  saveProfileWithFile: (values: Record<string, unknown>, file: PickedFile) => api.upload<ProfileData>(`${V}/profile`, toFormData(values, file, "cv_file")),
  addArea: (values: Record<string, unknown>) => api.post<{ area: Area; warning?: string }>(`${V}/profile/areas`, values),
  changeArea: (id: number, values: Record<string, unknown>) => api.patch<{ area: Area; warning?: string }>(`${V}/profile/areas/${id}`, values),
  removeArea: (id: number) => api.delete<{ ok: true }>(`${V}/profile/areas/${id}`),
  deleteAccount: (confirm: string) => api.post<{ ok: true }>(`${V}/account/delete`, { confirm }),
  strength: () => api.get<Strength>(`${V}/profile/strength`),
  suggestRoles: (cv?: string) => api.post<Suggestions>(`${V}/profile/suggest`, cv && cv.trim() ? { cv } : {}),

  preferences: () => api.get<Preferences>(`${V}/preferences`),
  savePreferences: (patch: Partial<Preferences>) => api.put<Preferences>(`${V}/preferences`, patch),

  ai: () => api.get<AiSettings>(`${V}/ai-settings`),
  saveAi: (values: AiSave) => api.put<AiSettings>(`${V}/ai-settings`, values),
  usage: () => api.get<AiUsage>(`${V}/ai-usage`),

  assistant: () => api.get<AssistantData>(`${V}/assistant`),
  makeToken: (values: { name: string; access: string; expires: number }) => api.post<NewToken>(`${V}/assistant/tokens`, values),
  revokeToken: (id: number) => api.post<{ token: Token }>(`${V}/assistant/tokens/${id}/revoke`),

  welcome: () => api.get<WelcomeData>(`${V}/welcome`),
  saveWelcome: (values: Record<string, unknown>) => api.post<{ ok: true }>(`${V}/welcome`, values),
  saveWelcomeWithFile: (values: Record<string, unknown>, file: PickedFile) => api.upload<{ ok: true }>(`${V}/welcome`, toFormData(values, file, "cv_file")),
  skipWelcome: () => api.post<{ ok: true }>(`${V}/welcome/skip`),

  importData: (file: PickedFile, preview: boolean) => {
    const form = new FormData();
    form.append("file", filePart(file));
    return api.upload<DataImportReport>(`${V}/account/import${preview ? "?preview=1" : ""}`, form);
  },
};
