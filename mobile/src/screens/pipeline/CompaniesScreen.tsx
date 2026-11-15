import { useRouter, type Href } from "expo-router";
import React from "react";

import { pipelineApi } from "../../api/pipeline";
import { Badge, Empty, ErrorBox, ListItem, Loading, Muted, Screen } from "../../ui";
import { useLoad } from "../../ui/useApi";

export default function CompaniesScreen() {
  const router = useRouter();
  const load = useLoad(() => pipelineApi.companies());
  const rows = load.data?.companies ?? [];
  return (
    <Screen title="Companies" onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !load.data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {load.data ? (
        rows.length === 0 ? (
          <Empty title="No companies yet" hint="Add a job to your tracker and its company will appear here." />
        ) : (
          <>
            <Muted style={{ marginBottom: 12 }}>Every company in your jobs and contacts, with what you know about it in one place.</Muted>
            {rows.map((c) => (
              <ListItem
                key={c.key}
                title={c.name}
                subtitle={`${c.jobs} ${c.jobs === 1 ? "job" : "jobs"} · ${c.contacts} ${c.contacts === 1 ? "contact" : "contacts"}`}
                right={c.watched ? <Badge label="Watching" /> : undefined}
                onPress={() => router.push(`/companies/${encodeURIComponent(c.name)}` as Href)}
              />
            ))}
          </>
        )
      ) : null}
    </Screen>
  );
}
