/// <reference lib="webworker" />
// Service worker (Serwist): precache the app shell and every page, NetworkFirst
// for API GETs with an offline fallback, never cache POST/PUT. Background Sync
// wakes the app so it can flush the outbox (the app holds the access token).
import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { ExpirationPlugin, NetworkFirst, NetworkOnly, Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}
declare const self: ServiceWorkerGlobalScope & { __SW_MANIFEST: (PrecacheEntry | string)[] | undefined };

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      matcher: ({ url, request }) => url.pathname.startsWith("/api/") && request.method !== "GET",
      handler: new NetworkOnly(),
    },
    {
      matcher: ({ url, request }) =>
        request.method === "GET" && /^\/api\/v1\/(analytics|meta)\//.test(url.pathname),
      handler: new NetworkFirst({
        cacheName: "api-get",
        networkTimeoutSeconds: 6,
        plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 24 * 3600 })],
      }),
    },
    {
      matcher: ({ url }) => url.pathname === "/config.json",
      handler: new NetworkFirst({ cacheName: "runtime-config", networkTimeoutSeconds: 3 }),
    },
    ...defaultCache,
  ],
  fallbacks: {
    entries: [{ url: "/offline", matcher: ({ request }) => request.destination === "document" }],
  },
});

self.addEventListener("sync", (event: Event) => {
  const e = event as Event & { tag: string; waitUntil(p: Promise<unknown>): void };
  if (e.tag === "outbox-sync") {
    e.waitUntil(
      self.clients.matchAll({ type: "window" }).then((clients) => {
        for (const c of clients) c.postMessage({ type: "outbox-sync" });
      }),
    );
  }
});

serwist.addEventListeners();
