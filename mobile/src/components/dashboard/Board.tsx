import React from "react";
import { ScrollView, useWindowDimensions, View } from "react-native";

import type { Bucket, Job, StatusInfo } from "../../api/dashboard";
import { jobsByBucket } from "../../screens/dashboard/logic";
import { radius } from "../../theme";
import { Text, useTheme } from "../../ui";
import { JobCard, type CardExtras } from "./JobCard";

/** The status columns side by side; swipe sideways to move between them. Change a job's stage from the status button on its card. */
export function Board({
  buckets, jobs, statuses, extras, onMove, onCheckFit, checkingId,
}: {
  buckets: Bucket[];
  jobs: Job[];
  statuses: StatusInfo[];
  extras: CardExtras;
  onMove: (job: Job, statusId: number) => void;
  onCheckFit: (job: Job) => void;
  checkingId: number | null;
}) {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const colWidth = Math.min(width - 48, 380);
  const by = jobsByBucket(jobs, buckets);
  return (
    <ScrollView horizontal snapToInterval={colWidth + 10} decelerationRate="fast" showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingRight: 16 }} nestedScrollEnabled>
      {buckets.map((b) => {
        const list = by[b.key] ?? [];
        return (
          <View key={b.key} style={{ width: colWidth, backgroundColor: colors.surfaceAlt, borderRadius: radius.card, padding: 10 }} accessibilityLabel={`${b.label}, ${list.length} jobs`}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 8, paddingHorizontal: 4 }}>
              <Text style={{ fontWeight: "700" }}>{b.label}</Text>
              <Text style={{ color: colors.textMuted }}>{list.length}</Text>
            </View>
            {list.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 13, padding: 8 }}>Nothing here right now.</Text> : null}
            {list.map((job) => (
              <JobCard key={job.id} job={job} compact statuses={statuses} extras={extras} onMove={onMove} onCheckFit={onCheckFit} checking={checkingId === job.id} />
            ))}
          </View>
        );
      })}
    </ScrollView>
  );
}
