import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { db } from "@/lib/db";
import { backoffDelay, MAX_ATTEMPTS, queueRecords, sha256Hex, syncNow } from "@/lib/sync";
import type { TelcoRecord } from "@/lib/validation";

const rec = (i: number): TelcoRecord => ({
  customer_id: `${String(i).padStart(4, "0")}-TESTX`, gender: "Male", senior_citizen: 0, partner: "No", dependents: "No",
  tenure_months: 2, phone_service: "Yes", multiple_lines: "No", internet_service: "DSL", online_security: "No",
  online_backup: "No", device_protection: "No", tech_support: "No", streaming_tv: "No", streaming_movies: "No",
  contract_type: "Month-to-month", paperless_billing: "Yes", payment_method: "Mailed check", monthly_charges: 50, total_charges: 100,
  churned: false,
});
const token = async () => "token-123";

beforeEach(async () => {
  await db.outbox.clear();
  vi.stubGlobal("fetch", vi.fn());
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => true });
});
afterEach(() => vi.unstubAllGlobals());

function respond(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Batch endpoint answers with a fresh response each call; /config.json is "missing" so defaults apply. */
function serve(status: number, body: unknown) {
  vi.mocked(fetch).mockImplementation(async (input) =>
    String(input).endsWith("/config.json") ? new Response("", { status: 404 }) : respond(status, body),
  );
}
const batchCalls = () => vi.mocked(fetch).mock.calls.filter(([u]) => String(u).includes("/ingest/batches"));

describe("queueRecords", () => {
  it("splits into batches of at most 500 with a checksum of the exact payload", async () => {
    const { batches, invalid } = await queueRecords(Array.from({ length: 1201 }, (_, i) => rec(i)), "csv", "big.csv");
    expect(invalid).toEqual([]);
    expect(batches.map((b) => b.records.length)).toEqual([500, 500, 201]);
    for (const b of batches) {
      expect(b.checksum).toBe(await sha256Hex(b.payload));
      expect(JSON.parse(b.payload).batch_id).toBe(b.batch_id);
    }
    expect(await db.outbox.count()).toBe(3);
  });

  it("does not queue invalid rows", async () => {
    const { batches, invalid } = await queueRecords([rec(1), { ...rec(2), monthly_charges: -1 }], "form", "x");
    expect(batches[0]!.records).toHaveLength(1);
    expect(invalid[0]).toMatchObject({ row: 1, field: "monthly_charges" });
  });
});

describe("syncNow", () => {
  it("sends the stored payload with idempotency and checksum headers", async () => {
    const [batch] = (await queueRecords([rec(1)], "form", "one")).batches;
    serve(200, { status: "VALIDATED", outcome: "ACCEPTED", accepted_count: 1, errors: [], conflicts: [] });
    const report = await syncNow(token);
    expect(report).toMatchObject({ sent: 1, accepted: 1, failed: 0 });
    const [, init] = batchCalls()[0]!;
    const headers = init!.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe(batch!.idempotency_key);
    expect(headers["X-Checksum-SHA256"]).toBe(batch!.checksum);
    expect(init!.body).toBe(batch!.payload);
    expect((await db.outbox.get(batch!.batch_id))!.status).toBe("ACCEPTED");
  });

  it("keeps per-row errors and conflicts from a partial result", async () => {
    const [batch] = (await queueRecords([rec(1), rec(2)], "form", "two")).batches;
    serve(200, {
      status: "VALIDATED", outcome: "PARTIAL", accepted_count: 1, errors: [],
      conflicts: [{ customer_id: rec(2).customer_id, server_version: 3, client_version: 1 }],
    });
    await syncNow(token);
    const saved = (await db.outbox.get(batch!.batch_id))!;
    expect(saved.status).toBe("PARTIAL");
    expect(saved.conflicts[0]!.server_version).toBe(3);
  });

  it("retries server errors with backoff and gives up after the attempt limit", async () => {
    const [batch] = (await queueRecords([rec(1)], "form", "flaky")).batches;
    serve(503, { title: "Service Unavailable" });
    await syncNow(token);
    let saved = (await db.outbox.get(batch!.batch_id))!;
    expect(saved.status).toBe("PENDING");
    expect(saved.attempts).toBe(1);
    expect(saved.next_attempt_at).toBeGreaterThan(Date.now());
    for (let i = 1; i < MAX_ATTEMPTS; i++) await syncNow(token, { force: true });
    saved = (await db.outbox.get(batch!.batch_id))!;
    expect(saved.status).toBe("FAILED");
    expect(saved.attempts).toBe(MAX_ATTEMPTS);
  });

  it("does not retry a validation failure", async () => {
    const [batch] = (await queueRecords([rec(1)], "form", "bad")).batches;
    serve(422, { title: "Unprocessable Content", detail: "Idempotency-Key reused" });
    await syncNow(token);
    expect((await db.outbox.get(batch!.batch_id))!.status).toBe("FAILED");
  });

  it("skips when offline", async () => {
    await queueRecords([rec(1)], "form", "x");
    Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
    expect((await syncNow(token)).skipped).toBe("offline");
    expect(batchCalls()).toHaveLength(0);
  });
});

describe("backoffDelay", () => {
  it("grows exponentially with jitter and is capped", () => {
    expect(backoffDelay(1, () => 0)).toBe(1000);
    expect(backoffDelay(1, () => 1)).toBe(2000);
    expect(backoffDelay(4, () => 1)).toBe(16000);
    expect(backoffDelay(20, () => 1)).toBe(300000);
  });
});
