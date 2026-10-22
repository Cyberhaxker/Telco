"use client";

import Link from "next/link";
import { useMemo } from "react";

import { Chart } from "@/components/Chart";
import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtInt, fmtMoney, fmtPct, fmtWhen } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { hasRole } from "@/lib/roles";

interface Breakdown {
  label: string;
  customers: number;
  churned: number;
  churn_rate_pct: number;
}

interface Kpis {
  total_customers: number;
  churned_customers: number;
  churn_rate_pct: number;
  avg_monthly_charges: number;
  avg_churn_probability: number | null;
  high_risk_active_customers: number;
  medium_risk_active_customers: number;
  snapshot_date: string | null;
  scored_at: string | null;
  high_risk_threshold: number;
  churn_by_contract: Breakdown[];
  churn_by_tenure_band: Breakdown[];
  churn_by_payment_method: Breakdown[];
}

function BreakdownTable({ rows, caption }: { rows: Breakdown[]; caption: string }) {
  return (
    <div className="table-wrap" style={{ maxHeight: "none" }}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>Segment</th>
            <th className="num">Customers</th>
            <th className="num">Churned</th>
            <th className="num">Churn rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="num">{fmtInt(r.customers)}</td>
              <td className="num">{fmtInt(r.churned)}</td>
              <td className="num">{fmtPct(r.churn_rate_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardPage() {
  const { getToken, status, profile, getRegistrationUrl } = useAuth();
  const ready = status === "authenticated" || status === "offline";
  const kpis = useAsync(() => apiGetCached<Kpis>("/analytics/kpis", getToken), [], ready);
  const k = kpis.data;

  const handleRegister = async () => {
    const url = await getRegistrationUrl();
    window.location.href = url;
  };

  const charts = useMemo(() => {
    if (!k) return null;
    const mk = (rows: Breakdown[]) => ({
      categories: rows.map((r) => r.label),
      series: [{ name: "Churn rate", values: rows.map((r) => r.churn_rate_pct), tone: "signal" as const }],
    });
    return { contract: mk(k.churn_by_contract), tenure: mk(k.churn_by_tenure_band), payment: mk(k.churn_by_payment_method) };
  }, [k]);
  const isAnalyst = hasRole(profile?.roles ?? [], ["analyst"]);

  return (
    <Page
      title="Dashboard"
      description="Churn across the current customer base, from the latest warehouse refresh."
      roles={["viewer", "analyst"]}
      actions={
        <>
          <CacheNote fromCache={kpis.fromCache} fetchedAt={kpis.fetchedAt} />
          <button type="button" className="btn small" onClick={kpis.reload} disabled={kpis.loading}>
            {kpis.loading ? "Refreshing…" : "Refresh"}
          </button>
          {!ready && (
            <button type="button" className="btn small secondary" onClick={handleRegister}>
              Register New Account
            </button>
          )}
        </>
      }
    >
      <Problem error={k ? null : kpis.error} />
      {!k && kpis.loading && <div className="empty">Loading churn KPIs…</div>}
      {k && charts && (
        <>
          <section className="kpis" aria-label="Key figures">
            <div className="kpi">
              <span className="label">Customers</span>
              <span className="value">{fmtInt(k.total_customers)}</span>
              <span className="sub">Snapshot {k.snapshot_date ?? "—"}</span>
            </div>
            <div className="kpi signal">
              <span className="label">Churn rate</span>
              <span className="value">{fmtPct(k.churn_rate_pct)}</span>
              <span className="sub">{fmtInt(k.churned_customers)} customers left</span>
              <div className="meter" aria-hidden="true"><span style={{ width: `${Math.min(100, k.churn_rate_pct)}%` }} /></div>
            </div>
            <div className="kpi">
              <span className="label">High-risk active customers</span>
              <span className="value">{fmtInt(k.high_risk_active_customers)}</span>
              <span className="sub">
                Probability ≥ {Math.round(k.high_risk_threshold * 100)}% · {fmtInt(k.medium_risk_active_customers)} medium
              </span>
            </div>
            <div className="kpi">
              <span className="label">Avg monthly charges</span>
              <span className="value">{fmtMoney(k.avg_monthly_charges)}</span>
              <span className="sub">Scored {fmtWhen(k.scored_at)}</span>
            </div>
          </section>

          <div className="grid-2">
            <section className="panel">
              <div className="panel-head">
                <h2>Churn rate by contract</h2>
                <span className="small muted">Month-to-month customers leave most often</span>
              </div>
              <Chart label="Churn rate by contract type" unit="%" {...charts.contract} />
              <BreakdownTable rows={k.churn_by_contract} caption="Churn by contract type" />
            </section>
            <section className="panel">
              <div className="panel-head">
                <h2>Churn rate by tenure</h2>
                <span className="small muted">Months with the company</span>
              </div>
              <Chart label="Churn rate by tenure band in months" unit="%" {...charts.tenure} />
              <BreakdownTable rows={k.churn_by_tenure_band} caption="Churn by tenure band" />
            </section>
          </div>
          <section className="panel">
            <div className="panel-head">
              <h2>Churn rate by payment method</h2>
              {isAnalyst && <Link href="/olap" className="small">Explore in OLAP →</Link>}
            </div>
            <Chart label="Churn rate by payment method" unit="%" horizontal {...charts.payment} />
          </section>
        </>
      )}
    </Page>
  );
}
