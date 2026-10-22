"use client";

import { useState } from "react";

import { Page } from "@/components/Page";
import { Problem } from "@/components/Problem";
import { EMPTY_RECORD, RecordForm } from "@/components/RecordForm";
import { apiGetCached, apiJson, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { ago } from "@/lib/format";
import { useAsync, useLiveQuery, useOnline } from "@/lib/hooks";
import { queueRecords, syncNow } from "@/lib/sync";
import { validateRecord, type TelcoRecord } from "@/lib/validation";

interface DictionaryEntry {
  column_name: string;
  table_name: string;
  description: string | null;
}

interface ServerCustomer {
  customer_id: string;
  gender: TelcoRecord["gender"];
  senior_citizen: 0 | 1;
  partner: TelcoRecord["partner"];
  dependents: TelcoRecord["dependents"];
  version: number;
  subscription: (Partial<TelcoRecord> & { tenure_months: number }) | null;
}

export default function DataEntryPage() {
  const { getToken, status } = useAuth();
  const online = useOnline();
  const [record, setRecord] = useState<Partial<TelcoRecord>>(EMPTY_RECORD);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "warn" | "bad"; text: string } | null>(null);
  const [lookupId, setLookupId] = useState("");
  const [lookupError, setLookupError] = useState<Error | null>(null);
  const ready = status === "authenticated" || status === "offline";

  // Business descriptions from the data dictionary become field hints (cached for offline use).
  const dict = useAsync(() => apiGetCached<{ items: DictionaryEntry[] }>("/meta/dictionary", getToken), [], ready);
  const hints = Object.fromEntries((dict.data?.items ?? []).map((d) => [d.column_name, d.description ?? ""]));
  const drafts = useLiveQuery(() => db.drafts.orderBy("updated_at").reverse().toArray(), [], []);

  const reset = () => {
    setRecord(EMPTY_RECORD);
    setDraftId(null);
    setShowErrors(false);
  };

  const save = async () => {
    setShowErrors(true);
    const errors = validateRecord(record);
    if (errors.length) {
      setMessage({ tone: "bad", text: "Some fields need attention. Nothing was saved." });
      return;
    }
    await queueRecords([record as TelcoRecord], "form", `Record ${record.customer_id}`);
    if (draftId) await db.drafts.delete(draftId);
    const result = online ? await syncNow(getToken) : null;
    setMessage({
      tone: "ok",
      text: online && result && !result.skipped
        ? `Saved ${record.customer_id} and sent it to the server. Check Sync for the result.`
        : `Saved ${record.customer_id} on this device. It will be sent when you are back online.`,
    });
    reset();
  };

  const saveDraft = async () => {
    const id = draftId ?? crypto.randomUUID();
    await db.drafts.put({ id, record, updated_at: new Date().toISOString() });
    setDraftId(id);
    setMessage({ tone: "ok", text: "Draft saved on this device." });
  };

  const loadExisting = async () => {
    setLookupError(null);
    try {
      const c = await apiJson<ServerCustomer>(`/ingest/customers/${encodeURIComponent(lookupId.trim())}`, { method: "GET" }, getToken);
      const s = c.subscription ?? {};
      setRecord({ ...EMPTY_RECORD, ...s, customer_id: c.customer_id, gender: c.gender, senior_citizen: c.senior_citizen,
                  partner: c.partner, dependents: c.dependents, version: c.version } as Partial<TelcoRecord>);
      setDraftId(null);
      setMessage({ tone: "ok", text: `Loaded ${c.customer_id} (version ${c.version}). Your changes are checked against this version when sent.` });
    } catch (e) {
      setLookupError(e instanceof ApiError && e.status === 404 ? new Error(`No customer ${lookupId} in the operational database.`) : (e as Error));
    }
  };

  return (
    <Page title="Data entry" description="Create or update a customer. Works offline: records are validated here and queued for sync." roles={["data_entry"]}>
      <div className="sidebar-layout" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(240px, 300px)" }}>
        <section className="panel" aria-label="Customer record">
          {record.version ? <span className="pill info">Editing server version {record.version}</span> : <span className="pill">New customer</span>}
          <RecordForm value={record} onChange={setRecord} hints={hints} showErrors={showErrors} lockId={!!record.version} />
          {message && <div className={`notice ${message.tone}`} role="status">{message.text}</div>}
          <div className="btn-row">
            <button type="button" className="btn primary" onClick={() => void save()}>Save record</button>
            <button type="button" className="btn" onClick={() => void saveDraft()}>Save draft</button>
            <button type="button" className="btn" onClick={reset}>Clear form</button>
          </div>
        </section>
        <aside style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <section className="panel">
            <h2>Edit an existing customer</h2>
            <div className="field">
              <label htmlFor="lookup">Customer ID</label>
              <input id="lookup" value={lookupId} onChange={(e) => setLookupId(e.target.value)} placeholder="7590-VHVEG" />
            </div>
            <button type="button" className="btn" disabled={!online || !lookupId.trim()} onClick={() => void loadExisting()}>
              {online ? "Load customer" : "Available when online"}
            </button>
            <Problem error={lookupError} />
          </section>
          <section className="panel">
            <h2>Drafts on this device</h2>
            {drafts.length === 0 ? <p className="small muted">No drafts. Use “Save draft” to keep an unfinished record.</p> : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                {drafts.map((d) => (
                  <li key={d.id} className="btn-row" style={{ justifyContent: "space-between" }}>
                    <span>{d.record.customer_id || "Untitled"} <span className="small muted">{ago(d.updated_at)}</span></span>
                    <span className="btn-row">
                      <button type="button" className="btn small" onClick={() => { setRecord(d.record); setDraftId(d.id); }}>Open</button>
                      <button type="button" className="btn small danger" onClick={() => void db.drafts.delete(d.id)}>Delete</button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </Page>
  );
}
