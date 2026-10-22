"""Batch-score every current customer with the champion model.

Writes ml.predictions (history) and ml.current_predictions, copies the
probability into marts.fact_customer_churn, logs feature drift (PSI) and prunes
prediction history older than ML_PREDICTION_RETENTION_DAYS.
"""

from __future__ import annotations

import logging
import sys
import uuid

import pandas as pd

from .champion import load_champion
from .config import MLConfig
from .data import load
from .modeling import psi, psi_status, risk_band, top_factors

log = logging.getLogger("telco_ml.score")


def score_frame(df: pd.DataFrame, champ, cfg: MLConfig) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    X = df[champ.features]
    proba = champ.pipeline.predict_proba(X)[:, 1]
    factors = top_factors(champ.pipeline, X, champ.reference["baseline"])
    return pd.DataFrame(
        {
            "customer_id": df["customer_id"].to_numpy(),
            "churn_probability": proba.round(5),
            "predicted_label": (proba >= champ.threshold).astype(int),
            "risk_band": [risk_band(p, cfg.high_risk_threshold, cfg.medium_risk_threshold) for p in proba],
            "top_factors": factors,
        }
    )


def write(cfg: MLConfig, scored: pd.DataFrame, champ, drift: dict[str, float]) -> str:  # type: ignore[no-untyped-def]
    import psycopg
    from psycopg.types.json import Jsonb

    run_id = str(uuid.uuid4())
    rows = [
        (
            run_id,
            r.customer_id,
            cfg.model_name,
            champ.version,
            float(r.churn_probability),
            int(r.predicted_label),
            r.risk_band,
            Jsonb(r.top_factors),
        )
        for r in scored.itertuples()
    ]
    assert cfg.dw_dsn
    with psycopg.connect(cfg.dw_dsn, application_name="telco-ml-score") as conn, conn.cursor() as cur:
        with cur.copy(
            "copy ml.predictions (scoring_run_id, customer_id, model_name, model_version, churn_probability, "
            "predicted_label, risk_band, top_factors) from stdin"
        ) as copy:
            for row in rows:
                copy.write_row(row)
        cur.execute(
            """insert into ml.current_predictions (customer_id, prediction_id, scoring_run_id, model_name, model_version,
                   churn_probability, predicted_label, risk_band, top_factors, scored_at)
               select customer_id, prediction_id, scoring_run_id, model_name, model_version, churn_probability,
                      predicted_label, risk_band, top_factors, scored_at
               from ml.predictions where scoring_run_id = %s
               on conflict (customer_id) do update set
                   prediction_id = excluded.prediction_id, scoring_run_id = excluded.scoring_run_id,
                   model_name = excluded.model_name, model_version = excluded.model_version,
                   churn_probability = excluded.churn_probability, predicted_label = excluded.predicted_label,
                   risk_band = excluded.risk_band, top_factors = excluded.top_factors, scored_at = excluded.scored_at""",
            (run_id,),
        )
        cur.execute("select ml.apply_predictions_to_fact()")
        updated = cur.fetchone()[0]
        cur.executemany(
            "insert into ml.drift_metrics (scoring_run_id, feature, psi, status) values (%s, %s, %s, %s)",
            [(run_id, f, round(v, 5), psi_status(v)) for f, v in drift.items()],
        )
        cur.execute("delete from ml.predictions where scored_at < now() - make_interval(days => %s)", (cfg.retention_days,))
        pruned = cur.rowcount
        conn.commit()
    log.info("scoring run %s: %d customers, %d fact rows updated, %d old predictions pruned", run_id, len(rows), updated, pruned)
    return run_id


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = MLConfig()
    champ = load_champion(cfg.model_name, cfg.tracking_uri, cfg.model_dir)
    if champ is None:
        log.error("no champion model available; run telco_ml.train first")
        return 1
    df = load(cfg.dw_dsn, cfg.csv_path)
    scored = score_frame(df, champ, cfg)
    drift = psi(champ.reference, df)
    significant = {k: round(v, 3) for k, v in drift.items() if psi_status(v) == "significant"}
    if significant:
        log.warning("significant drift (PSI >= 0.25): %s", significant)
    print(scored["risk_band"].value_counts().to_string())
    if cfg.dw_dsn:
        write(cfg, scored, champ, drift)
    return 0


if __name__ == "__main__":
    sys.exit(main())
