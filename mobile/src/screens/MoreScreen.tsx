import { useRouter, type Href } from "expo-router";
import React from "react";

import { NAV } from "../nav";
import { ListItem, Screen, SectionTitle } from "../ui";
import { useAuth } from "../context/AuthContext";

export default function MoreScreen() {
  const router = useRouter();
  const { me } = useAuth();
  return (
    <Screen title="More">
      {NAV.map((group) => (
        <React.Fragment key={group.title}>
          <SectionTitle>{group.title}</SectionTitle>
          {group.items
            .filter((item) => !item.needs || me?.[item.needs] !== false)
            .map((item) => (
              <ListItem key={item.to} title={item.label} icon={item.icon} onPress={() => router.push(item.to as Href)} />
            ))}
        </React.Fragment>
      ))}
    </Screen>
  );
}
