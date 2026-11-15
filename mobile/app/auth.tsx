import { Redirect, useLocalSearchParams } from "expo-router";
import React, { useEffect, useRef, useState } from "react";

import { finishWebSignIn } from "../src/api/webSignIn";
import { useAuth } from "../src/context/AuthContext";
import { Loading } from "../src/ui";

// stillopen://auth?code=... : where the website sends the person back after they signed in on its own page.
export default function Auth() {
  const { code } = useLocalSearchParams<{ code?: string }>();
  const { completeSignIn, signedIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current || typeof code !== "string") return;
    started.current = true;
    finishWebSignIn(code)
      .then(completeSignIn)
      .catch((e: Error) => setError(e.message));
  }, [code, completeSignIn]);

  if (signedIn) return <Redirect href="/" />;
  if (error || typeof code !== "string") return <Redirect href={{ pathname: "/login", params: { notice: error ?? "That sign-in link is not valid. Please try again." } }} />;
  return <Loading />;
}
