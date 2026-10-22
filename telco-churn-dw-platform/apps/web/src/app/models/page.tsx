"use client";

import { useMemo } from "react";

import { Chart } from "@/components/Chart";
import { Page } from "@/components/Page";
import { CacheNote, Problem } from "@/components/Problem";
import { apiGetCached } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtWhen } from "@/lib/format";
import { useAsync } from "@/lib/hooks";

type Metrics = Record<"accuracy" | "precision" | "recall" | "f1" | "roc_auc", number>;
interface Run {
  run_id: string; algorithm: string; holdout_metrics: Metrics; cv_metrics: Metrics; threshold: number;
  confusion_matrix: { tn: number; fp: number; fn: number; tp: number }; registered_version: string | null;
  is_champion: boolean; trained_at: string; feature_importance: { feature: string; importance: number }[];
}
interface Registry {
  model_name: string;
  champion: { version: string; algorithm: string; threshold: number; loaded_from: string } | null;
  runs: Run[];
  fairness: { attribute: string; group_value: string; n: number; positive_rate: number; tpr: number; fpr: number }[];
  drift: { feature: string; psi: number; status: string }[];
  baseline: Record<string, Metrics>;
}

const METRICS = ["accuracy", "precision", "recall", "f1", "roc_auc"] as const;
const f4 = (n: number | undefined) => (n === undefined || n === null ? "—" : n.toFixed(4));

export default function ModelsPage() {
  const { getToken, status } = useAuth();
  const reg = useAsync(() => apiGetCached<Registry>("/analytics/models", getToken), [], status === "authenticated" || status === "offline");
  const d = reg.data;
  const latest = useMemo(() => {
    if (!d?.runs.length) return [];
    const newest = d.runs[0]!.trained_at.slice(0, 16);
    return d.runs.filter((r) => r.trained_at.slice(0, 16) === newest);
  }, [d]);
  const champion = d?.runs.find((r) => r.is_champion);

  return (
    <Page title="Models" description="Hold-out results of the latest training run against the original study's baseline." roles={["analyst"]}
          actions={<CacheNote fromCache={reg.fromCache} fetchedAt={reg.fetchedAt} />}>
      <Problem error={d ? null : reg.error} />
      {d && latest.length === 0 && <div className="panel empty">No training runs yet. The weekly training pipeline writes results here.</div>}
      {d && latest.length > 0 && (
        <>
          <section className="kpis">
            <div className="kpi"><span className="label">Champion</span><span className="value" style={{ fontSize: "1.25rem" }}>{d.champion?.algorithm ?? champion?.algorithm ?? "—"}</span>
              <span className="sub">Version {d.champion?.version ?? champion?.registered_version ?? "—"} · threshold {d.champion?.threshold ?? champion?.threshold}</span></div>
            <div className="kpi signal"><span className="label">Champion F1 (churn class)</span><span className="value">{f4(champion?.holdout_metrics.f1)}</span><span className="sub">Baseline best 0.6304</span></div>
            <div className="kpi"><span className="label">Champion ROC-AUC</span><span className="value">{f4(champion?.holdout_metrics.roc_auc)}</span><span className="sub">Must be ≥ 0.83</span></div>
            <div className="kpi"><span className="label">Trained</span><span className="value" style={{ fontSize: "1.1rem" }}>{fmtWhen(latest[0]?.trained_at)}</span><span className="sub">Stratified 80/20 + 5-fold CV</span></div>
          </section>
          <section className="panel">
            <h2>Hold-out metrics</h2>
            <Chart label="Hold-out F1 and ROC-AUC per model" categories={latest.map((r) => r.algorithm)}
                   series={[{ name: "F1", values: latest.map((r) => r.holdout_metrics.f1), tone: "signal" },
                            { name: "Baseline F1", values: latest.map((r) => d.baseline[r.algorithm]?.f1 ?? null), tone: "muted" },
                            { name: "ROC-AUC", values: latest.map((r) => r.holdout_metrics.roc_auc), tone: "primary" }]} />
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Model comparison</caption>
                <thead><tr><th>Model</th>{METRICS.map((m) => <th key={m} className="num">{m}</th>)}<th className="num">CV F1</th><th className="num">Threshold</th><th>Confusion (TN/FP/FN/TP)</th></tr></thead>
                <tbody>
                  {latest.map((r) => (
                    <tr key={r.run_id} className={r.is_champion ? "selected" : undefined}>
                      <td>{r.algorithm} {r.is_champion && <span className="pill ok">Champion</span>}
                        <div className="small muted">baseline F1 {f4(d.baseline[r.algorithm]?.f1)} · AUC {f4(d.baseline[r.algorithm]?.roc_auc)}</div></td>
                      {METRICS.map((m) => <td key={m} className="num">{f4(r.holdout_metrics[m])}</td>)}
                      <td className="num">{f4(r.cv_metrics.f1)}</td><td className="num">{r.threshold}</td>
                      <td className="num small">{r.confusion_matrix.tn}/{r.confusion_matrix.fp}/{r.confusion_matrix.fn}/{r.confusion_matrix.tp}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Thresholds are tuned for F1 on the churn class, which trades some accuracy for catching more churners.</p>
          </section>
          <div className="grid-2">
            {champion && (
              <section className="panel">
                <h2>What the champion relies on</h2>
                <Chart label="Permutation importance (drop in ROC-AUC)" horizontal categories={champion.feature_importance.slice(0, 10).map((f) => f.feature.replace(/_/g, " "))}
                       series={[{ name: "Importance", values: champion.feature_importance.slice(0, 10).map((f) => Number(f.importance.toFixed(4))), tone: "primary" }]} />
                <p className="small muted">Permutation importance shows how much the model depends on a feature, not whether it causes churn.</p>
              </section>
            )}
            <section className="panel">
              <h2>Fairness by protected group</h2>
              <p className="small muted">Gender and senior-citizen status are not model inputs. Rates are reported so differences stay visible.</p>
              <div className="table-wrap" style={{ maxHeight: "none" }}>
                <table>
                  <caption className="sr-only">Fairness metrics</caption>
                  <thead><tr><th>Group</th><th className="num">n</th><th className="num">Flagged</th><th className="num">TPR</th><th className="num">FPR</th></tr></thead>
                  <tbody>{d.fairness.map((f) => (
                    <tr key={`${f.attribute}-${f.group_value}`}><td>{f.attribute} = {f.group_value}</td><td className="num">{f.n}</td>
                      <td className="num">{f4(f.positive_rate)}</td><td className="num">{f4(f.tpr)}</td><td className="num">{f4(f.fpr)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              <h3>Feature drift (PSI, latest scoring run)</h3>
              <div className="chips">{d.drift.length ? d.drift.map((x) => (
                <span key={x.feature} className={`pill ${x.status === "stable" ? "ok" : x.status === "moderate" ? "warn" : "bad"}`}>{x.feature} {x.psi.toFixed(3)}</span>
              )) : <span className="small muted">No scoring run yet.</span>}</div>
            </section>
          </div>
        </>
      )}
    </Page>
  );
}
