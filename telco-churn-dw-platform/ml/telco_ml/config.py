from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class MLConfig:
    dw_dsn: str | None = field(default_factory=lambda: os.environ.get("DW_DSN"))
    csv_path: str | None = field(default_factory=lambda: os.environ.get("ML_CSV_PATH"))
    tracking_uri: str | None = field(default_factory=lambda: os.environ.get("MLFLOW_TRACKING_URI"))
    model_name: str = field(default_factory=lambda: _env("ML_MODEL_NAME", "telco_churn"))
    experiment: str = field(default_factory=lambda: _env("ML_EXPERIMENT", "telco-churn"))
    champion_metric: str = field(default_factory=lambda: _env("ML_CHAMPION_METRIC", "f1"))
    min_roc_auc: float = field(default_factory=lambda: float(_env("ML_MIN_ROC_AUC", "0.83")))
    high_risk_threshold: float = field(default_factory=lambda: float(_env("ML_HIGH_RISK_THRESHOLD", "0.6")))
    medium_risk_threshold: float = field(default_factory=lambda: float(_env("ML_MEDIUM_RISK_THRESHOLD", "0.3")))
    model_dir: Path = field(default_factory=lambda: Path(_env("ML_MODEL_DIR", "./ml/artifacts")))
    random_state: int = 42
    test_size: float = 0.2
    cv_folds: int = 5
    exclude_protected: bool = field(default_factory=lambda: _env("ML_EXCLUDE_PROTECTED", "true").lower() == "true")
    class_weight_balanced: bool = field(default_factory=lambda: _env("ML_CLASS_WEIGHT_BALANCED", "false").lower() == "true")
    calibrate: bool = field(default_factory=lambda: _env("ML_CALIBRATE", "true").lower() == "true")
    retention_days: int = field(default_factory=lambda: int(_env("ML_PREDICTION_RETENTION_DAYS", "400")))
    kafka_bootstrap: str | None = field(default_factory=lambda: os.environ.get("KAFKA_BOOTSTRAP_SERVERS"))
