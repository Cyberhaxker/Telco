"use client";

// Sign-in against the web app's own /api/auth routes (bcrypt-checked users, JWT). The httpOnly
// session cookie proves who you are; short-lived API tokens are fetched from /api/auth/session and
// kept in memory only. Offline, the last known profile lets people browse cached data and queue writes.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { getState, setState } from "./db";
import type { Role } from "./roles";

export type AuthStatus = "loading" | "authenticated" | "offline" | "anonymous";

export interface Profile {
  username: string;
  name: string;
  roles: Role[];
}

export interface RegisterInput {
  username: string;
  name: string;
  password: string;
}

export interface AuthContextValue {
  status: AuthStatus;
  profile: Profile | null;
  getToken: () => Promise<string | null>;
  /** Resolves to an error message, or null on success. */
  signIn: (username: string, password: string) => Promise<string | null>;
  signUp: (input: RegisterInput) => Promise<string | null>;
  logout: () => Promise<void>;
}

interface TokenResponse {
  profile: Profile;
  accessToken: string;
  expiresIn: number;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [profile, setProfile] = useState<Profile | null>(null);
  const tokenRef = useRef<{ value: string; expiresAt: number } | null>(null);

  const adopt = useCallback(async (res: TokenResponse) => {
    tokenRef.current = { value: res.accessToken, expiresAt: Date.now() + res.expiresIn * 1000 };
    setProfile(res.profile);
    setStatus("authenticated");
    await setState("profile", res.profile);
  }, []);

  /** Fetches a fresh token from the session cookie; null if there's no session. Throws when unreachable. */
  const refresh = useCallback(async (): Promise<TokenResponse | null> => {
    const res = await fetch("/api/auth/session", { cache: "no-store", credentials: "same-origin" });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error(`session check failed (${res.status})`);
    return (await res.json()) as TokenResponse;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await refresh();
        if (cancelled) return;
        if (res) return void (await adopt(res));
        setStatus("anonymous");
      } catch {
        if (cancelled) return;
        const saved = await getState<Profile>("profile");
        if (saved && !navigator.onLine) {
          setProfile(saved);
          setStatus("offline");
        } else {
          setStatus("anonymous");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adopt, refresh]);

  const getToken = useCallback(async () => {
    const t = tokenRef.current;
    if (t && t.expiresAt - Date.now() > 30_000) return t.value;
    if (!navigator.onLine) return null;
    try {
      const res = await refresh();
      if (!res) {
        tokenRef.current = null;
        setStatus("anonymous");
        return null;
      }
      await adopt(res);
      return res.accessToken;
    } catch {
      return null;
    }
  }, [adopt, refresh]);

  const post = useCallback(
    async (url: string, body: unknown): Promise<string | null> => {
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(body),
        });
        const json = (await res.json().catch(() => ({}))) as Partial<TokenResponse> & { detail?: string };
        if (!res.ok) return json.detail ?? `Sign-in failed (${res.status})`;
        await adopt(json as TokenResponse);
        return null;
      } catch {
        return "Cannot reach the server. Check your connection and try again.";
      }
    },
    [adopt],
  );

  const signIn = useCallback((username: string, password: string) => post("/api/auth/login", { username, password }), [post]);
  const signUp = useCallback((input: RegisterInput) => post("/api/auth/register", input), [post]);

  const logout = useCallback(async () => {
    await setState("profile", null);
    tokenRef.current = null;
    setProfile(null);
    setStatus("anonymous");
    if (navigator.onLine) await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
  }, []);

  const value = useMemo(
    () => ({ status, profile, getToken, signIn, signUp, logout }),
    [status, profile, getToken, signIn, signUp, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
