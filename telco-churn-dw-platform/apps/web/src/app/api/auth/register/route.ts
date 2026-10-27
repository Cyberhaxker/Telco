import { NextResponse, type NextRequest } from "next/server";

import { noStore, problem, profileOf } from "@/server/http";
import { accessToken, ACCESS_TTL, startSession } from "@/server/session";
import { register } from "@/server/users";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => null)) as { username?: unknown; name?: unknown; password?: unknown } | null;
  const username = typeof body?.username === "string" ? body.username.trim().toLowerCase() : "";
  const name = typeof body?.name === "string" ? body.name.trim() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  if (!/^[a-z0-9._-]{3,40}$/.test(username)) return problem(400, "Username must be 3-40 characters: letters, digits, . _ -");
  if (name.length < 1 || name.length > 80) return problem(400, "Name is required (80 characters max)");
  if (password.length < 10 || password.length > 72) return problem(400, "Password must be 10-72 characters");

  const user = await register(username, name, password);
  if (user === "exists") return problem(409, "That username is taken");
  await startSession(user);
  return NextResponse.json(
    { profile: profileOf(user), accessToken: await accessToken(user), expiresIn: ACCESS_TTL },
    { status: 201, headers: noStore },
  );
}
