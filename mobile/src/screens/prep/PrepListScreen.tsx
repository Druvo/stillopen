import { useRouter } from "expo-router";
import React from "react";

import { ApiError } from "../../api/client";
import { prepApi } from "../../api/prep";
import { Badge, Empty, ErrorBox, ListItem, Loading, Muted, Screen } from "../../ui";
import { useLoad } from "../../ui/useApi";

/** The site's admin can switch prep plans off; the API then answers 404 for every prep route. */
export const PREP_OFF_TITLE = "Prep plans are turned off";
export const PREP_OFF_HINT = "The site you use has switched prep plans off. Ask whoever runs it if you need them.";

export default function PrepListScreen() {
  const router = useRouter();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(async () => {
    try {
      return { off: false, plans: (await prepApi.list()).plans };
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return { off: true, plans: [] };
      throw e;
    }
  });

  return (
    <Screen title="Prep plans" onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : error && !data ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : data?.off ? (
        <Empty title={PREP_OFF_TITLE} hint={PREP_OFF_HINT} />
      ) : (
        <>
          <Muted style={{ marginBottom: 14 }}>
            A prep plan is a short study plan that closes the gaps a job showed: a few weeks of lessons with links to the official documentation, and quiz questions that cite their source. It is written
            from your CV and the job by your own AI account, and nothing starts until you have read it and said yes.
          </Muted>
          {data && data.plans.length === 0 ? (
            <Empty
              title="No prep plans yet"
              hint="Check how well a job fits you on your dashboard. If it shows skills you are missing, press Prepare on its card."
              action={{ label: "Go to my dashboard", onPress: () => router.push("/" as never) }}
            />
          ) : (
            data?.plans.map((plan) => (
              <ListItem
                key={plan.id}
                icon="school-outline"
                title={plan.title || "Prep plan"}
                subtitle={`${plan.job ? `For ${plan.job.role} at ${plan.job.company} · ` : ""}${plan.status_label}${plan.lessons_total ? ` · ${plan.lessons_done} of ${plan.lessons_total} lessons done` : ""}`}
                right={plan.status === "draft" ? <Badge label="Review the draft" /> : undefined}
                onPress={() => router.push(`/prep/${plan.id}` as never)}
              />
            ))
          )}
        </>
      )}
    </Screen>
  );
}
