import { Redirect, useLocalSearchParams } from "expo-router";
import React, { useEffect, useState } from "react";

import { setApiBase } from "../src/api/client";
import { Loading } from "../src/ui";

// stillopen://connect?server=https://jobs.example.com : opened from the "Get the app" page of a person's own server.
export default function Connect() {
  const { server } = useLocalSearchParams<{ server?: string }>();
  const [done, setDone] = useState(false);
  useEffect(() => {
    (async () => {
      if (typeof server === "string") await setApiBase(server);
      setDone(true);
    })();
  }, [server]);
  return done ? <Redirect href="/login" /> : <Loading />;
}
