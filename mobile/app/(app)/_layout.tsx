import { Stack } from "expo-router";
import React from "react";

import { colors } from "../../src/theme";

// Every screen after sign-in. Screens set their own header title through <Screen title="...">.
export default function AppLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
    </Stack>
  );
}
