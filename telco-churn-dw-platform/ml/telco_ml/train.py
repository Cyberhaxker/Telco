"""Train the four candidate models, log them to MLflow and promote a champion.

    python -m telco_ml.train              # warehouse (DW_DSN) or CSV (ML_CSV_PATH)

A new model becomes champion only if it reaches ML_MIN_ROC_AUC on the hold-out
set and beats the current champion on ML_CHAMPION_METRIC. Otherwise it is
registered as the challenger.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .config import MLConfig
from .data import load
from .modeling import ModelResult, TrainingOutput, select_champion, train_all

log = logging.getLogger("telco_ml.train")

# Logged-model URIs from the current training job, by algorithm (MLflow 3 LoggedModel).
MODEL_URIS: dict[str, str] = {}


def save_local_champion(cfg: MLConfig, champ: ModelResult, out: TrainingOutput, version: str, run_id: str) -> Path:
    """Write the champion next to its metadata so analytics-api can serve it even when MLflow is down."""
    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    tmp = cfg.model_dir / f".champion-{uuid.uuid4().hex}.joblib"
    joblib.dump(champ.pipeline, tmp)
    tmp.replace(cfg.model_dir / "champion.joblib")
    meta = {
        "model_name": cfg.model_name,
        "algorithm": champ.name,
        "version": version,
        "mlflow_run_id": run_id,
        "threshold": champ.threshold,
        "holdout": champ.holdout,
        "cv": champ.cv,
        "numeric": out.features[0],
        "categorical": out.features[1],
        "reference": out.reference,
        "trained_at": datetime.now(UTC).isoformat(),
    }
    (cfg.model_dir / "champion.json").write_text(json.dumps(meta, indent=2))
    return cfg.model_dir / "champion.joblib"


def record_runs(
    cfg: MLConfig,
    training_run_id: str,
    out: TrainingOutput,
    run_ids: dict[str, str],
    champion: ModelResult | None,
    promoted: bool,
    version: str | None,
) -> None:
    if not cfg.dw_dsn:
        return
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(cfg.dw_dsn, application_name="telco-ml") as conn, conn.cursor() as cur:
        if promoted:
            cur.execute("update ml.model_runs set is_champion = false where model_name = %s and is_champion", (cfg.model_name,))
        for r in out.results:
            is_champ = promoted and champion is not None and r.name == champion.name
            cur.execute(
                """insert into ml.model_runs (run_id, training_run_id, model_name, algorithm, params, holdout_metrics,
                       cv_metrics, confusion_matrix, threshold, feature_importance, registered_version, is_champion)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    run_ids.get(r.name, f"{training_run_id}:{r.name}"),
                    training_run_id,
                    cfg.model_name,
                    r.name,
                    Jsonb(_clean(r.params)),
                    Jsonb(r.holdout),
                    Jsonb(r.cv),
                    Jsonb(r.confusion),
                    r.threshold,
                    Jsonb(r.importance),
                    version if champion is not None and r.name == champion.name else None,
                    is_champ,
                ),
            )
        if champion is not None:
            cur.executemany(
                "insert into ml.fairness_metrics (run_id, attribute, group_value, n, positive_rate, tpr, fpr) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        run_ids.get(champion.name, training_run_id),
                        f["attribute"],
                        f["group_value"],
                        f["n"],
                        f["positive_rate"],
                        f["tpr"],
                        f["fpr"],
                    )
                    for f in champion.fairness
                ],
            )
        conn.commit()


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is None or isinstance(v, (int, float, str, bool))}


def trusted_types(pipeline: Any) -> list[str]:
    """Types in our own fitted pipeline that skops does not trust by default."""
    import skops.io as sio

    return sorted(sio.get_untrusted_types(data=sio.dumps(pipeline)))


def log_to_mlflow(cfg: MLConfig, out: TrainingOutput, training_run_id: str, sample: pd.DataFrame) -> dict[str, str]:
    import mlflow
    from mlflow.models import infer_signature

    mlflow.set_tracking_uri(cfg.tracking_uri)
    mlflow.set_experiment(cfg.experiment)
    features = out.features[0] + out.features[1]
    run_ids = {}
    for r in out.results:
        with mlflow.start_run(run_name=f"{r.name}-{training_run_id[:8]}") as run:
            mlflow.set_tags({"training_run_id": training_run_id, "algorithm": r.name})
            mlflow.log_params({**_clean(r.params), "threshold": r.threshold, "n_train": out.n_train, "n_test": out.n_test})
            mlflow.log_metrics({f"holdout_{k}": v for k, v in r.holdout.items()})
            mlflow.log_metrics({f"cv_{k}": v for k, v in r.cv.items()})
            with tempfile.TemporaryDirectory() as d:
                Path(d, "confusion_matrix.json").write_text(json.dumps(r.confusion, indent=2))
                Path(d, "permutation_importance.json").write_text(json.dumps(r.importance, indent=2))
                Path(d, "fairness.json").write_text(json.dumps(r.fairness, indent=2))
                Path(d, "reference_profile.json").write_text(json.dumps(out.reference))
                mlflow.log_artifacts(d, artifact_path="evaluation")
            X = sample[features]
            info = mlflow.sklearn.log_model(
                r.pipeline,
                name="model",
                signature=infer_signature(X, r.pipeline.predict_proba(X)[:, 1]),
                input_example=X.head(3),
                # MLflow saves sklearn models with skops (no pickle). The pipeline's own
                # scikit-learn/numpy types must be declared trusted explicitly.
                skops_trusted_types=trusted_types(r.pipeline),
            )
            run_ids[r.name] = run.info.run_id
            MODEL_URIS[r.name] = info.model_uri
    return run_ids


def promote(cfg: MLConfig, champ: ModelResult, run_id: str) -> tuple[bool, str]:
    """Register the best model; alias it champion if it beats the current champion."""
    import mlflow
    from mlflow import MlflowClient

    client = MlflowClient(cfg.tracking_uri)
    mv = mlflow.register_model(MODEL_URIS.get(champ.name, f"runs:/{run_id}/model"), cfg.model_name)
    client.set_model_version_tag(cfg.model_name, mv.version, "threshold", str(champ.threshold))
    client.set_model_version_tag(cfg.model_name, mv.version, "algorithm", champ.name)
    current_value = None
    try:
        current = client.get_model_version_by_alias(cfg.model_name, "champion")
        current_value = client.get_run(current.run_id).data.metrics.get(f"holdout_{cfg.champion_metric}")
    except Exception:  # noqa: BLE001 - no champion yet
        current = None
    new_value = champ.holdout[cfg.champion_metric]
    if current is None or current_value is None or new_value > current_value:
        client.set_registered_model_alias(cfg.model_name, "champion", mv.version)
        log.info(
            "promoted %s v%s to champion (%s=%.4f, previous=%s)",
            champ.name,
            mv.version,
            cfg.champion_metric,
            new_value,
            current_value,
        )
        return True, str(mv.version)
    client.set_registered_model_alias(cfg.model_name, "challenger", mv.version)
    log.info(
        "kept current champion (%s=%.4f >= %.4f); v%s is challenger", cfg.champion_metric, current_value, new_value, mv.version
    )
    return False, str(mv.version)


def notify_promoted(cfg: MLConfig, version: str, algorithm: str) -> None:
    if not cfg.kafka_bootstrap:
        return
    try:
        from confluent_kafka import Producer
    except ImportError:
        return
    msg = {
        "event_id": str(uuid.uuid4()),
        "event_type": "model.promoted",
        "schema_version": "1",
        "batch_id": None,
        "produced_at": datetime.now(UTC).isoformat(),
        "source": "telco-ml",
        "payload": {"model_name": cfg.model_name, "version": version, "algorithm": algorithm},
    }
    p = Producer({"bootstrap.servers": cfg.kafka_bootstrap, "acks": "all", "enable.idempotence": True})
    p.produce("dw.events.v1", key=cfg.model_name.encode(), value=json.dumps(msg).encode())
    p.flush(10)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = MLConfig()
    df = load(cfg.dw_dsn, cfg.csv_path)
    log.info("training on %d rows (%d churners)", len(df), int(df["churn"].sum()))
    training_run_id = str(uuid.uuid4())
    out = train_all(df, cfg)
    print(f"\n{'model':20} {'acc':>7} {'prec':>7} {'recall':>7} {'f1':>7} {'auc':>7} {'thr':>5} | cv_f1  cv_auc")
    for r in out.results:
        h = r.holdout
        print(
            f"{r.name:20} {h['accuracy']:7.4f} {h['precision']:7.4f} {h['recall']:7.4f} {h['f1']:7.4f} "
            f"{h['roc_auc']:7.4f} {r.threshold:5.2f} | {r.cv['f1']:.4f} {r.cv['roc_auc']:.4f}"
        )

    champ = select_champion(out.results, cfg.champion_metric, cfg.min_roc_auc)
    if champ is None:
        log.error("no model reached ROC-AUC %.2f; nothing promoted", cfg.min_roc_auc)
    run_ids: dict[str, str] = {}
    promoted, version = False, None
    if cfg.tracking_uri:
        run_ids = log_to_mlflow(cfg, out, training_run_id, df.head(200))
        if champ is not None:
            promoted, version = promote(cfg, champ, run_ids[champ.name])
    elif champ is not None:
        promoted, version = True, f"local-{training_run_id[:8]}"
    if champ is not None and promoted:
        save_local_champion(cfg, champ, out, version or "local", run_ids.get(champ.name, ""))
        notify_promoted(cfg, version or "local", champ.name)
    record_runs(cfg, training_run_id, out, run_ids, champ, promoted, version)
    if champ is not None:
        print(
            f"\nchampion candidate: {champ.name} ({cfg.champion_metric}={champ.holdout[cfg.champion_metric]:.4f}, "
            f"roc_auc={champ.holdout['roc_auc']:.4f}) promoted={promoted} version={version}"
        )
    return 0 if champ is not None else 1


if __name__ == "__main__":
    sys.exit(main())
