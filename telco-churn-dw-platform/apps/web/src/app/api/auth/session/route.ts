import { NextResponse } from "next/server";

import { noStore, problem, profileOf } from "@/server/http";
import { accessToken, ACCESS_TTL, endSession, sessionUserId } from "@/server/session";
import { findUser } from "@/server/users";

export const dynamic = "force-dynamic";

/** Exchanges the session cookie for a fresh short-lived API token (roles re-read from the database). */
export async function GET() {
  const id = await sessionUserId();
  const user = id === null ? null : await findUser(id);
  if (!user) {
    if (id !== null) await endSession();
    return problem(401, "Not signed in");
  }
  return NextResponse.json(
    { profile: profileOf(user), accessToken: await accessToken(user), expiresIn: ACCESS_TTL },
    { headers: noStore },
  );
}
