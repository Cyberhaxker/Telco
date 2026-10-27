import "server-only";
import mysql from "mysql2/promise";

// Users live in the operational MySQL database (telco_ops.app_users).
let pool: mysql.Pool | null = null;

export function db(): mysql.Pool {
  pool ??= mysql.createPool({
    host: process.env.OPS_DB_HOST ?? "127.0.0.1",
    port: Number(process.env.OPS_DB_PORT ?? 3306),
    user: process.env.OPS_DB_USER ?? "ops_app",
    password: process.env.OPS_DB_PASSWORD ?? process.env.OPS_APP_PASSWORD,
    database: process.env.OPS_DB ?? "telco_ops",
    connectionLimit: 5,
  });
  return pool;
}
