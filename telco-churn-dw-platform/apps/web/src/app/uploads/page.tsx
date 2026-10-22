"use client";

import Link from "next/link";
import Papa from "papaparse";
import { useState } from "react";

import { Page } from "@/components/Page";
import { detectLayout, RECORD_FIELDS, rowToRecord, type CsvLayout } from "@/lib/csv";
import type { RowError } from "@/lib/db";
import { fmtInt } from "@/lib/format";
import { MAX_BATCH_RECORDS, queueRecords } from "@/lib/sync";
import { validateRecord, type TelcoRecord } from "@/lib/validation";

interface Parsed {
  fileName: string;
  layout: CsvLayout;
  records: Record<string, unknown>[];
  errors: Map<number, RowError[]>;
}

const MAX_BYTES = 10 * 1024 * 1024;
const PREVIEW = 100;

export default function UploadsPage() {
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [queued, setQueued] = useState<{ batches: number; records: number } | null>(null);
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [busy, setBusy] = useState(false);

  const onFile = (file: File | undefined) => {
    setProblem(null);
    setQueued(null);
    setParsed(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setProblem(`${file.name} is ${(file.size / 1048576).toFixed(1)} MB. The limit is 10 MB; split the file and upload the parts.`);
      return;
    }
    setBusy(true);
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (res) => {
        setBusy(false);
        const layout = detectLayout(res.meta.fields ?? []);
        if (layout === "unknown") {
          setProblem("The header does not match the IBM Telco layout (customerID, gender, …) or the record layout (customer_id, gender, …).");
          return;
        }
        const records = res.data.map((row) => rowToRecord(row, layout));
        const errors = new Map<number, RowError[]>();
        records.forEach((r, i) => {
          const e = validateRecord(r, i);
          if (e.length) errors.set(i, e);
        });
        setParsed({ fileName: file.name, layout, records, errors });
      },
      error: (err) => {
        setBusy(false);
        setProblem(`Could not read the file: ${err.message}`);
      },
    });
  };

  const queue = async () => {
    if (!parsed) return;
    setBusy(true);
    const valid = parsed.records.filter((_, i) => !parsed.errors.has(i)) as unknown as TelcoRecord[];
    const result = await queueRecords(valid, "csv", parsed.fileName);
    setQueued({ batches: result.batches.length, records: valid.length });
    setBusy(false);
  };

  const validCount = parsed ? parsed.records.length - parsed.errors.size : 0;
  const rows = parsed
    ? parsed.records.map((r, i) => ({ i, r, e: parsed.errors.get(i) })).filter((x) => !onlyErrors || x.e).slice(0, PREVIEW)
    : [];

  return (
    <Page title="CSV uploads" description="Check a CSV on this device, then queue the valid rows for sync in batches of 500." roles={["data_entry"]}>
      <section className="panel">
        <div className="field">
          <label htmlFor="csv">CSV file (IBM Telco layout or record layout, up to 10 MB)</label>
          <input id="csv" type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0])} />
        </div>
        {busy && <p className="muted">Reading file…</p>}
        {problem && <div className="notice bad" role="alert">{problem}</div>}
        {parsed && (
          <>
            <div className="kpis">
              <div className="kpi"><span className="label">Rows</span><span className="value">{fmtInt(parsed.records.length)}</span><span className="sub">{parsed.layout === "ibm" ? "IBM Telco layout" : "Record layout"}</span></div>
              <div className="kpi"><span className="label">Valid</span><span className="value">{fmtInt(validCount)}</span><span className="sub">{Math.ceil(validCount / MAX_BATCH_RECORDS)} batch(es) of up to {MAX_BATCH_RECORDS}</span></div>
              <div className="kpi signal"><span className="label">With errors</span><span className="value">{fmtInt(parsed.errors.size)}</span><span className="sub">Not queued; fix and re-upload</span></div>
            </div>
            <div className="btn-row">
              <button type="button" className="btn primary" onClick={() => void queue()} disabled={busy || validCount === 0 || !!queued}>
                Queue {fmtInt(validCount)} valid rows
              </button>
              <label className="small"><input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> Show only rows with errors</label>
            </div>
            {queued && (
              <div className="notice ok" role="status">
                Queued {fmtInt(queued.records)} records in {queued.batches} batch(es). <Link href="/sync">Follow progress on the Sync page.</Link>
              </div>
            )}
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Preview of the first {PREVIEW} rows</caption>
                <thead>
                  <tr><th className="num">Row</th><th>Status</th>{RECORD_FIELDS.slice(0, 8).map((f) => <th key={f}>{f.replace(/_/g, " ")}</th>)}<th>Problems</th></tr>
                </thead>
                <tbody>
                  {rows.map(({ i, r, e }) => (
                    <tr key={i}>
                      <td className="num">{i + 2}</td>
                      <td>{e ? <span className="pill bad">Error</span> : <span className="pill ok">OK</span>}</td>
                      {RECORD_FIELDS.slice(0, 8).map((f) => <td key={f}>{String(r[f] ?? "")}</td>)}
                      <td className="small">{e?.map((x) => `${x.field}: ${x.message}`).join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Row numbers match the line in the file (line 1 is the header). Showing up to {PREVIEW} rows.</p>
          </>
        )}
      </section>
    </Page>
  );
}
