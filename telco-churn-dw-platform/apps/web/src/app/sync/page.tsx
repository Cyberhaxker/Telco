"use client";

import { useState } from "react";

import { Page } from "@/components/Page";
import { useAuth } from "@/lib/auth";
import { db, type OutboxBatch } from "@/lib/db";
import { ago, fmtInt } from "@/lib/format";
import { useLiveQuery, useOnline } from "@/lib/hooks";
import { MAX_ATTEMPTS, queueRecords, retryBatch, syncNow, type SyncReport } from "@/lib/sync";
import type { TelcoRecord } from "@/lib/validation";

const TONE: Record<OutboxBatch["status"], string> = {
  PENDING: "signal", SENDING: "info", ACCEPTED: "ok", PARTIAL: "warn", REJECTED: "bad", FAILED: "bad",
};
const STATUS_TEXT: Record<OutboxBatch["status"], string> = {
  PENDING: "Waiting", SENDING: "Sending", ACCEPTED: "Accepted", PARTIAL: "Partly accepted", REJECTED: "Rejected", FAILED: "Failed",
};

function BatchCard({ batch }: { batch: OutboxBatch }) {
  const [open, setOpen] = useState(batch.status !== "ACCEPTED");
  const errorRows = new Map<number, string[]>();
  for (const e of batch.errors) errorRows.set(e.row, [...(errorRows.get(e.row) ?? []), `${e.field}: ${e.message}`]);

  const resolveConflict = async (customerId: string, keep: "server" | "mine") => {
    const conflict = batch.conflicts.find((c) => c.customer_id === customerId);
    if (!conflict) return;
    if (keep === "mine") {
      const mine = batch.records.find((r) => r.customer_id === customerId);
      if (mine) await queueRecords([{ ...mine, version: conflict.server_version }], batch.source, `${customerId} (conflict resolved: kept mine)`);
    }
    await db.outbox.update(batch.batch_id, { conflicts: batch.conflicts.filter((c) => c.customer_id !== customerId) });
  };

  const requeueFixable = async () => {
    // Rejected rows are returned to the form via drafts so they can be corrected.
    const rows = [...errorRows.keys()].map((i) => batch.records[i]).filter(Boolean) as TelcoRecord[];
    await db.drafts.bulkPut(rows.map((r) => ({ id: crypto.randomUUID(), record: r, updated_at: new Date().toISOString() })));
    await db.outbox.update(batch.batch_id, { errors: [] });
  };

  return (
    <article className="panel">
      <div className="panel-head">
        <div style={{ display: "grid", gap: 2 }}>
          <h3>{batch.label}</h3>
          <span className="small muted">
            {fmtInt(batch.records.length)} records · {batch.source === "csv" ? "CSV" : "Form"} · created {ago(batch.created_at)} · attempt {batch.attempts}/{MAX_ATTEMPTS}
          </span>
        </div>
        <div className="btn-row">
          <span className={`pill ${TONE[batch.status]}`}>{STATUS_TEXT[batch.status]}</span>
          {batch.accepted_count > 0 && <span className="pill ok">{fmtInt(batch.accepted_count)} accepted</span>}
          {batch.errors.length > 0 && <span className="pill bad">{errorRows.size} rows rejected</span>}
          {batch.conflicts.length > 0 && <span className="pill warn">{batch.conflicts.length} conflicts</span>}
          <button type="button" className="btn small" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide" : "Details"}</button>
        </div>
      </div>
      {open && (
        <>
          {batch.last_error && <div className="notice bad">{batch.last_error}{batch.status === "PENDING" && batch.next_attempt_at ? ` · next try ${new Date(batch.next_attempt_at).toLocaleTimeString()}` : ""}</div>}
          {errorRows.size > 0 && (
            <>
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Rejected rows</caption>
                  <thead><tr><th className="num">Row</th><th>Customer</th><th>Problems</th></tr></thead>
                  <tbody>
                    {[...errorRows.entries()].map(([row, msgs]) => (
                      <tr key={row}><td className="num">{row + 1}</td><td>{String(batch.records[row]?.customer_id ?? "—")}</td><td className="small">{msgs.join("; ")}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div><button type="button" className="btn small" onClick={() => void requeueFixable()}>Move rejected rows to drafts for correction</button></div>
            </>
          )}
          {batch.conflicts.map((c) => (
            <div key={c.customer_id} className="notice warn" style={{ display: "grid", gap: 8 }}>
              <div>
                <strong>{c.customer_id}</strong> changed on the server (server version {c.server_version}, you edited version {c.client_version}).
                The server version was kept.
              </div>
              {c.server_record && (
                <span className="small">
                  Server now has: {c.server_record.contract_type} · {c.server_record.payment_method} · ${c.server_record.monthly_charges}/month · tenure {c.server_record.tenure_months}
                </span>
              )}
              <div className="btn-row">
                <button type="button" className="btn small" onClick={() => void resolveConflict(c.customer_id, "server")}>Keep server version</button>
                <button type="button" className="btn small" onClick={() => void resolveConflict(c.customer_id, "mine")}>Overwrite with my version</button>
              </div>
            </div>
          ))}
          <div className="btn-row">
            {(batch.status === "FAILED" || batch.status === "PENDING") && (
              <button type="button" className="btn small" onClick={() => void retryBatch(batch.batch_id)}>Retry now</button>
            )}
            <button type="button" className="btn small danger" onClick={() => void db.outbox.delete(batch.batch_id)}>
              {batch.status === "ACCEPTED" ? "Clear" : "Discard batch"}
            </button>
          </div>
        </>
      )}
    </article>
  );
}

export default function SyncPage() {
  const { getToken, status } = useAuth();
  const online = useOnline();
  const batches = useLiveQuery(() => db.outbox.orderBy("created_at").reverse().toArray(), [], [] as OutboxBatch[]);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = batches.filter((b) => b.status === "PENDING" || b.status === "SENDING").length;

  const run = async () => {
    setBusy(true);
    setReport(await syncNow(getToken, { force: true }));
    setBusy(false);
  };
  const clearAccepted = () => void db.outbox.where("status").equals("ACCEPTED").delete();

  return (
    <Page
      title="Sync"
      description="Batches saved on this device and what the server said about them."
      roles={["data_entry", "data_steward"]}
      actions={
        <>
          <button type="button" className="btn primary" onClick={() => void run()} disabled={busy || !online || status !== "authenticated"}>
            {busy ? "Syncing…" : "Sync now"}
          </button>
          <button type="button" className="btn" onClick={clearAccepted}>Clear accepted</button>
        </>
      }
    >
      {!online && <div className="notice warn">Offline. {pending} batch(es) will be sent automatically when the connection returns.</div>}
      {online && status !== "authenticated" && <div className="notice warn">Sign in again to send queued batches.</div>}
      {report && (
        <div className={`notice ${report.failed ? "warn" : "ok"}`} role="status">
          {report.skipped
            ? `Nothing sent (${report.skipped === "offline" ? "offline" : "not signed in"}).`
            : `Sent ${report.sent} batch(es): ${fmtInt(report.accepted)} records accepted${report.failed ? `, ${report.failed} batch(es) will be retried` : ""}.`}
        </div>
      )}
      {batches.length === 0 ? (
        <div className="panel empty">Nothing queued. Records you save on Data entry or CSV uploads appear here until the server accepts them.</div>
      ) : (
        batches.map((b) => <BatchCard key={b.batch_id} batch={b} />)
      )}
    </Page>
  );
}
