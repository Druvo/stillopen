import React from "react";
import { View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import type { Job } from "../../api/dashboard";
import { Text, useTheme } from "../../ui";

/** How well the job matches: a ring filled to the percent, with the number inside and the band's name under it, so colour is never the only clue. */
export function MatchRing({ job, showBand = true }: { job: Pick<Job, "percent" | "band">; showBand?: boolean }) {
  const { colors } = useTheme();
  if (job.percent === null) {
    return (
      <View
        style={{ width: 58, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border, borderRadius: 10, paddingVertical: 6, paddingHorizontal: 2, alignItems: "center" }}
        accessibilityLabel="Fit not checked yet"
      >
        <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: "center", lineHeight: 13 }}>Not checked yet</Text>
      </View>
    );
  }
  const size = 48;
  const r = 18;
  const c = 2 * Math.PI * r;
  const color = job.band?.color ?? colors.accent;
  return (
    <View style={{ width: 58, alignItems: "center" }} accessible accessibilityLabel={`${job.percent}% match${job.band ? `, ${job.band.label}` : ""}`}>
      <View style={{ width: size, height: size }}>
        <Svg width={size} height={size} viewBox="0 0 44 44" style={{ transform: [{ rotate: "-90deg" }] }}>
          <Circle cx="22" cy="22" r={r} fill="none" strokeWidth={4} stroke={colors.border} />
          <Circle cx="22" cy="22" r={r} fill="none" strokeWidth={4} strokeLinecap="round" stroke={color} strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, job.percent) / 100)} />
        </Svg>
        <View style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 0, alignItems: "center", justifyContent: "center" }}>
          <Text style={{ fontSize: 12, fontWeight: "700" }}>{job.percent}%</Text>
        </View>
      </View>
      {showBand && job.band ? <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: 2 }}>{job.band.label}</Text> : null}
    </View>
  );
}
