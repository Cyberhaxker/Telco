import "server-only";
import { jwtVerify, SignJWT } from "jose";
import { cookies } from "next/headers";

import type { UserRow } from "./users";

export const COOKIE = "telco_session";
const SESSION_TTL = 8 * 3600;
export const ACCESS_TTL = 15 * 60;
const ISSUER = process.env.JWT_ISSUER ?? "telco-web";
const AUDIENCE = process.env.OIDC_AUDIENCE ?? "telco-api";

function key(): Uint8Array {
  const secret = process.env.JWT_SECRET;
  if (!secret || secret.length < 32) throw new Error("JWT_SECRET must be set (32+ characters)");
  return new TextEncoder().encode(secret);
}

function sign(user: UserRow, typ: "session" | "access", ttl: number, aud: string): Promise<string> {
  return new SignJWT({ typ, preferred_username: user.username, name: user.name, roles: user.roles })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(String(user.id))
    .setIssuer(ISSUER)
    .setAudience(aud)
    .setIssuedAt()
    .setExpirationTime(`${ttl}s`)
    .sign(key());
}

/** Sets the httpOnly session cookie (8h). The browser exchanges it for short-lived API bearer tokens. */
export async function startSession(user: UserRow): Promise<void> {
  (await cookies()).set(COOKIE, await sign(user, "session", SESSION_TTL, "telco-web"), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** Subject of a valid session cookie, or null. */
export async function sessionUserId(): Promise<number | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, key(), { issuer: ISSUER, audience: "telco-web" });
    return payload.typ === "session" ? Number(payload.sub) : null;
  } catch {
    return null;
  }
}

export function accessToken(user: UserRow): Promise<string> {
  return sign(user, "access", ACCESS_TTL, AUDIENCE);
}
