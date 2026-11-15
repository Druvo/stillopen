import { useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { accountApi, type PickedFile, type WelcomeData } from "../../api/account";
import { Button, Card, ErrorBox, Field, Loading, Muted, notify, Screen, Toggle } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { addRole, CV_FILE_HINT, pickCvFile, SuggestRoles } from "./ProfileParts";

export default function WelcomeScreen() {
  const { data, error, loading, reload } = useLoad(() => accountApi.welcome());
  return (
    <Screen title="Welcome to StillOpen">
      {loading ? <Loading /> : error && !data ? <ErrorBox message={error} onRetry={reload} /> : data ? <WelcomeForm data={data} /> : null}
    </Screen>
  );
}

function WelcomeForm({ data }: { data: WelcomeData }) {
  const router = useRouter();
  const [values, setValues] = useState({
    target_roles: data.target_roles, home_country: data.home_country, open_remote: data.open_remote, other_places: data.other_places, profile_cv: data.profile_cv,
  });
  const [file, setFile] = useState<PickedFile | null>(null);
  const save = useAction();
  const skip = useAction();
  const set = (key: keyof typeof values, value: string | boolean) => setValues((v) => ({ ...v, [key]: value }));
  const fieldError = (key: string) => save.fields?.[key];

  const submit = async () => {
    const ok = await save.run(() => (file ? accountApi.saveWelcomeWithFile({ ...values }, file) : accountApi.saveWelcome({ ...values })));
    if (!ok) return;
    notify("Lovely, that helps.", "We are searching for jobs that fit you now; they will appear on your dashboard in a minute.");
    router.replace("/");
  };
  const leave = async () => {
    const ok = await skip.run(() => accountApi.skipWelcome());
    if (ok) router.replace("/");
  };

  return (
    <>
      <Muted style={{ marginBottom: 12 }}>Three quick questions so your first matches fit you. Everything can be changed later in your profile.</Muted>
      <Card>
        <Field
          label="What kind of work are you looking for?"
          hint="One role per line. It is fine to be rough, you can change it any time."
          multiline
          placeholder={"Senior Backend Engineer\nSolutions Architect"}
          value={values.target_roles}
          onChangeText={(v) => set("target_roles", v)}
          error={fieldError("target_roles")}
        />
        <SuggestRoles cv={values.profile_cv} roles={values.target_roles} onAddRole={(role) => set("target_roles", addRole(values.target_roles, role))} onAddPlace={(place) => set("other_places", addRole(values.other_places, place))} />
        <Field
          label="Where do you live?"
          hint="So we can tell you whether a job is open to someone there. A country name is enough."
         
          value={values.home_country}
          onChangeText={(v) => set("home_country", v)}
          error={fieldError("home_country")}
        />
        <Toggle label="I am happy to work remotely, from anywhere" hint="Switch off if you only want work in a place you name below." value={values.open_remote} onChange={(v) => set("open_remote", v)} />
        <Field
          label="Anywhere else you would work in person?"
          hint="A country like Malaysia, or a region like Gulf or Europe, one per line. Leave it empty to look only where you live, plus remote."
          multiline
          placeholder={"Malaysia\nGulf"}
          value={values.other_places}
          onChangeText={(v) => set("other_places", v)}
          error={fieldError("other_places")}
        />
      </Card>
      <Card>
        <Button
          variant="secondary"
          label={file ? `Chosen: ${file.name}` : "Upload your CV"}
          icon="document-attach-outline"
          onPress={async () => {
            const picked = await pickCvFile();
            if (picked) setFile(picked);
          }}
        />
        <Muted style={{ marginTop: 6, marginBottom: 6 }}>{CV_FILE_HINT.replace("into the box below", "")}</Muted>
        {fieldError("cv_file") ? <Muted>{fieldError("cv_file")}</Muted> : null}
        <Muted style={{ marginBottom: 12 }}>No CV yet? You can build one step by step under CVs after this.</Muted>
        <Field label="Or paste your CV here" multiline style={{ minHeight: 160 }} value={values.profile_cv} onChangeText={(v) => set("profile_cv", v)} error={fieldError("profile_cv")} />
      </Card>
      {save.error ? <ErrorBox message={save.error} /> : null}
      {skip.error ? <ErrorBox message={skip.error} /> : null}
      <Muted style={{ marginBottom: 12 }}>Your answers stay private to you. Nothing is ever sent to an employer, and we never apply for you.</Muted>
      <View style={{ gap: 8 }}>
        <Button label="Save and see my jobs" busy={save.busy} disabled={skip.busy} onPress={submit} />
        <Button variant="ghost" label="Skip for now" busy={skip.busy} disabled={save.busy} onPress={leave} />
      </View>
    </>
  );
}
