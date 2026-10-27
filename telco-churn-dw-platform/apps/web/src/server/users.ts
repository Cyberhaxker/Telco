import "server-only";
import bcrypt from "bcryptjs";
import type { RowDataPacket } from "mysql2";

import type { Role } from "@/lib/roles";

import { db } from "./db";

export interface UserRow {
  id: number;
  username: string;
  name: string;
  roles: Role[];
}

interface DbUser extends RowDataPacket {
  id: number;
  username: string;
  name: string;
  password_hash: string;
  roles: string;
  active: number;
}

const KNOWN: readonly string[] = ["admin", "data_steward", "data_entry", "analyst", "viewer"];
// Compared against when the username is unknown so response time doesn't reveal which accounts exist.
const DUMMY_HASH = bcrypt.hashSync("not-a-real-password", 12);

function toUser(r: DbUser): UserRow {
  return { id: r.id, username: r.username, name: r.name, roles: r.roles.split(",").filter((x): x is Role => KNOWN.includes(x)) };
}

export async function authenticate(username: string, password: string): Promise<UserRow | null> {
  const [rows] = await db().query<DbUser[]>("SELECT * FROM app_users WHERE username = ? LIMIT 1", [username]);
  const row = rows[0];
  const ok = await bcrypt.compare(password, row?.password_hash ?? DUMMY_HASH);
  return row && row.active && ok ? toUser(row) : null;
}

export async function findUser(id: number): Promise<UserRow | null> {
  const [rows] = await db().query<DbUser[]>("SELECT * FROM app_users WHERE id = ? AND active = 1", [id]);
  return rows[0] ? toUser(rows[0]) : null;
}

/** Self-service sign-up always creates a read-only (viewer) account. */
export async function register(username: string, name: string, password: string): Promise<UserRow | "exists"> {
  const hash = await bcrypt.hash(password, 12);
  try {
    const [res] = await db().query<import("mysql2").ResultSetHeader>(
      "INSERT INTO app_users (username, name, password_hash, roles) VALUES (?, ?, ?, 'viewer')",
      [username, name, hash],
    );
    return { id: res.insertId, username, name, roles: ["viewer"] };
  } catch (e) {
    if ((e as { code?: string }).code === "ER_DUP_ENTRY") return "exists";
    throw e;
  }
}
