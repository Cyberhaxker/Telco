"use client";

import { liveQuery } from "dexie";
import { useEffect, useRef, useState } from "react";

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

export type StreamStatus = "connecting" | "live" | "polling" | "closed";

/**
 * Subscribe to a server-sent-events endpoint with fetch (so the bearer token can be sent).
 * `event` is the SSE event name carrying JSON. If the stream cannot be opened, or drops, the hook
 * reconnects with backoff and meanwhile loads `fallback` (a plain GET) so the page never stays empty.
 */
export function useEventStream<T>(
  open: (signal: AbortSignal) => Promise<Response>,
  event: string,
  fallback: () => Promise<T>,
  enabled = true,
): { data: T | null; status: StreamStatus; error: Error | null; updatedAt: string | null } {
  const [state, setState] = useState<{ data: T | null; status: StreamStatus; error: Error | null; updatedAt: string | null }>({
    data: null, status: "connecting", error: null, updatedAt: null,
  });
  const openRef = useRef(open);
  const fallbackRef = useRef(fallback);
  openRef.current = open;
  fallbackRef.current = fallback;

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let attempt = 0;
    const push = (data: T) => setState({ data, status: "live", error: null, updatedAt: new Date().toISOString() });

    async function run() {
      while (!ctrl.signal.aborted) {
        try {
          const res = await openRef.current(ctrl.signal);
          if (!res.ok || !res.body) throw new Error(`stream HTTP ${res.status}`);
          attempt = 0;
          const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += value;
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              const block = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              let name = "message";
              const data: string[] = [];
              for (const line of block.split("\n")) {
                if (line.startsWith("event:")) name = line.slice(6).trim();
                else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
              }
              if (name === event && data.length) push(JSON.parse(data.join("\n")) as T);
            }
          }
        } catch (e) {
          if (ctrl.signal.aborted) return;
          setState((s) => ({ ...s, status: "polling", error: e instanceof Error ? e : new Error(String(e)) }));
          try {
            const data = await fallbackRef.current();
            setState({ data, status: "polling", error: null, updatedAt: new Date().toISOString() });
          } catch {
            // keep last data; retry below
          }
        }
        attempt += 1;
        await new Promise((r) => setTimeout(r, Math.min(30_000, 2_000 * attempt)));
      }
    }
    void run();
    return () => ctrl.abort();
  }, [event, enabled]);

  return state;
}
