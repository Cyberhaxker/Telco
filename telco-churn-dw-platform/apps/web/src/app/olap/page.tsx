"use client";

import { useEffect, useMemo, useState } from "react";

import { Chart, type Series } from "@/components/Chart";
import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached, apiPostCached, type CachedResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { downloadText, fmtInt, toCsv } from "@/lib/format";
import { useAsync } from "@/lib/hooks";

type Operation = "rollup" | "drilldown" | "slice" | "dice" | "pivot";
type Source = "current" | "history";

interface Query {
  measures: string[];
  rows: string[];
  columns: string[];
  filters: Record<string, string[]>;
  operation: Operation;
  source: Source;
  limit: number;
}

interface OlapResult {
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
  cached: boolean;
  pivot?: {
    row_keys: string[][];
    column_keys: string[][];
    values: Record<string, (number | null)[][]>;
  };
}

interface DimensionInfo {
  dimensions: Record<string, string[]>;
  history_dimensions: string[];
  measures: string[];
}

const MEASURE_LABEL: Record<string, string> = {
  customer_count: "Customers", churned_count: "Churned", churn_rate_pct: "Churn rate %",
  avg_monthly_charges: "Avg monthly $", sum_total_charges: "Total charges $", avg_tenure_months: "Avg tenure (months)",
  avg_churn_probability: "Avg churn probability",
};
const DRILL_PATH = ["contract_type", "payment_method", "internet_service", "tenure_band"];
const TIME_PATH = ["year", "quarter", "month"];
const label = (d: string) => d.replace(/_/g, " ");

const PRESETS: { name: string; q: Partial<Query> }[] = [
  { name: "Churn by contract", q: { rows: ["contract_type"], columns: [], filters: {}, operation: "drilldown" } },
  { name: "Contract → payment (roll-up)", q: { rows: ["contract_type", "payment_method"], columns: [], filters: {}, operation: "rollup" } },
  { name: "Tenure bands", q: { rows: ["tenure_band"], columns: [], filters: {}, operation: "drilldown" } },
  { name: "Slice: month-to-month", q: { rows: ["payment_method"], columns: [], filters: { contract_type: ["Month-to-month"] }, operation: "slice" } },
  { name: "Dice: e-check, 1–2 yr", q: { rows: ["contract_type"], columns: [], filters: { payment_method: ["Electronic check"], contract_type: ["One year", "Two year"] }, operation: "dice" } },
  { name: "Pivot: contract × internet", q: { rows: ["contract_type"], columns: ["internet_service"], filters: {}, operation: "pivot" } },
  { name: "Time: year → month", q: { rows: ["year", "quarter", "month"], columns: [], filters: {}, operation: "rollup", source: "history" } },
];

const INITIAL: Query = {
  measures: ["customer_count", "churned_count", "churn_rate_pct"], rows: ["contract_type"], columns: [], filters: {},
  operation: "drilldown", source: "current", limit: 1000,
};

export default function OlapPage() {
  const { getToken, status } = useAuth();
  const ready = status === "authenticated" || status === "offline";
  const [q, setQ] = useState<Query>(INITIAL);
  const [chartMeasure, setChartMeasure] = useState("churn_rate_pct");
  const [sliceDim, setSliceDim] = useState("contract_type");
  const dims = useAsync(() => apiGetCached<DimensionInfo>("/analytics/olap/dimensions", getToken), [], ready);
  const result = useAsync<OlapResult>(
    () => apiPostCached<OlapResult>("/analytics/olap/query", q, getToken) as Promise<CachedResult<OlapResult>>,
    [JSON.stringify(q)],
    ready,
  );

  useEffect(() => {
    if (!q.measures.includes(chartMeasure)) setChartMeasure(q.measures[0] ?? "customer_count");
  }, [q.measures, chartMeasure]);

  const available = q.source === "history" ? (dims.data?.history_dimensions ?? TIME_PATH) : Object.keys(dims.data?.dimensions ?? {});
  const members = (d: string) => dims.data?.dimensions[d] ?? [];
  const update = (patch: Partial<Query>) => setQ((prev) => ({ ...prev, ...patch }));

  // ----------------------------------------------------------- operations
  const drillDown = () => {
    const path = q.source === "history" ? TIME_PATH : DRILL_PATH;
    const next = path.find((d) => !q.rows.includes(d) && !q.columns.includes(d)) ?? available.find((d) => !q.rows.includes(d) && !q.columns.includes(d));
    if (next) update({ rows: [...q.rows, next], operation: "drilldown" });
  };
  const rollUp = () => update({ rows: q.operation === "rollup" && q.rows.length > 1 ? q.rows.slice(0, -1) : q.rows, operation: "rollup" });
  const slice = (dim: string, value: string) =>
    update({ filters: { [dim]: [value] }, rows: q.rows.filter((r) => r !== dim).length ? q.rows.filter((r) => r !== dim) : [DRILL_PATH.find((d) => d !== dim) ?? "payment_method"], columns: q.columns.filter((c) => c !== dim), operation: "slice" });
  const pivot = () => {
    if (!q.columns.length) {
      const col = q.rows.length > 1 ? q.rows[q.rows.length - 1]! : (available.find((d) => !q.rows.includes(d)) ?? "internet_service");
      update({ rows: q.rows.length > 1 ? q.rows.slice(0, -1) : q.rows, columns: [col], operation: "pivot" });
    } else {
      update({ rows: q.columns, columns: q.rows, operation: "pivot" });
    }
  };
  const toggleFilter = (dim: string, value: string) => {
    const current = q.filters[dim] ?? [];
    const nextVals = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    const filters = { ...q.filters };
    if (nextVals.length) filters[dim] = nextVals;
    else delete filters[dim];
    update({ filters, operation: Object.keys(filters).length ? "dice" : "drilldown" });
  };
  const toggleMeasure = (m: string) =>
    update({ measures: q.measures.includes(m) ? (q.measures.length > 1 ? q.measures.filter((x) => x !== m) : q.measures) : [...q.measures, m] });
  const removeRow = (d: string) => update({ rows: q.rows.filter((r) => r !== d) });
  const addRow = (d: string) => d && update({ rows: [...q.rows, d] });
  const removeCol = (d: string) => update({ columns: q.columns.filter((r) => r !== d), operation: q.operation === "pivot" ? "drilldown" : q.operation });

  // ----------------------------------------------------------- chart data
  const r = result.data;
  const chart = useMemo(() => {
    if (!r || !r.rows.length) return null;
    const idx = (c: string) => r.columns.indexOf(c);
    const mIdx = idx(chartMeasure);
    if (r.pivot && q.columns.length) {
      const values = r.pivot.values[chartMeasure] ?? [];
      return {
        categories: r.pivot.row_keys.map((k) => k.join(" · ")),
        series: r.pivot.column_keys.map((ck, j): Series => ({ name: ck.join(" · "), values: values.map((row) => row[j] ?? null) })),
      };
    }
    const detail = r.rows.filter((row) => !row.includes("(All)"));
    const rowsForChart = detail.length ? detail : r.rows;
    return {
      categories: rowsForChart.map((row) => q.rows.map((d) => String(row[idx(d)])).join(" · ") || "All customers"),
      series: [{ name: MEASURE_LABEL[chartMeasure] ?? chartMeasure, values: rowsForChart.map((row) => (row[mIdx] as number) ?? null), tone: "signal" as const }],
    };
  }, [r, chartMeasure, q.rows, q.columns.length]);

  const exportCsv = () => r && downloadText(`olap-${q.operation}-${Date.now()}.csv`, toCsv(r.columns, r.rows));

  return (
    <Page
      title="OLAP explorer"
      description="Slice the churn cube by any customer, contract, service or payment dimension."
      roles={["analyst"]}
      actions={
        <>
          <CacheNote fromCache={result.fromCache} fetchedAt={result.fetchedAt} />
          <button type="button" className="btn small" onClick={exportCsv} disabled={!r}>Export CSV</button>
        </>
      }
    >
      <div className="sidebar-layout">
        <aside className="panel" aria-label="Query builder">
          <div className="field">
            <span className="label">Presets</span>
            <div className="chips">
              {PRESETS.map((p) => (
                <button key={p.name} type="button" className="chip" onClick={() => setQ({ ...INITIAL, measures: q.measures, ...p.q } as Query)}>
                  {p.name}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span className="label">Data</span>
            <div className="seg" role="group" aria-label="Source">
              {(["current", "history"] as Source[]).map((s) => (
                <button key={s} type="button" aria-pressed={q.source === s}
                        onClick={() => setQ({ ...INITIAL, measures: q.measures, source: s, rows: s === "history" ? ["year"] : ["contract_type"] })}>
                  {s === "current" ? "Current snapshot" : "Daily history"}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span className="label">Measures</span>
            <div className="chips">
              {Object.keys(MEASURE_LABEL).map((m) => (
                <button key={m} type="button" className="chip" aria-pressed={q.measures.includes(m)} onClick={() => toggleMeasure(m)}>
                  {MEASURE_LABEL[m]}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span className="label">Rows</span>
            <div className="chips">
              {q.rows.map((d) => (
                <button key={d} type="button" className="chip" aria-pressed="true" onClick={() => removeRow(d)} aria-label={`Remove ${label(d)} from rows`}>
                  {label(d)} <span className="x" aria-hidden="true">×</span>
                </button>
              ))}
            </div>
            <select className="input" value="" onChange={(e) => addRow(e.target.value)} aria-label="Add row dimension">
              <option value="">Add a row dimension…</option>
              {available.filter((d) => !q.rows.includes(d) && !q.columns.includes(d)).map((d) => (
                <option key={d} value={d}>{label(d)}</option>
              ))}
            </select>
          </div>
          {q.columns.length > 0 && (
            <div className="field">
              <span className="label">Columns</span>
              <div className="chips">
                {q.columns.map((d) => (
                  <button key={d} type="button" className="chip" aria-pressed="true" onClick={() => removeCol(d)}>
                    {label(d)} <span className="x" aria-hidden="true">×</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {q.source === "current" && (
            <div className="field">
              <span className="label">Slice</span>
              <div className="btn-row">
                <select className="input" style={{ flex: 1 }} value={sliceDim} onChange={(e) => setSliceDim(e.target.value)} aria-label="Slice dimension">
                  {available.map((d) => <option key={d} value={d}>{label(d)}</option>)}
                </select>
                <select className="input" style={{ flex: 1 }} value="" onChange={(e) => e.target.value && slice(sliceDim, e.target.value)} aria-label="Slice value">
                  <option value="">Fix a value…</option>
                  {members(sliceDim).map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
            </div>
          )}
          {q.source === "current" && (
            <details>
              <summary className="label" style={{ cursor: "pointer" }}>Dice filters ({Object.keys(q.filters).length})</summary>
              <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
                {DRILL_PATH.concat(["churn_label", "gender", "senior_citizen"]).map((d) => (
                  <div key={d} className="field">
                    <span className="small">{label(d)}</span>
                    <div className="chips">
                      {members(d).map((v) => (
                        <button key={v} type="button" className="chip" aria-pressed={(q.filters[d] ?? []).includes(v)} onClick={() => toggleFilter(d, v)}>
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}
          {Object.keys(q.filters).length > 0 && (
            <button type="button" className="btn small" onClick={() => update({ filters: {}, operation: "drilldown" })}>Clear filters</button>
          )}
        </aside>

        <section className="panel" aria-live="polite">
          <div className="panel-head">
            <div className="btn-row" role="group" aria-label="OLAP operations">
              <button type="button" className="btn" onClick={rollUp} aria-pressed={q.operation === "rollup"}>Roll up</button>
              <button type="button" className="btn" onClick={drillDown}>Drill down</button>
              <button type="button" className="btn" onClick={pivot} aria-pressed={q.operation === "pivot"}>Pivot</button>
              <span className="pill info">{q.operation}</span>
              {Object.entries(q.filters).map(([d, v]) => (
                <span key={d} className="pill">{label(d)} = {v.join(" | ")}</span>
              ))}
            </div>
            {r && <span className="small muted num">{fmtInt(r.row_count)} rows · {r.elapsed_ms} ms{r.truncated ? " · truncated" : ""}</span>}
          </div>
          <Problem error={r ? null : result.error} />
          {result.loading && !r && <div className="empty">Running query…</div>}
          {r && chart && (
            <>
              <div className="btn-row">
                <label className="small" htmlFor="chart-measure">Chart</label>
                <select id="chart-measure" className="input" style={{ width: "auto" }} value={chartMeasure} onChange={(e) => setChartMeasure(e.target.value)}>
                  {q.measures.map((m) => <option key={m} value={m}>{MEASURE_LABEL[m]}</option>)}
                </select>
              </div>
              <Chart label={`${MEASURE_LABEL[chartMeasure]} by ${q.rows.map(label).join(", ")}`} tall
                     unit={chartMeasure === "churn_rate_pct" ? "%" : ""} categories={chart.categories} series={chart.series} />
            </>
          )}
          {r && r.pivot && q.columns.length > 0 ? (
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Pivot of {MEASURE_LABEL[chartMeasure]}</caption>
                <thead>
                  <tr>
                    <th>{q.rows.map(label).join(" · ")} \ {q.columns.map(label).join(" · ")}</th>
                    {r.pivot.column_keys.map((ck) => <th key={ck.join("|")} className="num">{ck.join(" · ")}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {r.pivot.row_keys.map((rk, i) => (
                    <tr key={rk.join("|")}>
                      <td>{rk.join(" · ")}</td>
                      {(r.pivot!.values[chartMeasure]?.[i] ?? []).map((v, j) => <td key={j} className="num">{v ?? "—"}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : r ? (
            <div className="table-wrap">
              <table>
                <caption className="sr-only">OLAP result</caption>
                <thead>
                  <tr>{r.columns.filter((c) => c !== "grouping_level").map((c) => (
                    <th key={c} className={q.measures.includes(c) ? "num" : undefined}>{MEASURE_LABEL[c] ?? label(c)}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {r.rows.length === 0 ? (
                    <tr><td colSpan={r.columns.length} className="empty">No customers match these filters.</td></tr>
                  ) : r.rows.map((row, i) => (
                    <tr key={i} className={row.includes("(All)") ? "subtotal" : undefined}>
                      {r.columns.map((c, j) => c === "grouping_level" ? null : (
                        <td key={c} className={q.measures.includes(c) ? "num" : undefined}>{row[j] ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </Page>
  );
}
