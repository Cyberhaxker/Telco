"use client";

import { liveQuery } from "dexie";
import { useEffect, useState } from "react";

/** Subscribe to an IndexedDB query; re-renders when the underlying tables change. */
export function useLiveQuery<T>(query: () => Promise<T>, deps: unknown[], initial: T): T {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    const sub = liveQuery(query).subscribe({ next: setValue, error: () => undefined });
    return () => sub.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return value;
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  fromCache: boolean;
  fetchedAt: string | null;
  reload: () => void;
}

/** Load data from a function returning { data, fromCache, fetchedAt }. */
export function useAsync<T>(
  fn: () => Promise<{ data: T; fromCache: boolean; fetchedAt: string }>,
  deps: unknown[],
  enabled = true,
): AsyncState<T> {
  const [state, setState] = useState<Omit<AsyncState<T>, "reload">>({
    data: null, error: null, loading: enabled, fromCache: false, fetchedAt: null,
  });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then(
      (r) => alive && setState({ data: r.data, error: null, loading: false, fromCache: r.fromCache, fetchedAt: r.fetchedAt }),
      (e: unknown) => alive && setState((s) => ({ ...s, error: e instanceof Error ? e : new Error(String(e)), loading: false })),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}
