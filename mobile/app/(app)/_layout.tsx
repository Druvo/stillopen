import { Stack } from "expo-router";
import React from "react";

import { useTheme } from "../../src/context/ThemeContext";

// Every screen after sign-in. Screens set their own header title through <Screen title="...">.
export default function AppLayout() {
  const { colors } = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerTitleStyle: { fontFamily: "AlbertSans_700Bold" },
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
    </Stack>
  );
}
