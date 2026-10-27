import { NextResponse, type NextRequest } from "next/server";

import { noStore, problem, profileOf } from "@/server/http";
import { accessToken, ACCESS_TTL, startSession } from "@/server/session";
import { authenticate } from "@/server/users";

export const dynamic = "force-dynamic";

// In-memory throttle per username+IP: 5 failures per 5 minutes (single-instance dev/small deployments).
const failures = new Map<string, { n: number; until: number }>();

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => null)) as { username?: unknown; password?: unknown } | null;
  const username = typeof body?.username === "string" ? body.username.trim().toLowerCase() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  if (!username || !password) return problem(400, "Username and password are required");

  const k = `${username}|${req.headers.get("x-forwarded-for") ?? ""}`;
  const f = failures.get(k);
  if (f && f.n >= 5 && f.until > Date.now()) return problem(429, "Too many attempts. Try again in a few minutes.");

  const user = await authenticate(username, password);
  if (!user) {
    failures.set(k, { n: (f && f.until > Date.now() ? f.n : 0) + 1, until: Date.now() + 5 * 60_000 });
    return problem(401, "Invalid username or password");
  }
  failures.delete(k);
  await startSession(user);
  return NextResponse.json(
    { profile: profileOf(user), accessToken: await accessToken(user), expiresIn: ACCESS_TTL },
    { headers: noStore },
  );
}
