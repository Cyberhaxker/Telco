"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";
import { useOnline } from "@/lib/hooks";

export default function LoginPage() {
  const { status, login, getRegistrationUrl } = useAuth();
  const online = useOnline();
  const router = useRouter();
  useEffect(() => {
    if (status === "authenticated" || status === "offline") router.replace("/dashboard");
  }, [status, router]);

  const handleRegister = async () => {
    const url = await getRegistrationUrl();
    window.location.href = url;
  };

  return (
    <div className="login">
      <div className="panel card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/icon-192.png" alt="" width={56} height={56} />
        <div>
          <h1>Telco Churn Analytics</h1>
          <p className="muted">Churn KPIs, OLAP analysis, predictions and offline data entry for the customer warehouse.</p>
        </div>
        {online ? (
          <div style={{ display: "grid", gap: "12px" }}>
            <button type="button" className="btn primary" onClick={() => void login("/dashboard")} disabled={status === "loading"}>
              {status === "loading" ? "Checking session…" : "Sign in with Keycloak"}
            </button>
            <button type="button" className="btn secondary" onClick={handleRegister}>
              Register New Account
            </button>
          </div>
        ) : (
          <div className="notice warn">You are offline. Sign in once while online; after that the app opens offline with saved data.</div>
        )}
        <p className="small muted">Uses single sign-on (OAuth 2.0 with PKCE). Your access token is kept in memory only.</p>
      </div>
    </div>
  );
}
