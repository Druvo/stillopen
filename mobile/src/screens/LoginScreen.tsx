import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, View } from "react-native";

import { useAuth } from "../context/AuthContext";
import { Button, Field, Heading, Muted, Text, useTheme } from "../ui";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const { colors } = useTheme();
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
    <KeyboardAvoidingView style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: colors.background }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={{ marginBottom: 28 }}>
        <Heading style={{ fontSize: 34 }}>StillOpen</Heading>
        <Muted>Your job search, in one calm place.</Muted>
      </View>

      <Field label="Username or email" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />

      {error ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{error}</Text> : null}

      <Button label="Sign in" onPress={submit} busy={busy} disabled={!username || !password} />
    </KeyboardAvoidingView>
  );
}
