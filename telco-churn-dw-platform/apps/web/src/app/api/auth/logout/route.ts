import { NextResponse } from "next/server";

import { noStore } from "@/server/http";
import { endSession } from "@/server/session";

export const dynamic = "force-dynamic";

export async function POST() {
  await endSession();
  return NextResponse.json({ ok: true }, { headers: noStore });
}
