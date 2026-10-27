"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { hasRole, type Role } from "@/lib/roles";

import { AppShell } from "./AppShell";

interface PageProps {
  title: string;
  description?: string;
  roles: Role[];
  actions?: ReactNode;
  children: ReactNode;
}

/** Page frame: shell, heading, and role-based access (also enforced by the APIs). */
export function Page({ title, description, roles, actions, children }: PageProps) {
  const { status, profile } = useAuth();

  if (status === "loading") {
    return (
      <AppShell>
        <div className="empty">Checking your session…</div>
      </AppShell>
    );
  }
  if (status === "anonymous") {
    return (
      <AppShell>
        <div className="panel" style={{ maxWidth: 520 }}>
          <h1>Sign in to continue</h1>
          <p className="muted">Your session has ended. Sign in with your Telco account to open {title.toLowerCase()}.</p>
          <div>
            <a className="btn primary" href="/login">
              Sign in
            </a>
          </div>
        </div>
      </AppShell>
    );
  }
  if (!hasRole(profile?.roles ?? [], roles)) {
    return (
      <AppShell>
        <div className="panel" style={{ maxWidth: 560 }}>
          <h1>{title}</h1>
          <p>
            This page needs the <strong>{roles.join(" or ")}</strong> role. Ask an administrator to change your role.
          </p>
        </div>
      </AppShell>
    );
  }
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="btn-row">{actions}</div>}
      </div>
      {children}
    </AppShell>
  );
}
