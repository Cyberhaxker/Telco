"use client";

import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtWhen } from "@/lib/format";
import { useAsync } from "@/lib/hooks";

interface Pipeline {
  dag_id: string; found: boolean; is_paused: boolean | null; schedule: string | null; next_run: string | null;
  runs: { dag_run_id: string; state: string; run_type: string; start_date: string | null; end_date: string | null }[];
}
const STATE_TONE: Record<string, string> = { success: "ok", running: "info", queued: "info", failed: "bad" };
const ROLES: [string, string][] = [
  ["admin", "Everything below, plus users, pipelines and models"],
  ["data_steward", "Edit the data dictionary, review rejected batches, see pipeline status"],
  ["data_entry", "Create and update customers, upload CSVs, submit batches"],
  ["analyst", "OLAP explorer, predictions, model results"],
  ["viewer", "Dashboard and metadata (read only)"],
];

export default function AdminPage() {
  const { getToken, status, profile } = useAuth();
  const p = useAsync(() => apiGetCached<{ pipelines: Pipeline[] }>("/meta/pipelines", getToken), [], status === "authenticated" || status === "offline");
  return (
    <Page title="Admin" description="Pipeline runs and the roles that control access." roles={["admin", "data_steward"]}
          actions={<><CacheNote fromCache={p.fromCache} fetchedAt={p.fetchedAt} /><button type="button" className="btn small" onClick={p.reload}>Refresh</button></>}>
      <Problem error={p.data ? null : p.error} />
      {p.data && (
        <div className="grid-2">
          {p.data.pipelines.map((d) => (
            <section key={d.dag_id} className="panel">
              <div className="panel-head">
                <h2>{d.dag_id}</h2>
                {!d.found ? <span className="pill bad">Not deployed</span> : d.is_paused ? <span className="pill warn">Paused</span> : <span className="pill ok">Active</span>}
              </div>
              <span className="small muted">Schedule: {d.schedule ?? "manual"} · next run {fmtWhen(d.next_run)}</span>
              {d.runs.length === 0 ? <p className="small muted">No runs yet.</p> : (
                <div className="table-wrap" style={{ maxHeight: "none" }}>
                  <table>
                    <caption className="sr-only">Recent runs of {d.dag_id}</caption>
                    <thead><tr><th>Started</th><th>Type</th><th>State</th></tr></thead>
                    <tbody>{d.runs.map((r) => (
                      <tr key={r.dag_run_id}><td className="small">{fmtWhen(r.start_date)}</td><td className="small">{r.run_type}</td>
                        <td><span className={`pill ${STATE_TONE[r.state] ?? ""}`}>{r.state}</span></td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
      <section className="panel">
        <h2>Roles</h2>
        <p className="small muted">Roles are managed in Keycloak (realm “telco”). You have: {profile?.roles.join(", ") || "none"}.</p>
        <div className="table-wrap" style={{ maxHeight: "none" }}>
          <table>
            <caption className="sr-only">Roles and permissions</caption>
            <thead><tr><th>Role</th><th>Can</th></tr></thead>
            <tbody>{ROLES.map(([r, can]) => (
              <tr key={r}><td>{r} {profile?.roles.includes(r as never) && <span className="pill ok">You</span>}</td><td>{can}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </section>
    </Page>
  );
}
