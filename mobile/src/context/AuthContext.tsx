import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getToken, setToken as persistToken } from "../api/client";
import * as endpoints from "../api/endpoints";
import type { Me } from "../api/types";

interface AuthState {
  loading: boolean; // still checking for a stored token
  signedIn: boolean;
  me: Me | null;
  error: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshMe = useCallback(async () => {
    const data = await endpoints.getMe();
    setMe(data);
  }, []);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      if (token) {
        try {
          await refreshMe();
          setSignedIn(true);
        } catch {
          setSignedIn(false); // a stale/revoked token: client.ts already cleared it
        }
      }
      setLoading(false);
    })();
  }, [refreshMe]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      setError(null);
      try {
        const result = await endpoints.login(username, password);
        await persistToken(result.token);
        await refreshMe();
        setSignedIn(true);
      } catch (err: any) {
        setError(err?.message ?? "Could not sign in.");
        throw err;
      }
    },
    [refreshMe],
  );

  const signOut = useCallback(async () => {
    try {
      await endpoints.logout();
    } catch {
      // the token may already be gone server-side; sign out locally regardless
    }
    await persistToken(null);
    setMe(null);
    setSignedIn(false);
  }, []);

  const value = useMemo(() => ({ loading, signedIn, me, error, signIn, signOut, refreshMe }), [loading, signedIn, me, error, signIn, signOut, refreshMe]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
