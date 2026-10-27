"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/lib/auth";
import { useOnline } from "@/lib/hooks";

export default function LoginPage() {
  const { status, signIn, signUp } = useAuth();
  const online = useOnline();
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authenticated" || status === "offline") router.replace("/dashboard");
  }, [status, router]);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const username = String(f.get("username") ?? "").trim();
    const password = String(f.get("password") ?? "");
    setBusy(true);
    setError(null);
    const err =
      mode === "signin"
        ? await signIn(username, password)
        : await signUp({ username, name: String(f.get("name") ?? "").trim(), password });
    setBusy(false);
    if (err) setError(err);
  };

  return (
    <div className="login">
      <div className="panel card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/icon-192.png" alt="" width={56} height={56} />
        <div>
          <h1>Telco Churn Analytics</h1>
          <p className="muted">
            Churn KPIs, OLAP analysis, predictions and offline data entry for the customer warehouse.
          </p>
        </div>
        {online ? (
          <form onSubmit={submit} style={{ display: "grid", gap: "12px" }}>
            {mode === "signup" && (
              <div className="field">
                <label htmlFor="name">Full name</label>
                <input id="name" name="name" autoComplete="name" required maxLength={80} />
              </div>
            )}
            <div className="field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                required
                minLength={3}
                maxLength={40}
                autoCapitalize="none"
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                required
                minLength={mode === "signup" ? 10 : 1}
                maxLength={72}
              />
            </div>
            {mode === "signup" && (
              <p className="small muted">
                At least 10 characters. New accounts get read-only access until an administrator changes the
                role.
              </p>
            )}
            {error && (
              <div className="notice bad" role="alert">
                {error}
              </div>
            )}
            <button type="submit" className="btn primary" disabled={busy || status === "loading"}>
              {busy
                ? "Please wait…"
                : status === "loading"
                  ? "Checking session…"
                  : mode === "signin"
                    ? "Sign in"
                    : "Create account"}
            </button>
            <button
              type="button"
              className="btn secondary"
              onClick={() => {
                setMode(mode === "signin" ? "signup" : "signin");
                setError(null);
              }}
            >
              {mode === "signin" ? "Register New Account" : "I already have an account"}
            </button>
          </form>
        ) : (
          <div className="notice warn">
            You are offline. Sign in once while online; after that the app opens offline with saved data.
          </div>
        )}
        <p className="small muted">
          Your API access token is kept in memory only; the session cookie is httpOnly.
        </p>
      </div>
    </div>
  );
}
