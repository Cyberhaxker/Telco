"use client";

import { useMemo, useState } from "react";

import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached, apiJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtInt, fmtWhen } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { hasRole } from "@/lib/roles";

interface DictEntry {
  column_id: number;
  schema_name: string;
  table_name: string;
  column_name: string;
  data_type: string;
  business_name: string | null;
  description: string | null;
  is_pii: boolean;
  is_protected_attribute: boolean;
  allowed_values: string[] | null;
  example_value: string | null;
  updated_by: string;
  updated_at: string;
  version: number;
}
interface Dataset { dataset_id: string; name: string; layer: string; schema_name: string; table_name: string; description: string; row_count: number | null; last_refreshed_at: string | null; refresh_schedule: string }
interface DqRun { run_id: string; source: string; status: string; total: number; passed: number; failed: number; warned: number; started_at: string }
interface DqResult { test_name: string; model: string | null; status: string; failures: number | null; message: string | null }
interface LineageNode { unique_id: string; name: string; resource_type: string; relation: string; materialized: string | null }
interface LineageGraph { model: LineageNode; upstream: string[]; downstream: string[]; nodes: LineageNode[] }

type Tab = "dictionary" | "datasets" | "lineage" | "quality";
const STATUS_TONE: Record<string, string> = { pass: "ok", warn: "warn", fail: "bad", error: "bad" };
const LINEAGE_MODELS = ["fact_customer_churn", "dim_customer", "int_customer_current", "mv_churn_cube", "ml_features"];

function EditEntry({ entry, onSaved }: { entry: DictEntry; onSaved: () => void }) {
  const { getToken } = useAuth();
  const [draft, setDraft] = useState(entry);
  const [error, setError] = useState<Error | null>(null);
  const save = async () => {
    setError(null);
    try {
      await apiJson(`/meta/dictionary/${entry.column_id}`, {
        method: "PUT",
        body: JSON.stringify({
          business_name: draft.business_name, description: draft.description, is_pii: draft.is_pii,
          is_protected_attribute: draft.is_protected_attribute, allowed_values: draft.allowed_values,
          example_value: draft.example_value, version: entry.version,
        }),
      }, getToken);
      onSaved();
    } catch (e) {
      setError(e as Error);
    }
  };
  return (
    <div className="panel" style={{ background: "var(--surface-2)" }}>
      <h3>Edit {entry.table_name}.{entry.column_name}</h3>
      <div className="form-grid">
        <div className="field"><label htmlFor="bn">Business name</label><input id="bn" value={draft.business_name ?? ""} onChange={(e) => setDraft({ ...draft, business_name: e.target.value })} /></div>
        <div className="field"><label htmlFor="ex">Example value</label><input id="ex" value={draft.example_value ?? ""} onChange={(e) => setDraft({ ...draft, example_value: e.target.value })} /></div>
      </div>
      <div className="field"><label htmlFor="desc">Description</label><textarea id="desc" rows={3} value={draft.description ?? ""} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></div>
      <div className="btn-row">
        <label className="small"><input type="checkbox" checked={draft.is_pii} onChange={(e) => setDraft({ ...draft, is_pii: e.target.checked })} /> Personal data</label>
        <label className="small"><input type="checkbox" checked={draft.is_protected_attribute} onChange={(e) => setDraft({ ...draft, is_protected_attribute: e.target.checked })} /> Protected attribute</label>
      </div>
      <Problem error={error} />
      <div className="btn-row"><button type="button" className="btn primary" onClick={() => void save()}>Save</button></div>
    </div>
  );
}

export default function MetadataPage() {
  const { getToken, status, profile } = useAuth();
  const ready = status === "authenticated" || status === "offline";
  const [tab, setTab] = useState<Tab>("dictionary");
  const [table, setTable] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [model, setModel] = useState("fact_customer_churn");
  const [run, setRun] = useState<string | null>(null);
  const isSteward = hasRole(profile?.roles ?? [], ["data_steward"]);

  const dict = useAsync(() => apiGetCached<{ items: DictEntry[] }>("/meta/dictionary", getToken), [], ready && tab === "dictionary");
  const datasets = useAsync(() => apiGetCached<{ items: Dataset[] }>("/meta/datasets?limit=200", getToken), [], ready && tab === "datasets");
  const lineage = useAsync(() => apiGetCached<LineageGraph>(`/meta/lineage/${model}`, getToken), [model], ready && tab === "lineage");
  const runs = useAsync(() => apiGetCached<{ items: DqRun[] }>("/meta/quality/runs?limit=30", getToken), [], ready && tab === "quality");
  const runDetail = useAsync(() => apiGetCached<DqRun & { results: DqResult[] }>(`/meta/quality/runs/${run}`, getToken), [run], ready && !!run);

  const tables = useMemo(() => [...new Set((dict.data?.items ?? []).map((d) => `${d.schema_name}.${d.table_name}`))], [dict.data]);
  const entries = (dict.data?.items ?? []).filter((d) => !table || `${d.schema_name}.${d.table_name}` === table);
  const byId = useMemo(() => Object.fromEntries((lineage.data?.nodes ?? []).map((n) => [n.unique_id, n])), [lineage.data]);
  const current = { dictionary: dict, datasets, lineage, quality: runs }[tab];

  return (
    <Page title="Metadata" description="What each table and column means, where data comes from, and how the latest quality checks went."
          roles={["viewer", "data_steward", "analyst", "data_entry"]} actions={<CacheNote fromCache={current.fromCache} fetchedAt={current.fetchedAt} />}>
      <div className="seg" role="tablist" aria-label="Metadata views">
        {(["dictionary", "datasets", "lineage", "quality"] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {{ dictionary: "Data dictionary", datasets: "Datasets", lineage: "Lineage", quality: "Data quality" }[t]}
          </button>
        ))}
      </div>
      <Problem error={current.data ? null : current.error} />

      {tab === "dictionary" && dict.data && (
        <section className="panel">
          <div className="btn-row">
            <label htmlFor="tbl" className="small">Table</label>
            <select id="tbl" className="input" style={{ width: "auto" }} value={table} onChange={(e) => setTable(e.target.value)}>
              <option value="">All tables</option>
              {tables.map((t) => <option key={t}>{t}</option>)}
            </select>
            <span className="small muted">{entries.length} columns{isSteward ? " · select a row to edit" : ""}</span>
          </div>
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Data dictionary</caption>
              <thead><tr><th>Column</th><th>Business name</th><th>Description</th><th>Type</th><th>Flags</th><th>Updated</th></tr></thead>
              <tbody>
                {entries.map((d) => (
                  <tr key={d.column_id} className={isSteward ? "clickable" : undefined} onClick={isSteward ? () => setEditing(editing === d.column_id ? null : d.column_id) : undefined}>
                    <td><span className="small muted">{d.table_name}.</span>{d.column_name}</td>
                    <td>{d.business_name}</td>
                    <td className="small">{d.description}{d.allowed_values?.length ? <div className="muted">Values: {d.allowed_values.join(", ")}</div> : null}</td>
                    <td className="small num">{d.data_type}</td>
                    <td>{d.is_pii && <span className="pill warn">Personal</span>} {d.is_protected_attribute && <span className="pill bad">Protected</span>}</td>
                    <td className="small muted">{d.updated_by} · v{d.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editing && entries.find((e) => e.column_id === editing) && (
            <EditEntry key={editing} entry={entries.find((e) => e.column_id === editing)!} onSaved={() => { setEditing(null); dict.reload(); }} />
          )}
        </section>
      )}

      {tab === "datasets" && datasets.data && (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Datasets</caption>
            <thead><tr><th>Layer</th><th>Dataset</th><th>Description</th><th className="num">Rows</th><th>Refresh</th><th>Last refreshed</th></tr></thead>
            <tbody>
              {datasets.data.items.map((d) => (
                <tr key={d.dataset_id}>
                  <td><span className="pill">{d.layer}</span></td>
                  <td>{d.name}<div className="small muted">{d.schema_name}.{d.table_name}</div></td>
                  <td className="small">{d.description}</td>
                  <td className="num">{fmtInt(d.row_count)}</td>
                  <td className="small">{d.refresh_schedule}</td>
                  <td className="small">{fmtWhen(d.last_refreshed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "lineage" && (
        <section className="panel">
          <div className="btn-row">
            <label htmlFor="model" className="small">Model</label>
            <select id="model" className="input" style={{ width: "auto" }} value={model} onChange={(e) => setModel(e.target.value)}>
              {LINEAGE_MODELS.map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
          {lineage.data && (
            <div className="grid-3">
              <div className="panel"><h3>Upstream ({lineage.data.upstream.length})</h3>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{lineage.data.upstream.map((u) => <li key={u}>{byId[u]?.relation ?? u} <span className="muted">{byId[u]?.resource_type}</span></li>)}</ul>
              </div>
              <div className="panel" style={{ borderColor: "var(--primary)" }}><h3>{lineage.data.model.relation}</h3>
                <p className="small muted">{lineage.data.model.resource_type} · {lineage.data.model.materialized}</p>
              </div>
              <div className="panel"><h3>Downstream ({lineage.data.downstream.length})</h3>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{lineage.data.downstream.map((u) => <li key={u}>{byId[u]?.relation ?? u} <span className="muted">{byId[u]?.resource_type}</span></li>)}</ul>
              </div>
            </div>
          )}
        </section>
      )}

      {tab === "quality" && runs.data && (
        <div className="grid-2">
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Data quality runs</caption>
              <thead><tr><th>When</th><th>Source</th><th>Status</th><th className="num">Passed</th><th className="num">Failed</th></tr></thead>
              <tbody>
                {runs.data.items.map((r) => (
                  <tr key={r.run_id} className={`clickable${run === r.run_id ? " selected" : ""}`} onClick={() => setRun(r.run_id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setRun(r.run_id)}>
                    <td className="small">{fmtWhen(r.started_at)}</td><td>{r.source}</td>
                    <td><span className={`pill ${STATUS_TONE[r.status] ?? ""}`}>{r.status}</span></td>
                    <td className="num">{r.passed}/{r.total}</td><td className="num">{r.failed + r.warned}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {runDetail.data && (
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Results of the selected run</caption>
                <thead><tr><th>Check</th><th>Model</th><th>Status</th><th>Detail</th></tr></thead>
                <tbody>
                  {runDetail.data.results.map((t, i) => (
                    <tr key={i}><td className="small">{t.test_name}</td><td className="small">{t.model}</td>
                      <td><span className={`pill ${STATUS_TONE[t.status] ?? ""}`}>{t.status}</span></td><td className="small">{t.message}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Page>
  );
}
