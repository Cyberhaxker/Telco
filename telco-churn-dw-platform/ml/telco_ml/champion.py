"""Load the current champion: MLflow registry alias first, local copy as fallback."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.pipeline import Pipeline

log = logging.getLogger(__name__)


@dataclass
class Champion:
    pipeline: Pipeline
    version: str
    algorithm: str
    threshold: float
    numeric: list[str]
    categorical: list[str]
    reference: dict[str, Any]
    source: str

    @property
    def features(self) -> list[str]:
        return self.numeric + self.categorical


def load_local(model_dir: Path) -> Champion | None:
    meta_path, model_path = model_dir / "champion.json", model_dir / "champion.joblib"
    if not (meta_path.exists() and model_path.exists()):
        return None
    meta = json.loads(meta_path.read_text())
    return Champion(
        joblib.load(model_path),
        str(meta["version"]),
        meta["algorithm"],
        float(meta["threshold"]),
        meta["numeric"],
        meta["categorical"],
        meta["reference"],
        "local",
    )


def load_champion(model_name: str, tracking_uri: str | None, model_dir: Path) -> Champion | None:
    local = load_local(model_dir)
    if tracking_uri:
        try:
            import mlflow
            from mlflow import MlflowClient

            client = MlflowClient(tracking_uri)
            mv = client.get_model_version_by_alias(model_name, "champion")
            if local is not None and local.version == str(mv.version):
                return local  # same version already on disk; skip the download
            mlflow.set_tracking_uri(tracking_uri)
            pipe = mlflow.sklearn.load_model(f"models:/{model_name}@champion")
            ref_path = mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="evaluation/reference_profile.json")
            reference = json.loads(Path(ref_path).read_text())
            numeric = list(reference["numeric"])
            categorical = list(reference["categorical"])
            return Champion(
                pipe,
                str(mv.version),
                mv.tags.get("algorithm", "unknown"),
                float(mv.tags.get("threshold", 0.5)),
                numeric,
                categorical,
                reference,
                "mlflow",
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the local copy
            log.warning("could not load champion from MLflow (%s); using local copy", exc)
    return local
