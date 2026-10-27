import "server-only";
import { NextResponse } from "next/server";

import type { UserRow } from "./users";

export const noStore = { "Cache-Control": "no-store" };

export function problem(status: number, detail: string): NextResponse {
  return NextResponse.json({ title: status === 401 ? "Unauthorized" : "Error", status, detail }, { status, headers: noStore });
}

export function profileOf(u: UserRow) {
  return { username: u.username, name: u.name, roles: u.roles };
}
