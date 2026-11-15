import { useRouter, type Href } from "expo-router";
import React from "react";

import { NAV } from "../nav";
import { Badge, ListItem, Screen, SectionTitle, useTheme } from "../ui";
import { useUnread } from "../components/account/useUnread";
import { useAuth } from "../context/AuthContext";

export default function MoreScreen() {
  const router = useRouter();
  const { me } = useAuth();
  const { colors } = useTheme();
  const unread = useUnread();
  return (
    <Screen title="More">
      {NAV.map((group) => (
        <React.Fragment key={group.title}>
          <SectionTitle>{group.title}</SectionTitle>
          {group.items
            .filter((item) => !item.needs || me?.[item.needs] !== false)
            .map((item) => (
              <ListItem
                key={item.to}
                title={item.label}
                icon={item.icon}
                right={item.to === "/notifications" && unread > 0 ? <Badge label={unread > 9 ? "9+" : String(unread)} color={colors.accent} /> : undefined}
                onPress={() => router.push(item.to as Href)}
              />
            ))}
        </React.Fragment>
      ))}
    </Screen>
  );
}
