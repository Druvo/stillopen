// Extra, named lists of roles searched alongside the roles on the person's profile.
import React, { useState } from "react";
import { View } from "react-native";

import { sourcesApi } from "../../api/jobs";
import { Badge, Button, Card, ErrorBox, Field, Loading, Muted, Screen, SectionTitle, Text, confirm, notify, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";

export default function SavedSearchesScreen() {
  const { colors } = useTheme();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => sourcesApi.savedSearches(), []);
  const [name, setName] = useState("");
  const [roles, setRoles] = useState("");
  const form = useAction();
  const row = useAction();

  const add = async () => {
    const r = await form.run(() => sourcesApi.addSavedSearch({ name, target_roles: roles }));
    if (r) {
      notify(`Saved "${name}".`);
      setName("");
      setRoles("");
      await reload();
    }
  };

  return (
    <Screen title="Saved searches" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>
        Extra, named lists of roles searched alongside the roles on your profile, such as "Remote Backend Roles". Each is included in your search while it is on; turn one off without losing it.
      </Muted>
      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 8 }}>Add a saved search</Text>
        <Field label="Name" value={name} onChangeText={setName} hint="A short name for this search." error={form.fields?.name} />
        <Field
          label="Roles (one per line)"
          value={roles}
          onChangeText={setRoles}
          multiline
          placeholder={"Senior Backend Engineer\nSolutions Architect"}
          error={form.fields?.target_roles}
        />
        {form.error && !form.fields ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{form.error}</Text> : null}
        <Button label="Save search" busy={form.busy} onPress={add} />
        <Muted style={{ marginTop: 6 }}>You can have up to 10.</Muted>
      </Card>

      <SectionTitle>Your saved searches</SectionTitle>
      {row.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{row.error}</Text> : null}
      {loading ? <Loading /> : null}
      {error ? <ErrorBox message={error} onRetry={reload} /> : null}
      {data && data.saved_searches.length === 0 ? <Muted>None yet. Your profile's own roles are still searched either way.</Muted> : null}
      {data?.saved_searches.map((s) => (
        <Card key={s.id}>
          <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Text style={{ fontWeight: "700" }}>{s.name}</Text>
            {!s.enabled ? <Badge label="off" color={colors.warn} /> : null}
          </View>
          <Muted style={{ marginTop: 4 }}>{s.target_roles}</Muted>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
            <Button
              label={s.enabled ? "Turn off" : "Turn on"}
              variant="secondary"
              disabled={row.busy}
              onPress={async () => {
                if (await row.run(() => sourcesApi.toggleSavedSearch(s.id, !s.enabled))) await reload();
              }}
            />
            <Button
              label="Delete"
              variant="danger"
              disabled={row.busy}
              onPress={async () => {
                if (!(await confirm(`Delete "${s.name}"?`, "This cannot be undone."))) return;
                if (await row.run(() => sourcesApi.removeSavedSearch(s.id))) {
                  notify("Deleted.");
                  await reload();
                }
              }}
            />
          </View>
        </Card>
      ))}
    </Screen>
  );
}
