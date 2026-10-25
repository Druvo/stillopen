"use client";

import { QueryClient, type Query } from "@tanstack/react-query";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { PersistQueryClientProvider, persistQueryClientSave, type Persister } from "@tanstack/react-query-persist-client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMe } from "@/lib/me";
import { cacheBuster, CACHE_KEY, MAX_AGE_MS, readUid, shouldPersistKey, tabStorage, trimToLimit, writeUid } from "@/lib/persist";

/** The build-time render has no browser: a persister that keeps nothing. */
const NO_PERSISTER: Persister = { persistClient: () => undefined, restoreClient: async () => undefined, removeClient: () => undefined };

/** Notices who is signed in: a different person than the cache was made for loses it, and the cache starts being kept once the id is known. */
function Identity({ uid, setUid, client, persister }: { uid: number | null; setUid: (id: number) => void; client: QueryClient; persister: Persister }) {
  const me = useMe();
  const id = me.data?.id ?? null;
  useEffect(() => {
    if (id === null || id === uid) return;
    if (uid !== null) client.clear(); // another person in this tab: nothing of the last one stays
    writeUid(tabStorage(), id);
    setUid(id);
  }, [id, uid, client, setUid]);
  useEffect(() => {
    // The id just became known: write the cache now, so the very next reload already has something to show.
    if (uid !== null) {
      void persistQueryClientSave({ queryClient: client, persister, buster: cacheBuster(uid), dehydrateOptions: dehydrateOptions(uid) });
    }
  }, [uid, client, persister]);
  return null;
}

function dehydrateOptions(uid: number | null) {
  return {
    shouldDehydrateQuery: (q: Query) => uid !== null && q.state.status === "success" && shouldPersistKey(q.queryKey),
    shouldDehydrateMutation: () => false, // actions are never cached
  };
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        // gcTime must outlast the stored cache or restored answers would be dropped as unused.
        defaultOptions: { queries: { staleTime: 30_000, gcTime: MAX_AGE_MS, refetchOnWindowFocus: false, retry: 1 } },
      }),
  );
  const [persister] = useState<Persister>(() => {
    const storage = tabStorage();
    return storage ? createSyncStoragePersister({ storage, key: CACHE_KEY, throttleTime: 300, serialize: (c) => JSON.stringify(trimToLimit(c)) }) : NO_PERSISTER;
  });
  const [uid, setUidState] = useState<number | null>(() => readUid(tabStorage()));
  const uidRef = useRef(uid);
  const setUid = useCallback((id: number) => {
    uidRef.current = id;
    setUidState(id);
  }, []);
  const persistOptions = useMemo(
    () => ({
      persister,
      maxAge: MAX_AGE_MS,
      buster: cacheBuster(uid),
      // Reads the id when the cache is written, so a cache never goes out before the person is known.
      dehydrateOptions: { shouldDehydrateQuery: (q: Query) => dehydrateOptions(uidRef.current).shouldDehydrateQuery(q), shouldDehydrateMutation: () => false },
    }),
    [persister, uid],
  );
  return (
    <PersistQueryClientProvider
      client={client}
      persistOptions={persistOptions}
      // What was painted from the saved copy is out of date by definition: fetch the current answers behind it (without cancelling a fetch already going).
      onSuccess={() => void client.invalidateQueries(undefined, { cancelRefetch: false })}
    >
      <Identity uid={uid} setUid={setUid} client={client} persister={persister} />
      {children}
    </PersistQueryClientProvider>
  );
}
