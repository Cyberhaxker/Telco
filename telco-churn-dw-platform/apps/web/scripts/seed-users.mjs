// Creates telco_ops.app_users and one account per role (idempotent; existing users are left alone).
// Passwords come from SEED_<USERNAME>_PASSWORD or are generated and printed once.
// Usage: OPS_APP_PASSWORD=... node scripts/seed-users.mjs
import { randomBytes } from "node:crypto";

import bcrypt from "bcryptjs";
import mysql from "mysql2/promise";

const conn = await mysql.createConnection({
  host: process.env.OPS_DB_HOST ?? "127.0.0.1",
  port: Number(process.env.OPS_DB_PORT ?? 3306),
  user: process.env.OPS_DB_USER ?? "ops_app",
  password: process.env.OPS_DB_PASSWORD ?? process.env.OPS_APP_PASSWORD,
  database: process.env.OPS_DB ?? "telco_ops",
  multipleStatements: true,
});
await conn.query(`CREATE TABLE IF NOT EXISTS app_users (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(40)  NOT NULL UNIQUE,
  name          VARCHAR(80)  NOT NULL,
  password_hash VARCHAR(100) NOT NULL,
  roles         VARCHAR(120) NOT NULL DEFAULT 'viewer',
  active        TINYINT(1)   NOT NULL DEFAULT 1,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
)`); // same DDL as infra/db/mysql/init/02_app_users.sql

const USERS = [
  ["admin", "Administrator", "admin"],
  ["steward", "Data steward", "data_steward"],
  ["entry", "Data entry clerk", "data_entry"],
  ["analyst", "Analyst", "analyst"],
  ["viewer", "Viewer", "viewer"],
];
for (const [username, name, role] of USERS) {
  const [rows] = await conn.query("SELECT 1 FROM app_users WHERE username = ?", [username]);
  if (rows.length) continue;
  const supplied = process.env[`SEED_${username.toUpperCase()}_PASSWORD`];
  const password = supplied ?? randomBytes(9).toString("base64url");
  await conn.query("INSERT INTO app_users (username, name, password_hash, roles) VALUES (?, ?, ?, ?)", [
    username,
    name,
    await bcrypt.hash(password, 12),
    role,
  ]);
  console.log(`created ${username} (${role})${supplied ? "" : `  password: ${password}`}`);
}
await conn.end();
