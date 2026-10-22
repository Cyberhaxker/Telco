"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";

export default function AuthCallback() {
  const { completeLogin } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    completeLogin().then(
      (to) => router.replace(to),
      (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [completeLogin, router]);
  return (
    <div className="login">
      <div className="panel card">
        {error ? (
          <>
            <h1>Sign-in failed</h1>
            <div className="notice bad">{error}</div>
            <a className="btn primary" href="/login">Try again</a>
          </>
        ) : (
          <p>Completing sign-in…</p>
        )}
      </div>
    </div>
  );
}
