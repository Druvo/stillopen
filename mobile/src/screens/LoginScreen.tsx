import React, { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      await signIn(username.trim(), password);
    } catch (err: any) {
      setError(err?.message ?? "Could not sign in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Text style={styles.title}>StillOpen</Text>
      <Text style={styles.subtitle}>Your job search, in one calm place.</Text>

      <TextInput
        style={styles.input}
        placeholder="Username or email"
        placeholderTextColor={colors.textMuted}
        autoCapitalize="none"
        autoCorrect={false}
        value={username}
        onChangeText={setUsername}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor={colors.textMuted}
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <TouchableOpacity style={styles.button} onPress={submit} disabled={busy || !username || !password}>
        {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.buttonText}>Sign in</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: 24, backgroundColor: colors.background },
  title: { fontSize: 32, fontWeight: "700", color: colors.text, marginBottom: 4 },
  subtitle: { fontSize: 15, color: colors.textMuted, marginBottom: 32 },
  input: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 14,
    color: colors.text,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  button: { backgroundColor: colors.accent, borderRadius: 10, paddingVertical: 14, alignItems: "center", marginTop: 12 },
  buttonText: { color: "#0a0e07", fontWeight: "700", fontSize: 16 },
  error: { color: colors.danger, marginBottom: 8 },
});
