"use client";

// Keycloak login with Authorization Code + PKCE (oidc-client-ts). Tokens live in
// memory only; after a reload the Keycloak SSO session restores them silently.
// Offline, the last known profile lets people browse cached data and queue writes.
import { InMemoryWebStorage, User, UserManager, WebStorageStateStore } from "oidc-client-ts";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { loadConfig } from "./config";
import { getState, setState } from "./db";
import { rolesFromToken, type Role } from "./roles";

export type AuthStatus = "loading" | "authenticated" | "offline" | "anonymous";

export interface Profile {
  username: string;
  name: string;
  roles: Role[];
}

export interface AuthContextValue {
  status: AuthStatus;
  profile: Profile | null;
  getToken: () => Promise<string | null>;
  login: (returnTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  completeLogin: () => Promise<string>;
  getRegistrationUrl: () => Promise<string>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
let manager: UserManager | null = null;

async function getManager(): Promise<UserManager> {
  if (manager) return manager;
  const cfg = await loadConfig();
  const origin = window.location.origin;
  manager = new UserManager({
    authority: `${cfg.keycloakUrl}/realms/${cfg.realm}`,
    client_id: cfg.clientId,
    redirect_uri: `${origin}/auth/callback`,
    silent_redirect_uri: `${origin}/silent-renew.html`,
    post_logout_redirect_uri: `${origin}/login`,
    response_type: "code",
    scope: "openid",
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    automaticSilentRenew: true,
    monitorSession: false,
    silentRequestTimeoutInSeconds: 6,
  });
  return manager;
}

function toProfile(user: User): Profile {
  const p = user.profile;
  return {
    username: String(p.preferred_username ?? p.sub),
    name: String(p.name ?? p.preferred_username ?? p.sub),
    roles: rolesFromToken(user.access_token),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [profile, setProfile] = useState<Profile | null>(null);
  const userRef = useRef<User | null>(null);

  const adopt = useCallback(async (user: User | null) => {
    userRef.current = user;
    if (user && !user.expired) {
      const prof = toProfile(user);
      setProfile(prof);
      setStatus("authenticated");
      await setState("profile", prof);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const mgr = await getManager();
      mgr.events.addUserLoaded((u) => void adopt(u));
      mgr.events.addUserSignedOut(() => {
        userRef.current = null;
        setStatus("anonymous");
      });
      const existing = await mgr.getUser();
      if (existing && !existing.expired) return adopt(existing);
      if (navigator.onLine && !window.location.pathname.startsWith("/auth/")) {
        try {
          const u = await mgr.signinSilent();
          if (!cancelled) return adopt(u);
        } catch {
          // no Keycloak session: fall through
        }
      }
      if (cancelled) return;
      const saved = await getState<Profile>("profile");
      if (!navigator.onLine && saved) {
        setProfile(saved);
        setStatus("offline");
      } else {
        setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adopt]);

  const getToken = useCallback(async () => {
    const user = userRef.current;
    if (!user) return null;
    if ((user.expires_in ?? 0) > 30) return user.access_token;
    if (!navigator.onLine) return null;
    try {
      const mgr = await getManager();
      const renewed = await mgr.signinSilent();
      await adopt(renewed);
      return renewed?.access_token ?? null;
    } catch {
      setStatus("anonymous");
      return null;
    }
  }, [adopt]);

  const login = useCallback(async (returnTo?: string) => {
    const mgr = await getManager();
    await mgr.signinRedirect({ state: { returnTo: returnTo ?? "/dashboard" } });
  }, []);

  const getRegistrationUrl = useCallback(async () => {
    const cfg = await loadConfig();
    const origin = window.location.origin;
    const params = new URLSearchParams({
      client_id: cfg.clientId,
      response_type: "code",
      scope: "openid",
      redirect_uri: `${origin}/auth/callback`,
    });
    return `${cfg.keycloakUrl}/realms/${cfg.realm}/protocol/openid-connect/registrations?${params.toString()}`;
  }, []);

  const logout = useCallback(async () => {
    const mgr = await getManager();
    await setState("profile", null);
    const user = userRef.current;
    userRef.current = null;
    setProfile(null);
    setStatus("anonymous");
    if (navigator.onLine) await mgr.signoutRedirect({ id_token_hint: user?.id_token });
  }, []);

  const completeLogin = useCallback(async () => {
    const mgr = await getManager();
    const user = await mgr.signinRedirectCallback();
    await adopt(user);
    const state = user.state as { returnTo?: string } | undefined;
    return state?.returnTo && state.returnTo.startsWith("/") ? state.returnTo : "/dashboard";
  }, [adopt]);

  const value = useMemo(
    () => ({ status, profile, getToken, login, logout, completeLogin, getRegistrationUrl }),
    [status, profile, getToken, login, logout, completeLogin, getRegistrationUrl],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
