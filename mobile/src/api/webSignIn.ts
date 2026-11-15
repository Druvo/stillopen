// Sign in through the website's own page (Google, GitHub, Facebook, Clerk or a password) instead of typing a password into the app.
// The app keeps a secret (the verifier) in secure storage, opens the sign-in page in the phone's browser with only its SHA-256 (the
// challenge), and the website hands back a one-time code through a stillopen://auth link. The code alone is useless: it is traded for a token
// together with the verifier. See tracker/views_mobilesignin.py.
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Linking } from "react-native";

import { API_BASE } from "./client";

const VERIFIER_KEY = "stillopen_signin_verifier";

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function openWebSignIn(): Promise<void> {
  const verifier = hex(Crypto.getRandomBytes(32));
  await SecureStore.setItemAsync(VERIFIER_KEY, verifier);
  const challenge = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier);
  await Linking.openURL(`${API_BASE}/auth/mobile/start/?challenge=${challenge}`);
}

/** Trade the one-time code from the link for an access token, using the secret this phone kept. */
export async function finishWebSignIn(code: string): Promise<string> {
  const verifier = await SecureStore.getItemAsync(VERIFIER_KEY);
  await SecureStore.deleteItemAsync(VERIFIER_KEY); // one try per start
  if (!verifier) throw new Error("This sign-in did not start in the app. Tap the sign-in button in the app and try again.");
  const response = await fetch(`${API_BASE}/auth/mobile/exchange/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, verifier }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || typeof body.token !== "string") throw new Error(body.error || "Signing in did not work. Please try again.");
  return body.token;
}
