"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached, apiJson, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtInt, fmtMoney, fmtProb, fmtWhen } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { ENUMS } from "@/lib/validation";

interface Factor {
  feature: string;
  value: string | number | null;
  contribution: number;
}

interface Prediction {
  customer_id: string;
  churn_probability: number | null;
  predicted_label: number | null;
  risk_band: "high" | "medium" | "low" | null;
  top_factors: Factor[] | null;
  model_version: string | null;
  scored_at: string | null;
  contract_type: string;
  payment_method: string;
  internet_service: string;
  tenure_months: number;
  tenure_band: string;
  monthly_charges: number;
  churn_label: string;
  [key: string]: unknown;
}

interface PageOf<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

const RISK_TONE = { high: "bad", medium: "warn", low: "ok" } as const;
const PAGE = 50;

function Probability({ p }: { p: number | null }) {
  return (
    <span className="prob">
      <span className="num">{fmtProb(p)}</span>
      <span className="bar" aria-hidden="true"><span style={{ width: `${Math.round((p ?? 0) * 100)}%` }} /></span>
    </span>
  );
}

function Factors({ factors }: { factors: Factor[] }) {
  const max = Math.max(0.01, ...factors.map((f) => Math.abs(f.contribution)));
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {factors.map((f) => {
        const pct = (Math.abs(f.contribution) / max) * 50;
        const up = f.contribution > 0;
        return (
          <div key={f.feature} className="factor">
            <span>
              {f.feature.replace(/_/g, " ")} <span className="muted">= {String(f.value ?? "—")}</span>
            </span>
            <span className="track" aria-hidden="true">
              <span style={{ left: up ? "50%" : `${50 - pct}%`, width: `${pct}%`, background: up ? "var(--signal)" : "var(--primary)" }} />
            </span>
            <span className={`num small ${up ? "" : "muted"}`}>{up ? "+" : ""}{(f.contribution * 100).toFixed(1)} pt</span>
          </div>
        );
      })}
    </div>
  );
}

const PROFILE_DEFAULT = {
  tenure_months: 4, monthly_charges: 89.5, total_charges: 358, partner: "No", dependents: "No", phone_service: "Yes",
  multiple_lines: "No", internet_service: "Fiber optic", online_security: "No", online_backup: "No", device_protection: "No",
  tech_support: "No", streaming_tv: "Yes", streaming_movies: "No", contract_type: "Month-to-month", paperless_billing: "Yes",
  payment_method: "Electronic check",
};

function WhatIf() {
  const { getToken } = useAuth();
  const [profile, setProfile] = useState<Record<string, string | number>>(PROFILE_DEFAULT);
  const [result, setResult] = useState<{ churn_probability: number; risk_band: string; top_factors: Factor[]; model: { version: string; algorithm: string } } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | number) => setProfile((p) => ({ ...p, [k]: v }));
  const choice = (k: string, options: readonly string[]) => (
    <div className="field" key={k}>
      <label htmlFor={`wi-${k}`}>{k.replace(/_/g, " ")}</label>
      <select id={`wi-${k}`} value={String(profile[k])} onChange={(e) => set(k, e.target.value)}>
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  );
  const score = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await apiJson("/analytics/predict", { method: "POST", body: JSON.stringify(profile) }, getToken));
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>What-if scoring</h2>
        <span className="small muted">Score a hypothetical customer with the champion model</span>
      </div>
      <div className="form-grid">
        {(["tenure_months", "monthly_charges", "total_charges"] as const).map((k) => (
          <div className="field" key={k}>
            <label htmlFor={`wi-${k}`}>{k.replace(/_/g, " ")}</label>
            <input id={`wi-${k}`} type="number" min={0} step={k === "tenure_months" ? 1 : 0.01} value={profile[k]}
                   onChange={(e) => set(k, Number(e.target.value))} />
          </div>
        ))}
        {choice("contract_type", ENUMS.contract_type)}
        {choice("payment_method", ENUMS.payment_method)}
        {choice("internet_service", ENUMS.internet_service)}
        {choice("online_security", ENUMS.addon)}
        {choice("tech_support", ENUMS.addon)}
        {choice("paperless_billing", ENUMS.yesNo)}
      </div>
      <div className="btn-row">
        <button type="button" className="btn primary" onClick={() => void score()} disabled={busy}>{busy ? "Scoring…" : "Score profile"}</button>
        {result && (
          <span className={`pill ${RISK_TONE[result.risk_band as keyof typeof RISK_TONE] ?? ""}`}>
            {fmtProb(result.churn_probability)} · {result.risk_band} risk · model v{result.model.version} ({result.model.algorithm})
          </span>
        )}
      </div>
      <Problem error={error instanceof ApiError && error.status === 503 ? new Error("No trained model is available yet. Run the training pipeline first.") : error} />
      {result && <Factors factors={result.top_factors} />}
    </section>
  );
}

export default function PredictionsPage() {
  const { getToken, status } = useAuth();
  const ready = status === "authenticated" || status === "offline";
  const [risk, setRisk] = useState<"high" | "medium" | "low" | "">("high");
  const [contract, setContract] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const c = new URLSearchParams(window.location.search).get("customer");
    if (c) setSelected(c);
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (selected) url.searchParams.set("customer", selected);
    else url.searchParams.delete("customer");
    window.history.replaceState(null, "", url);
  }, [selected]);

  const qs = new URLSearchParams({ limit: String(PAGE), offset: String(offset), ...(risk ? { risk } : {}), ...(contract ? { contract_type: contract } : {}) });
  const list = useAsync(() => apiGetCached<PageOf<Prediction>>(`/analytics/predictions?${qs}`, getToken), [qs.toString()], ready);
  const detail = useAsync(() => apiGetCached<Prediction>(`/analytics/predictions/${encodeURIComponent(selected ?? "")}`, getToken), [selected], ready && !!selected);

  const columns = useMemo<ColumnDef<Prediction, unknown>[]>(() => [
    { accessorKey: "customer_id", header: "Customer" },
    { accessorKey: "churn_probability", header: "Churn probability", cell: (c) => <Probability p={c.getValue() as number | null} /> },
    { accessorKey: "risk_band", header: "Risk", cell: (c) => { const r = c.getValue() as Prediction["risk_band"]; return r ? <span className={`pill ${RISK_TONE[r]}`}>{r}</span> : "—"; } },
    { accessorKey: "contract_type", header: "Contract" },
    { accessorKey: "tenure_months", header: "Tenure (mo)" },
    { accessorKey: "monthly_charges", header: "Monthly", cell: (c) => fmtMoney(c.getValue() as number) },
    { accessorKey: "payment_method", header: "Payment" },
  ], []);

  const d = detail.data;
  return (
    <Page title="Predictions" description="Active customers ranked by predicted churn probability from the champion model." roles={["analyst"]}
          actions={<CacheNote fromCache={list.fromCache} fetchedAt={list.fetchedAt} />}>
      <section className="panel">
        <div className="btn-row">
          <div className="seg" role="group" aria-label="Risk band">
            {(["high", "medium", "low", ""] as const).map((r) => (
              <button key={r || "all"} type="button" aria-pressed={risk === r} onClick={() => { setRisk(r); setOffset(0); }}>
                {r ? `${r[0]!.toUpperCase()}${r.slice(1)} risk` : "All"}
              </button>
            ))}
          </div>
          <label className="sr-only" htmlFor="contract-filter">Contract</label>
          <select id="contract-filter" className="input" style={{ width: "auto" }} value={contract} onChange={(e) => { setContract(e.target.value); setOffset(0); }}>
            <option value="">All contracts</option>
            {ENUMS.contract_type.map((c) => <option key={c}>{c}</option>)}
          </select>
          {list.data && <span className="small muted num">{fmtInt(list.data.total)} customers</span>}
        </div>
        <Problem error={list.data ? null : list.error} />
        <div className="grid-2" style={{ gridTemplateColumns: selected ? undefined : "1fr" }}>
          <div style={{ display: "grid", gap: 8, minWidth: 0 }}>
            <DataTable caption="Customers by churn probability" data={list.data?.items ?? []} columns={columns}
                       numericColumns={["churn_probability", "tenure_months", "monthly_charges"]}
                       onRowClick={(row) => setSelected(row.customer_id)} isSelected={(row) => row.customer_id === selected}
                       empty={list.loading ? "Loading…" : "No customers in this risk band."} />
            {list.data && list.data.total > PAGE && (
              <div className="btn-row">
                <button type="button" className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <span className="small muted num">{offset + 1}–{Math.min(offset + PAGE, list.data.total)} of {fmtInt(list.data.total)}</span>
                <button type="button" className="btn small" disabled={offset + PAGE >= list.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            )}
          </div>
          {selected && (
            <aside className="panel" aria-label="Customer detail">
              <div className="panel-head">
                <h2>{selected}</h2>
                <button type="button" className="btn small" onClick={() => setSelected(null)}>Close</button>
              </div>
              <Problem error={d ? null : detail.error} />
              {d && (
                <>
                  <div className="btn-row">
                    <Probability p={d.churn_probability} />
                    {d.risk_band && <span className={`pill ${RISK_TONE[d.risk_band]}`}>{d.risk_band} risk</span>}
                    {d.churn_label === "Yes" && <span className="pill">Already churned</span>}
                  </div>
                  <h3>Top factors</h3>
                  {d.top_factors?.length ? <Factors factors={d.top_factors} /> : <p className="muted">Not scored yet.</p>}
                  <p className="small muted">{String(d.note ?? "")}</p>
                  <dl className="kv">
                    <dt>Contract</dt><dd>{d.contract_type} · paperless {String(d.paperless_billing)}</dd>
                    <dt>Payment</dt><dd>{d.payment_method}</dd>
                    <dt>Internet</dt><dd>{d.internet_service}</dd>
                    <dt>Tenure</dt><dd className="num">{d.tenure_months} months ({d.tenure_band})</dd>
                    <dt>Charges</dt><dd className="num">{fmtMoney(d.monthly_charges)} / month · {fmtMoney(d.total_charges as number)} total</dd>
                    <dt>Scored</dt><dd>{fmtWhen(d.scored_at)} · model v{d.model_version ?? "—"}</dd>
                  </dl>
                </>
              )}
            </aside>
          )}
        </div>
      </section>
      <WhatIf />
    </Page>
  );
}
