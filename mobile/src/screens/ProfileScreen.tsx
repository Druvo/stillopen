import React from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";

export default function ProfileScreen() {
  const { me, signOut } = useAuth();

  const confirmSignOut = () => {
    Alert.alert("Sign out?", undefined, [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: () => signOut() },
    ]);
  };

  return (
    <View style={styles.container}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{(me?.name ?? "?").charAt(0).toUpperCase()}</Text>
      </View>
      <Text style={styles.name}>{me?.name}</Text>
      <Text style={styles.email}>{me?.email}</Text>

      <TouchableOpacity style={styles.signOutButton} onPress={confirmSignOut}>
        <Text style={styles.signOutText}>Sign out</Text>
      </TouchableOpacity>

      <Text style={styles.note}>
        Full profile editing (roles, places, CV text, notification settings) isn't built yet here -- use the
        website for those for now.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, padding: 24, alignItems: "center", paddingTop: 48 },
  avatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center", marginBottom: 16 },
  avatarText: { fontSize: 28, fontWeight: "700", color: "#0a0e07" },
  name: { fontSize: 20, fontWeight: "700", color: colors.text },
  email: { color: colors.textMuted, marginTop: 4 },
  signOutButton: { marginTop: 32, backgroundColor: colors.surface, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 32 },
  signOutText: { color: colors.danger, fontWeight: "700" },
  note: { color: colors.textMuted, marginTop: 40, textAlign: "center", fontSize: 13, lineHeight: 18 },
});
