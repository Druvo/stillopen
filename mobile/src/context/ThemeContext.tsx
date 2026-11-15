import {
  AlbertSans_400Regular,
  AlbertSans_500Medium,
  AlbertSans_600SemiBold,
  AlbertSans_700Bold,
  AlbertSans_800ExtraBold,
  useFonts,
} from "@expo-google-fonts/albert-sans";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { StyleSheet } from "react-native";

import { api } from "../api/client";
import { palettes, type Mode, type Palette } from "../theme";

type ThemeState = { colors: Palette; mode: Mode; setMode: (mode: Mode) => Promise<void>; fontsReady: boolean };

const ThemeContext = createContext<ThemeState>({ colors: palettes.dark, mode: "dark", setMode: async () => {}, fontsReady: false });

export function ThemeProvider({ children, signedIn }: { children: React.ReactNode; signedIn: boolean }) {
  const [mode, setModeState] = useState<Mode>("dark");
  const [loaded] = useFonts({ AlbertSans_400Regular, AlbertSans_500Medium, AlbertSans_600SemiBold, AlbertSans_700Bold, AlbertSans_800ExtraBold });

  // The person's own choice (saved with their other layout preferences) wins; until it is read, or when signed out, dark.
  useEffect(() => {
    if (!signedIn) return;
    api
      .get<{ preferences?: { theme?: string }; theme?: string }>("/api/v1/preferences")
      .then((p) => {
        const theme = p.preferences?.theme ?? p.theme;
        if (theme === "light" || theme === "dark") setModeState(theme);
      })
      .catch(() => {});
  }, [signedIn]);

  const setMode = useCallback(async (next: Mode) => {
    setModeState(next);
    try {
      await api.put("/api/v1/preferences", { theme: next });
    } catch {
      // the choice still applies on this phone for now
    }
  }, []);

  const value = useMemo(() => ({ colors: palettes[mode], mode, setMode, fontsReady: loaded }), [mode, setMode, loaded]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

/** Styles that follow the theme: `const s = useStyles((c) => ({ box: { backgroundColor: c.surface } }))`. */
export function useStyles<T extends Record<string, object>>(make: (colors: Palette) => T): T {
  const { colors } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => StyleSheet.create(make(colors) as never) as unknown as T, [colors]);
}
