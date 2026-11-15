import { useLocalSearchParams } from "expo-router";
import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, TouchableOpacity, View } from "react-native";

import { API_BASE, normalizeServer, setApiBase } from "../api/client";
import { openWebSignIn } from "../api/webSignIn";
import { useAuth } from "../context/AuthContext";
import { Button, Field, Heading, Muted, Text, useTheme } from "../ui";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const { notice } = useLocalSearchParams<{ notice?: string }>();
  const { colors } = useTheme();
  const [server, setServer] = useState(API_BASE);
  const [editingServer, setEditingServer] = useState(!API_BASE);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setServer(API_BASE);
    setEditingServer(!API_BASE);
  }, []);

  const submit = async () => {
    setError(null);
    if (!(await setApiBase(server))) {
      setError("That server address does not look right. It should start with https:// and be the address you use for StillOpen in a browser.");
      setEditingServer(true);
      return;
    }
    setServer(normalizeServer(server) ?? server);
    setBusy(true);
    try {
      await signIn(username.trim(), password);
    } catch (err: any) {
      setError(err?.message === "Network request failed" ? "Could not reach that server. Check the address and your connection." : (err?.message ?? "Could not sign in."));
    } finally {
      setBusy(false);
    }
  };

  const viaWebsite = async () => {
    setError(null);
    if (!(await setApiBase(server))) {
      setError("That server address does not look right. It should start with https:// and be the address you use for StillOpen in a browser.");
      setEditingServer(true);
      return;
    }
    try {
      await openWebSignIn();
    } catch {
      setError("Could not open the sign-in page. Check your connection and try again.");
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.background }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: 24 }} keyboardShouldPersistTaps="handled">
        <View style={{ marginBottom: 28 }}>
          <Heading style={{ fontSize: 34 }}>StillOpen</Heading>
          <Muted>Your job search, in one calm place.</Muted>
        </View>

        {editingServer ? (
          <Field
            label="Your StillOpen address"
            value={server}
            onChangeText={setServer}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="https://jobs.example.com"
            hint="The address you open in a browser to use StillOpen."
          />
        ) : (
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <Muted>Signing in to {server.replace(/^https?:\/\//, "")}</Muted>
            <TouchableOpacity onPress={() => setEditingServer(true)} accessibilityRole="button" accessibilityLabel="Change server">
              <Text style={{ color: colors.accent, fontWeight: "600" }}>Change</Text>
            </TouchableOpacity>
          </View>
        )}

        <Field label="Username or email" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />

        {error || notice ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{error ?? notice}</Text> : null}

        <Button label="Sign in" onPress={submit} busy={busy} disabled={!server || !username || !password} />

        <View style={{ flexDirection: "row", alignItems: "center", marginVertical: 18, gap: 10 }}>
          <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
          <Muted>or</Muted>
          <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
        </View>
        <Button label="Sign in with Google, GitHub or Facebook" variant="secondary" icon="open-outline" onPress={viaWebsite} disabled={!server} />
        <Muted style={{ marginTop: 8, textAlign: "center" }}>Opens the website's sign-in page in your browser, then brings you back here.</Muted>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
