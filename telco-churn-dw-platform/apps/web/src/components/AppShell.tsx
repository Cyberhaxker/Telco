"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { ago } from "@/lib/format";
import { useLiveQuery, useOnline } from "@/lib/hooks";
import { hasRole, NAV, type Role } from "@/lib/roles";

import { ThemeToggle } from "./ThemeToggle";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const online = useOnline();
  const { profile, status, logout } = useAuth();
  const roles = profile?.roles ?? [];
  const pending = useLiveQuery(() => db.outbox.where("status").anyOf("PENDING", "SENDING").count(), [], 0);
  const failed = useLiveQuery(() => db.outbox.where("status").anyOf("FAILED", "REJECTED", "PARTIAL").count(), [], 0);
  const lastCache = useLiveQuery(
    async () => (await db.analytics_cache.orderBy("fetched_at").last())?.fetched_at ?? null, [], null as string | null,
  );

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-row">
          <Link href="/dashboard" className="brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icons/icon-192.png" alt="" width={28} height={28} />
            <span>
              Telco Churn Analytics
              <small>Customer churn warehouse</small>
            </span>
          </Link>
          <div className="topbar-status">
            <span className={`pill ${online ? "ok" : "warn"}`} role="status">
              <span className="dot" aria-hidden="true" />
              {online ? "Online" : "Offline"}
            </span>
            {hasRole(roles, ["data_entry", "data_steward"]) && (
              <Link href="/sync" className={`pill ${pending ? "signal" : failed ? "bad" : ""}`}>
                {pending ? `${pending} waiting to sync` : failed ? `${failed} need review` : "All synced"}
              </Link>
            )}
            <ThemeToggle />
            {profile && (
              <span className="small muted" title={profile.roles.join(", ")}>
                {profile.name}
              </span>
            )}
            {status === "authenticated" && (
              <button type="button" className="btn small" onClick={() => void logout()}>
                Sign out
              </button>
            )}
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          {NAV.filter((item) => hasRole(roles, item.roles as Role[])).map((item) => (
            <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined}>
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      {!online ? (
        <div className="banner offline" role="status">
          <strong>You are offline.</strong>
          <span>
            Showing data saved {ago(lastCache)}. New records are kept on this device and sync when you reconnect.
          </span>
        </div>
      ) : (
        <div />
      )}
      <main className="main" id="main">
        {children}
      </main>
    </div>
  );
}
