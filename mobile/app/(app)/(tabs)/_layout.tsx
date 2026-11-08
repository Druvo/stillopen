import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";
import React from "react";

import { useTheme } from "../../../src/context/ThemeContext";

type Icon = React.ComponentProps<typeof Ionicons>["name"];
const icon = (name: Icon, focused: Icon) => ({ color, focused: f, size }: { color: import("react-native").ColorValue; focused: boolean; size: number }) => <Ionicons name={f ? focused : name} size={size} color={color as string} />;

export default function TabsLayout() {
  const { colors } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerTitleStyle: { fontFamily: "AlbertSans_700Bold" },
        headerShadowVisible: false,
        tabBarLabelStyle: { fontFamily: "AlbertSans_600SemiBold" },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textMuted,
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Home", tabBarIcon: icon("home-outline", "home") }} />
      <Tabs.Screen name="postings" options={{ title: "Postings", tabBarIcon: icon("search-outline", "search") }} />
      <Tabs.Screen name="cv/index" options={{ title: "CVs", tabBarIcon: icon("document-text-outline", "document-text") }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: icon("menu-outline", "menu") }} />
    </Tabs>
  );
}
