// Pieces of the profile and welcome screens: CV file picking, role suggestions, the strength meter, search areas, display choices, goals and time zone.
import * as DocumentPicker from "expo-document-picker";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { accountApi, type Area, type AreaValues, type Choice, type Preferences, type ProfileData, type Strength, type Suggestions, type PickedFile } from "../../api/account";
import { Button, Card, Chip, Choice as ChoiceRow, confirm, ErrorBox, Field, Muted, Text, Toggle, useTheme } from "../../ui";
import { useAction } from "../../ui/useApi";
import { addRole, deviceZone, hasRole, isZoneName } from "./format";

/** Opens the phone's file picker for a CV (PDF, .txt or .md, up to 2 MB). The text is read on the server; the file is not kept. */
export async function pickCvFile(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({ type: ["application/pdf", "text/plain", "text/markdown", "*/*"], copyToCacheDirectory: true });
  if (result.canceled || !result.assets[0]) return null;
  const a = result.assets[0];
  return { uri: a.uri, name: a.name, mimeType: a.mimeType, size: a.size };
}

export const CV_FILE_HINT = "PDF, .txt or .md, up to 2 MB. The text is read into the box below; the file itself is not kept.";

/** "Suggest roles from my CV": tapping a role only adds it to the box; the person still saves themselves. */
export function SuggestRoles({ cv, roles, onAddRole, onAddPlace }: { cv: string; roles: string; onAddRole: (role: string) => void; onAddPlace?: (place: string) => void }) {
  const [data, setData] = useState<Suggestions | null>(null);
  const action = useAction();
  const ask = async () => {
    const result = await action.run(() => accountApi.suggestRoles(cv));
    if (result) setData(result);
  };
  return (
    <View style={{ marginBottom: 14 }}>
      <Button variant="secondary" label={action.busy ? "Reading your CV…" : "Suggest roles from my CV"} icon="sparkles-outline" busy={action.busy} onPress={ask} />
      {action.error ? <Muted>{action.error}</Muted> : null}
      {data && data.roles.length === 0 ? <Muted style={{ marginTop: 8 }}>We could not find job titles in your CV. Type the roles you want in the box above, or add your free Google AI Studio key in AI settings for suggestions.</Muted> : null}
      {data && data.roles.length > 0 ? (
        <View style={{ marginTop: 8 }}>
          <Muted>Tap one to add it to the box above. Nothing is saved until you save.</Muted>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            {data.roles.map((role) => {
              const added = hasRole(roles, role);
              return <Chip key={role} label={added ? `✓ ${role}` : `+ ${role}`} selected={added} onPress={added ? undefined : () => onAddRole(role)} />;
            })}
          </View>
        </View>
      ) : null}
      {data && data.places.length > 0 ? (
        <View style={{ marginTop: 8 }}>
          <Muted>{onAddPlace ? "Places your CV mentions (tap to add):" : "Places your CV mentions (add them under where you would work, below):"}</Muted>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            {data.places.map((place) => (
              <Chip key={place} label={onAddPlace ? `+ ${place}` : place} onPress={onAddPlace ? () => onAddPlace(place) : undefined} />
            ))}
          </View>
        </View>
      ) : null}
      {data?.method === "ai" ? <Muted style={{ marginTop: 8 }}>{data.notice}</Muted> : null}
      {data?.method === "rules" && data.roles.length > 0 ? <Muted style={{ marginTop: 8 }}>Read from the job titles in your CV, without AI.</Muted> : null}
    </View>
  );
}

export { addRole };

/** How much of what matching needs is filled in, with the three most useful things still missing. */
export function StrengthMeter({ strength }: { strength: Strength | null }) {
  const { colors } = useTheme();
  if (!strength) return null;
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Profile strength</Text>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginTop: 8 }}>
        <View accessible accessibilityRole="progressbar" accessibilityLabel={`Your profile is ${strength.percent}% ready for matching.`} style={{ flex: 1, height: 10, borderRadius: 5, backgroundColor: colors.accentSoft, overflow: "hidden" }}>
          <View style={{ width: `${strength.percent}%`, height: 10, backgroundColor: colors.accent }} />
        </View>
        <Text style={{ fontWeight: "700" }}>{strength.percent}%</Text>
      </View>
      {strength.complete ? (
        <Muted style={{ marginTop: 8 }}>Everything that matters for matching is filled in.</Muted>
      ) : (
        <View style={{ marginTop: 8 }}>
          <Muted>The most useful things to add next:</Muted>
          {strength.missing.map((m) => (
            <View key={m.key} style={{ marginTop: 6 }}>
              <Text style={{ color: colors.accent, fontWeight: "600" }}>{m.label}</Text>
              <Muted>{m.why}</Muted>
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}

// --- search areas --------------------------------------------------------------------------------

const BLANK_AREA: AreaValues = {
  place: "", city: "", allow_remote: true, allow_hybrid: false, allow_onsite: false, needs_visa_sponsorship: false, needs_relocation_support: false,
  min_salary: "", salary_currency: "", salary_period: "month",
};

function areaToValues(area: Area): AreaValues {
  return {
    place: area.place, city: area.city, allow_remote: area.allow_remote, allow_hybrid: area.allow_hybrid, allow_onsite: area.allow_onsite,
    needs_visa_sponsorship: area.needs_visa_sponsorship, needs_relocation_support: area.needs_relocation_support,
    min_salary: area.min_salary === null ? "" : String(area.min_salary), salary_currency: area.salary_currency, salary_period: area.salary_period,
  };
}

/** An empty minimum pay is `null`, not an empty string. */
function areaPayload(values: AreaValues): Record<string, unknown> {
  return { ...values, min_salary: values.min_salary.trim() === "" ? null : values.min_salary.trim() };
}

export function AreasEditor({ areas: initial, max, periods }: { areas: Area[]; max: number; periods: Choice[] }) {
  const [areas, setAreas] = useState<Area[]>(initial);
  const [drafts, setDrafts] = useState<number[]>([]);
  const [next, setNext] = useState(1);
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Where you would work</Text>
      <Muted style={{ marginVertical: 6 }}>
        One row per place. Say which kinds of work you accept there and what you need from the employer. Jobs are checked against these rows; a job outside them is flagged, never hidden.
      </Muted>
      <Muted style={{ marginBottom: 10 }}>
        Examples: Bangladesh, city Dhaka: on-site, hybrid. Anywhere: remote. Malaysia: on-site, hybrid, only with visa sponsorship. A place can be a country, a region (Gulf, Europe, Southeast Asia) or Anywhere.
      </Muted>
      {areas.length === 0 && drafts.length === 0 ? <Text style={{ marginBottom: 10 }}>You have not added a place yet. Add one so we can tell you which jobs are within reach.</Text> : null}
      {areas.map((area) => (
        <AreaRow key={area.id} area={area} periods={periods} onSaved={(saved) => setAreas((l) => l.map((a) => (a.id === saved.id ? saved : a)))} onRemoved={() => setAreas((l) => l.filter((a) => a.id !== area.id))} />
      ))}
      {drafts.map((key) => (
        <AreaRow
          key={`new-${key}`}
          area={null}
          periods={periods}
          onSaved={(saved) => {
            setAreas((l) => [...l, saved]);
            setDrafts((l) => l.filter((k) => k !== key));
          }}
          onRemoved={() => setDrafts((l) => l.filter((k) => k !== key))}
        />
      ))}
      {areas.length + drafts.length >= max ? (
        <Muted>You can have at most {max} places.</Muted>
      ) : (
        <Button
          variant="secondary"
          label="Add a place"
          icon="add"
          onPress={() => {
            setDrafts((l) => [...l, next]);
            setNext((n) => n + 1);
          }}
        />
      )}
    </Card>
  );
}

function AreaRow({ area, periods, onSaved, onRemoved }: { area: Area | null; periods: Choice[]; onSaved: (a: Area) => void; onRemoved: () => void }) {
  const { colors } = useTheme();
  const [values, setValues] = useState<AreaValues>(area ? areaToValues(area) : BLANK_AREA);
  const [note, setNote] = useState("");
  const [dirty, setDirty] = useState(area === null);
  const action = useAction();
  const set = <K extends keyof AreaValues>(key: K, value: AreaValues[K]) => {
    setDirty(true);
    setNote("");
    setValues((v) => ({ ...v, [key]: value }));
  };
  const save = async () => {
    const payload = areaPayload(values);
    const result = await action.run(() => (area ? accountApi.changeArea(area.id, payload) : accountApi.addArea(payload)));
    if (!result) return;
    setDirty(false);
    setNote(result.warning ?? "Saved.");
    onSaved(result.area);
  };
  const remove = async () => {
    if (area) {
      if (!(await confirm(`Remove ${area.place} from your places?`, undefined, "Remove"))) return;
      const ok = await action.run(() => accountApi.removeArea(area.id));
      if (!ok) return;
    }
    onRemoved();
  };
  return (
    <View style={{ borderWidth: 1, borderColor: action.error ? colors.danger : colors.border, borderRadius: 12, padding: 12, marginBottom: 12 }}>
      <Field label="Place" value={values.place} onChangeText={(v) => set("place", v)} error={action.fields?.place} placeholder="Bangladesh, Gulf, Anywhere" />
      <Field label="City (optional)" value={values.city} onChangeText={(v) => set("city", v)} error={action.fields?.city} />
      <Toggle label="Remote" value={values.allow_remote} onChange={(v) => set("allow_remote", v)} />
      <Toggle label="Hybrid" value={values.allow_hybrid} onChange={(v) => set("allow_hybrid", v)} />
      <Toggle label="On-site" value={values.allow_onsite} onChange={(v) => set("allow_onsite", v)} />
      <Toggle label="Only with visa sponsorship" value={values.needs_visa_sponsorship} onChange={(v) => set("needs_visa_sponsorship", v)} />
      <Toggle label="Only with relocation support" value={values.needs_relocation_support} onChange={(v) => set("needs_relocation_support", v)} />
      <Field label="Minimum pay" keyboardType="numeric" value={values.min_salary} onChangeText={(v) => set("min_salary", v)} error={action.fields?.min_salary} />
      <Field label="Currency" maxLength={3} autoCapitalize="characters" placeholder="USD" value={values.salary_currency} onChangeText={(v) => set("salary_currency", v)} error={action.fields?.salary_currency} />
      <ChoiceRow label="Per" options={periods} value={values.salary_period} onChange={(v) => set("salary_period", v)} />
      {action.error ? <Muted style={{ color: colors.danger }}>{action.error}</Muted> : null}
      {note && !action.error ? <Muted style={{ marginBottom: 8 }}>{note}</Muted> : null}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <Button label={area ? "Save this place" : "Add this place"} busy={action.busy} disabled={!dirty} onPress={save} style={{ flex: 1 }} />
        <Button variant="danger" label={area ? "Remove" : "Cancel"} disabled={action.busy} onPress={remove} />
      </View>
    </View>
  );
}

// --- display, goals, time zone ------------------------------------------------------------------

/** Colour mode, text size and spacing. Saved on the account, so they follow the person to every device. Colours apply at once. */
export function DisplayCard({ prefs, onChange }: { prefs: Preferences; onChange: (patch: Partial<Preferences>) => void }) {
  const { mode, setMode } = useTheme();
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Display</Text>
      <Muted style={{ marginVertical: 6 }}>How StillOpen looks for you. This is saved to your account, so it is the same on your phone and your computer.</Muted>
      <ChoiceRow
        label="Colours"
        options={[
          { value: "light", label: "Light" },
          { value: "dark", label: "Dark" },
        ]}
        value={mode}
        onChange={(v) => void setMode(v)}
      />
      <ChoiceRow
        label="Text size"
        options={[
          { value: "normal", label: "Normal" },
          { value: "large", label: "Large" },
          { value: "larger", label: "Larger" },
        ]}
        value={prefs.text_size}
        onChange={(text_size) => onChange({ text_size })}
      />
      <ChoiceRow
        label="Spacing"
        options={[
          { value: "comfortable", label: "Comfortable" },
          { value: "compact", label: "Compact" },
        ]}
        value={prefs.density}
        onChange={(density) => onChange({ density })}
      />
    </Card>
  );
}

function NumberPref({ label, hint, value, min, max, onSave }: { label: string; hint: string; value: number; min: number; max: number; onSave: (n: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  const n = Number(text);
  const valid = text.trim() !== "" && Number.isInteger(n) && n >= min && n <= max;
  return (
    <Field
      label={label}
      hint={hint}
      keyboardType="numeric"
      value={text}
      error={valid ? undefined : `Enter a whole number from ${min} to ${max}.`}
      onChangeText={(t) => {
        setText(t);
        const m = Number(t);
        if (t.trim() !== "" && Number.isInteger(m) && m >= min && m <= max && m !== value) onSave(m);
      }}
    />
  );
}

export function GoalsCard({ prefs, onChange }: { prefs: Preferences; onChange: (patch: Partial<Preferences>) => void }) {
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Reminders and goals</Text>
      <Muted style={{ marginVertical: 6 }}>Both are your choice. Goals are off until you set a number, and nothing here is shared or sent to anyone.</Muted>
      <NumberPref label="Call an application quiet after (days)" hint="Applications with no reply for this long show up under Worth a look next. From 3 to 30." value={prefs.quiet_days} min={3} max={30} onSave={(quiet_days) => onChange({ quiet_days })} />
      <NumberPref label="Applications I would like to send each day" hint="0 turns the daily goal off." value={prefs.goal_daily} min={0} max={50} onSave={(goal_daily) => onChange({ goal_daily })} />
      <NumberPref label="Applications I would like to send each week" hint="Counted over the last 7 days. 0 turns the weekly goal off." value={prefs.goal_weekly} min={0} max={200} onSave={(goal_weekly) => onChange({ goal_weekly })} />
    </Card>
  );
}

/** Time zone: your day starts at your midnight. Empty means the site's zone. Saved on its own, so it never needs the rest of the profile to be valid. */
export function TimeZoneCard({ data, onSaved }: { data: ProfileData; onSaved: (next: ProfileData) => void }) {
  const [value, setValue] = useState(data.profile.timezone);
  const [message, setMessage] = useState("");
  const action = useAction();
  const device = deviceZone();
  const unknown = value.trim() !== "" && !isZoneName(value.trim());
  const save = async (zone: string) => {
    const next = await action.run(() => accountApi.saveProfile({ timezone: zone.trim() }));
    if (!next) return;
    onSaved(next);
    setValue(next.profile.timezone);
    setMessage(next.profile.timezone ? `Time zone set to ${next.profile.timezone}.` : "Using the site's time zone.");
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Time zone</Text>
      <Muted style={{ marginVertical: 6 }}>
        Your day starts at your midnight: what counts as today, your practice streak, follow-ups and &ldquo;due in 3 days&rdquo;. Leave it empty to use the site&apos;s ({data.site.timezone}).
      </Muted>
      <Field
        label="Time zone"
        value={value}
        onChangeText={(v) => {
          setValue(v);
          setMessage("");
        }}
        placeholder={`${data.site.timezone} (the site's)`}
        autoCapitalize="none"
        autoCorrect={false}
        error={unknown ? "That is not a time zone we know. Type a city like Asia/Dhaka or America/Los_Angeles." : action.fields?.timezone}
        hint="For example Asia/Dhaka."
      />
      {action.error && !action.fields?.timezone ? <ErrorBox message={action.error} /> : null}
      {message ? <Muted style={{ marginBottom: 8 }}>{message}</Muted> : null}
      <View style={{ gap: 8 }}>
        <Button label="Save time zone" busy={action.busy} disabled={unknown || value === data.profile.timezone} onPress={() => save(value)} />
        {device ? (
          <Button
            variant="secondary"
            label={`Use this phone's time zone (${device})`}
            disabled={action.busy}
            onPress={() => {
              setValue(device);
              void save(device);
            }}
          />
        ) : null}
      </View>
    </Card>
  );
}
