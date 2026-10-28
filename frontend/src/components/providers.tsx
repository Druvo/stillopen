"use client";

import { QueryClient, useIsRestoring, type Query } from "@tanstack/react-query";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { PersistQueryClientProvider, persistQueryClientSave, type Persister } from "@tanstack/react-query-persist-client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMe } from "@/lib/me";
import { cacheBuster, CACHE_KEY, guardedStorage, MAX_AGE_MS, readUid, shouldPersistKey, tabStorage, trimToLimit, writeUid } from "@/lib/persist";

/** The build-time render has no browser: a persister that keeps nothing. */
const NO_PERSISTER: Persister = { persistClient: () => undefined, restoreClient: async () => undefined, removeClient: () => undefined };

/** Notices who is signed in: a different person than the cache was made for loses it, and the cache starts being kept once the id is known. */
function Identity({ uid, setUid, client, persister }: { uid: number | null; setUid: (id: number) => void; client: QueryClient; persister: Persister }) {
  const me = useMe();
  const id = me.data?.id ?? null;
  const restoring = useIsRestoring();
  useEffect(() => {
    if (id === null || id === uid) return;
    if (uid !== null) client.clear(); // another person in this tab: nothing of the last one stays
    writeUid(tabStorage(), id);
    setUid(id);
  }, [id, uid, client, setUid]);
  useEffect(() => {
    // The id just became known: write the cache now, so the very next reload already has something to show.
    // Never while the saved copy is still being read back: this child effect runs before the provider's restore, and saving an empty client then would overwrite it.
    if (uid !== null && !restoring) {
      void persistQueryClientSave({ queryClient: client, persister, buster: cacheBuster(uid), dehydrateOptions: dehydrateOptions(uid) });
    }
  }, [uid, client, persister, restoring]);
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
  const [loadedAt] = useState(() => Date.now());
  const [uid, setUidState] = useState<number | null>(() => readUid(tabStorage()));
  const uidRef = useRef(uid);
  const [persister] = useState<Persister>(() => {
    const storage = guardedStorage(tabStorage());
    // The write is throttled, so a write queued before the person was known could land after the id was: the cache is stamped for whoever
    // is known at the moment it is written, never with the buster it was queued under (a copy stamped for nobody is never restored).
    return storage
      ? createSyncStoragePersister({
          storage,
          key: CACHE_KEY,
          throttleTime: 300,
          serialize: (c) => JSON.stringify(trimToLimit({ ...c, buster: cacheBuster(uidRef.current) })),
        })
      : NO_PERSISTER;
  });
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
      // Only what came from the saved copy: an answer fetched since this page loaded is already current, and asking again would be a repeat request.
      onSuccess={() => void client.invalidateQueries({ predicate: (q) => q.state.dataUpdatedAt < loadedAt }, { cancelRefetch: false })}
    >
      <Identity uid={uid} setUid={setUid} client={client} persister={persister} />
      {children}
    </PersistQueryClientProvider>
  );
}
