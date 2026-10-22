"use client";

import { useEffect, type ReactNode } from "react";

import { AuthProvider, useAuth } from "@/lib/auth";
import { syncNow } from "@/lib/sync";

/** Runs the outbox sync on start, on reconnect, every minute and on Background Sync wake-ups. */
function SyncScheduler() {
  const { status, getToken } = useAuth();
  useEffect(() => {
    if (status !== "authenticated") return;
    const run = () => void syncNow(getToken);
    run();
    const timer = setInterval(run, 60_000);
    window.addEventListener("online", run);
    const onMessage = (e: MessageEvent) => {
      if ((e.data as { type?: string } | null)?.type === "outbox-sync") run();
    };
    navigator.serviceWorker?.addEventListener("message", onMessage);
    return () => {
      clearInterval(timer);
      window.removeEventListener("online", run);
      navigator.serviceWorker?.removeEventListener("message", onMessage);
    };
  }, [status, getToken]);
  return null;
}

function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
    }
  }, []);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ServiceWorkerRegistration />
      <SyncScheduler />
      {children}
    </AuthProvider>
  );
}
