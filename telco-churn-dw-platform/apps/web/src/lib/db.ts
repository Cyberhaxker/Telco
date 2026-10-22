import Dexie, { type EntityTable } from "dexie";

import type { TelcoRecord } from "./validation";

export type OutboxStatus = "PENDING" | "SENDING" | "ACCEPTED" | "PARTIAL" | "REJECTED" | "FAILED";

export interface RowError {
  row: number;
  field: string;
  code: string;
  message: string;
}

export interface Conflict {
  row?: number;
  customer_id: string;
  server_version: number;
  client_version: number;
  server_record?: Partial<TelcoRecord> & { version?: number };
}

export interface OutboxBatch {
  batch_id: string;
  idempotency_key: string;
  source: "form" | "csv";
  label: string;
  records: TelcoRecord[];
  /** Exact JSON body that is sent; kept so a resend is byte-identical. */
  payload: string;
  checksum: string;
  status: OutboxStatus;
  attempts: number;
  next_attempt_at: number;
  last_error: string | null;
  errors: RowError[];
  conflicts: Conflict[];
  accepted_count: number;
  created_at: string;
  updated_at: string;
}

export interface Draft {
  id: string;
  record: Partial<TelcoRecord>;
  updated_at: string;
}

export interface MetadataEntry {
  key: string;
  value: unknown;
  fetched_at: string;
  etag?: string;
}

export interface CacheEntry {
  key: string;
  value: unknown;
  fetched_at: string;
}

export interface SyncState {
  key: string;
  value: unknown;
}

export class TelcoDb extends Dexie {
  metadata!: EntityTable<MetadataEntry, "key">;
  drafts!: EntityTable<Draft, "id">;
  outbox!: EntityTable<OutboxBatch, "batch_id">;
  analytics_cache!: EntityTable<CacheEntry, "key">;
  sync_state!: EntityTable<SyncState, "key">;

  constructor(name = "telco-churn") {
    super(name);
    this.version(1).stores({
      metadata: "key",
      drafts: "id, updated_at",
      outbox: "batch_id, status, next_attempt_at, created_at",
      analytics_cache: "key, fetched_at",
      sync_state: "key",
    });
  }
}

export const db = new TelcoDb();

export async function getState<T>(key: string): Promise<T | undefined> {
  return (await db.sync_state.get(key))?.value as T | undefined;
}

export async function setState(key: string, value: unknown): Promise<void> {
  await db.sync_state.put({ key, value });
}
