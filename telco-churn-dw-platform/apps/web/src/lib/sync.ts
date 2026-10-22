// Offline outbox: records are validated in the browser, grouped into batches of
// at most 500, checksummed and stored in IndexedDB. The sync engine sends them
// with an Idempotency-Key when online, retrying with exponential backoff and
// jitter (8 attempts max) and keeping per-row errors and conflicts for review.
import { loadConfig } from "./config";
import { db, type OutboxBatch, type OutboxStatus, type RowError } from "./db";
import { validateRecord, type TelcoRecord } from "./validation";

export const MAX_BATCH_RECORDS = 500;
export const MAX_ATTEMPTS = 8;
const BASE_DELAY_MS = 2_000;
const MAX_DELAY_MS = 5 * 60_000;

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const exp = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** Math.max(0, attempt - 1));
  return Math.round(exp / 2 + random() * (exp / 2)); // "equal jitter"
}

export function clientId(): string {
  let id = localStorage.getItem("telco.clientId");
  if (!id) {
    id = `pwa-${crypto.randomUUID().slice(0, 8)}`;
    localStorage.setItem("telco.clientId", id);
  }
  return id;
}

export interface QueueResult {
  batches: OutboxBatch[];
  invalid: RowError[];
}

/** Validate, split into batches of <= 500 and store them in the outbox. Invalid rows are not queued. */
export async function queueRecords(records: TelcoRecord[], source: "form" | "csv", label: string): Promise<QueueResult> {
  const invalid: RowError[] = [];
  const valid: TelcoRecord[] = [];
  records.forEach((r, i) => {
    const errors = validateRecord(r, i);
    if (errors.length) invalid.push(...errors);
    else valid.push(r);
  });
  const batches: OutboxBatch[] = [];
  for (let start = 0; start < valid.length; start += MAX_BATCH_RECORDS) {
    const chunk = valid.slice(start, start + MAX_BATCH_RECORDS);
    const batchId = crypto.randomUUID();
    const now = new Date().toISOString();
    const payload = JSON.stringify({ batch_id: batchId, client_id: clientId(), created_at: now, source, records: chunk });
    const part = valid.length > MAX_BATCH_RECORDS ? ` (part ${start / MAX_BATCH_RECORDS + 1})` : "";
    batches.push({
      batch_id: batchId, idempotency_key: crypto.randomUUID(), source, label: label + part, records: chunk, payload,
      checksum: await sha256Hex(payload), status: "PENDING", attempts: 0, next_attempt_at: 0, last_error: null,
      errors: [], conflicts: [], accepted_count: 0, created_at: now, updated_at: now,
    });
  }
  if (batches.length) await db.outbox.bulkAdd(batches);
  requestBackgroundSync();
  return { batches, invalid };
}

/** Rebuild a batch after the user corrected rows; it gets a new key because the payload changed. */
export async function resubmit(batchId: string, records: TelcoRecord[]): Promise<void> {
  const old = await db.outbox.get(batchId);
  if (!old) return;
  await db.outbox.delete(batchId);
  await queueRecords(records, old.source, `${old.label} (resubmitted)`);
}

export function requestBackgroundSync(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.ready
    .then((reg) => (reg as ServiceWorkerRegistration & { sync?: { register(tag: string): Promise<void> } }).sync?.register("outbox-sync"))
    .catch(() => undefined);
}

interface BatchResponse {
  status: string;
  outcome: "ACCEPTED" | "PARTIAL" | "REJECTED";
  accepted_count: number;
  errors: RowError[];
  conflicts: OutboxBatch["conflicts"];
}

export interface SyncReport {
  sent: number;
  accepted: number;
  failed: number;
  skipped: string | null;
}

let running: Promise<SyncReport> | null = null;

/** Send every due batch. Concurrent calls share one run. */
export function syncNow(getToken: () => Promise<string | null>, opts: { force?: boolean } = {}): Promise<SyncReport> {
  running ??= runSync(getToken, opts).finally(() => {
    running = null;
  });
  return running;
}

async function runSync(getToken: () => Promise<string | null>, { force = false }): Promise<SyncReport> {
  const report: SyncReport = { sent: 0, accepted: 0, failed: 0, skipped: null };
  if (!navigator.onLine) return { ...report, skipped: "offline" };
  const token = await getToken();
  if (!token) return { ...report, skipped: "signed-out" };
  const cfg = await loadConfig();
  const now = Date.now();
  const due = (await db.outbox.where("status").anyOf("PENDING", "SENDING").toArray())
    .filter((b) => force || b.next_attempt_at <= now)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));

  for (const batch of due) {
    await db.outbox.update(batch.batch_id, { status: "SENDING", updated_at: new Date().toISOString() });
    report.sent++;
    try {
      const res = await fetch(`${cfg.apiBase}/ingest/batches`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(await getToken()) ?? token}`,
          "Idempotency-Key": batch.idempotency_key,
          "X-Checksum-SHA256": batch.checksum,
        },
        body: batch.payload,
      });
      if (res.ok) {
        const body = (await res.json()) as BatchResponse;
        const status: OutboxStatus = body.outcome;
        await db.outbox.update(batch.batch_id, {
          status, accepted_count: body.accepted_count, errors: body.errors, conflicts: body.conflicts,
          last_error: null, attempts: batch.attempts + 1, updated_at: new Date().toISOString(),
        });
        report.accepted += body.accepted_count;
        continue;
      }
      // 4xx other than auth/rate-limit/in-progress will not succeed on retry.
      const retryable = res.status >= 500 || [401, 408, 409, 429].includes(res.status);
      const problem = (await res.json().catch(() => ({}))) as { detail?: string; title?: string; errors?: RowError[] };
      await fail(batch, `${res.status} ${problem.detail ?? problem.title ?? res.statusText}`, retryable, problem.errors);
      report.failed++;
      if (res.status === 401) break;
    } catch (err) {
      await fail(batch, err instanceof Error ? err.message : String(err), true);
      report.failed++;
    }
  }
  return report;
}

async function fail(batch: OutboxBatch, message: string, retryable: boolean, errors: RowError[] = []): Promise<void> {
  const attempts = batch.attempts + 1;
  const giveUp = !retryable || attempts >= MAX_ATTEMPTS;
  await db.outbox.update(batch.batch_id, {
    status: giveUp ? "FAILED" : "PENDING",
    attempts,
    last_error: message,
    errors: errors.length ? errors : batch.errors,
    next_attempt_at: giveUp ? 0 : Date.now() + backoffDelay(attempts),
    updated_at: new Date().toISOString(),
  });
}

export async function pendingCount(): Promise<number> {
  return db.outbox.where("status").anyOf("PENDING", "SENDING").count();
}

export async function retryBatch(batchId: string): Promise<void> {
  await db.outbox.update(batchId, { status: "PENDING", attempts: 0, next_attempt_at: 0, updated_at: new Date().toISOString() });
}
