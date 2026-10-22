"""Model training and evaluation, independent of MLflow and the database so it can be unit-tested."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from .config import MLConfig
from .features import PROTECTED, TARGET, build_preprocessor, feature_columns

METRICS = ("accuracy", "precision", "recall", "f1", "roc_auc")


def candidate_models(cfg: MLConfig) -> dict[str, Any]:
    cw = "balanced" if cfg.class_weight_balanced else None
    rs = cfg.random_state
    return {
        "LogisticRegression": LogisticRegression(max_iter=2000, class_weight=cw, random_state=rs),
        "DecisionTree": DecisionTreeClassifier(max_depth=6, min_samples_leaf=20, class_weight=cw, random_state=rs),
        "RandomForest": RandomForestClassifier(
            n_estimators=300,
            max_depth=10,
            min_samples_leaf=5,
            class_weight=cw or "balanced_subsample",
            n_jobs=-1,
            random_state=rs,
        ),
        "GradientBoosting": GradientBoostingClassifier(random_state=rs),
    }


def make_pipeline(estimator: Any, numeric: list[str], categorical: list[str], calibrate: bool) -> Pipeline:
    clf = CalibratedClassifierCV(clone(estimator), method="sigmoid", cv=3) if calibrate else clone(estimator)
    return Pipeline([("pre", build_preprocessor(numeric, categorical)), ("clf", clf)])


def scores(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> dict[str, float]:
    pred = (proba >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, proba)),
    }


def tune_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    """Threshold that maximises F1 on the churn class (missed churners are costly)."""
    grid = np.round(np.arange(0.20, 0.81, 0.01), 2)
    f1s = [f1_score(y_true, (proba >= t).astype(int), zero_division=0) for t in grid]
    return float(grid[int(np.argmax(f1s))])


@dataclass
class ModelResult:
    name: str
    pipeline: Pipeline
    threshold: float
    holdout: dict[str, float]
    cv: dict[str, float]
    confusion: dict[str, int]
    importance: list[dict[str, float | str]]
    params: dict[str, Any]
    fairness: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TrainingOutput:
    results: list[ModelResult]
    features: tuple[list[str], list[str]]
    reference: dict[str, Any]
    n_train: int
    n_test: int


def split(df: pd.DataFrame, cfg: MLConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = train_test_split(df, test_size=cfg.test_size, random_state=cfg.random_state, stratify=df[TARGET])
    return train, test


def fairness_report(test: pd.DataFrame, proba: np.ndarray, threshold: float) -> list[dict[str, Any]]:
    """Selection rate and error rates per protected group (reported, never used as features)."""
    out = []
    pred = (proba >= threshold).astype(int)
    y = test[TARGET].to_numpy()
    for attr in PROTECTED:
        for value in sorted(test[attr].astype(str).unique()):
            m = (test[attr].astype(str) == value).to_numpy()
            yt, yp = y[m], pred[m]
            pos, neg = yt == 1, yt == 0
            out.append(
                {
                    "attribute": attr,
                    "group_value": value,
                    "n": int(m.sum()),
                    "positive_rate": float(yp.mean()) if m.any() else None,
                    "tpr": float(yp[pos].mean()) if pos.any() else None,
                    "fpr": float(yp[neg].mean()) if neg.any() else None,
                }
            )
    return out


def reference_profile(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> dict[str, Any]:
    """Training distributions used later for PSI drift monitoring and for explanations."""
    prof: dict[str, Any] = {"numeric": {}, "categorical": {}, "baseline": {}}
    for c in numeric:
        s = train[c].dropna()
        edges = np.unique(np.quantile(s, np.linspace(0, 1, 11)))
        counts, _ = np.histogram(s, bins=edges)
        prof["numeric"][c] = {"edges": edges.tolist(), "freq": (counts / counts.sum()).tolist()}
        prof["baseline"][c] = float(s.median())
    for c in categorical:
        freq = train[c].astype(str).value_counts(normalize=True)
        prof["categorical"][c] = freq.to_dict()
        prof["baseline"][c] = str(freq.index[0])
    return prof


def train_all(df: pd.DataFrame, cfg: MLConfig, only: list[str] | None = None) -> TrainingOutput:
    numeric, categorical = feature_columns(cfg.exclude_protected)
    features = numeric + categorical
    train, test = split(df, cfg)
    X_train, y_train = train[features], train[TARGET].to_numpy()
    X_test, y_test = test[features], test[TARGET].to_numpy()
    # Validation fold (from the training set only) for threshold tuning.
    fit_part, val_part = train_test_split(train, test_size=0.2, random_state=cfg.random_state, stratify=train[TARGET])
    skf = StratifiedKFold(n_splits=cfg.cv_folds, shuffle=True, random_state=cfg.random_state)

    results = []
    for name, estimator in candidate_models(cfg).items():
        if only and name not in only:
            continue
        pipe = make_pipeline(estimator, numeric, categorical, cfg.calibrate)
        cv = cross_validate(
            pipe,
            X_train,
            y_train,
            cv=skf,
            n_jobs=1,
            scoring={"accuracy": "accuracy", "precision": "precision", "recall": "recall", "f1": "f1", "roc_auc": "roc_auc"},
        )
        cv_means = {m: float(np.mean(cv[f"test_{m}"])) for m in METRICS}

        tuner = make_pipeline(estimator, numeric, categorical, cfg.calibrate).fit(fit_part[features], fit_part[TARGET])
        threshold = tune_threshold(val_part[TARGET].to_numpy(), tuner.predict_proba(val_part[features])[:, 1])

        pipe.fit(X_train, y_train)
        proba = pipe.predict_proba(X_test)[:, 1]
        holdout = scores(y_test, proba, threshold)
        tn, fp, fn, tp = confusion_matrix(y_test, (proba >= threshold).astype(int), labels=[0, 1]).ravel()

        pi = permutation_importance(pipe, X_test, y_test, scoring="roc_auc", n_repeats=5, random_state=cfg.random_state, n_jobs=1)
        importance = sorted(
            (
                {"feature": f, "importance": float(m), "std": float(s)}
                for f, m, s in zip(features, pi.importances_mean, pi.importances_std, strict=True)
            ),
            key=lambda d: d["importance"],
            reverse=True,
        )
        results.append(
            ModelResult(
                name=name,
                pipeline=pipe,
                threshold=threshold,
                holdout=holdout,
                cv=cv_means,
                confusion={"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
                importance=importance,
                params={
                    "calibrated": cfg.calibrate,
                    "class_weight_balanced": cfg.class_weight_balanced,
                    "exclude_protected": cfg.exclude_protected,
                    **{k: v for k, v in estimator.get_params().items() if isinstance(v, (int, float, str, bool)) or v is None},
                },
                fairness=fairness_report(test, proba, threshold),
            )
        )
    return TrainingOutput(results, (numeric, categorical), reference_profile(train, numeric, categorical), len(train), len(test))


def select_champion(results: list[ModelResult], metric: str, min_roc_auc: float) -> ModelResult | None:
    eligible = [r for r in results if r.holdout["roc_auc"] >= min_roc_auc]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r.holdout[metric], r.holdout["roc_auc"]))


# ---------------------------------------------------------------- scoring helpers
def risk_band(p: float, high: float, medium: float) -> str:
    return "high" if p >= high else "medium" if p >= medium else "low"


def top_factors(pipe: Pipeline, X: pd.DataFrame, baseline: dict[str, Any], k: int = 3) -> list[list[dict[str, Any]]]:
    """Per-customer contributions by perturbation: replace one feature with its
    training baseline (median / mode) and measure the change in probability.
    This shows model reliance for that customer, not causation."""
    base = pipe.predict_proba(X)[:, 1]
    deltas = {}
    for col in X.columns:
        Xp = X.copy()
        Xp[col] = baseline[col]
        deltas[col] = base - pipe.predict_proba(Xp)[:, 1]
    names = list(deltas)
    mat = np.column_stack([deltas[c] for c in names])
    out = []
    for i in range(len(X)):
        order = np.argsort(-np.abs(mat[i]))[:k]
        out.append(
            [
                {"feature": names[j], "value": _jsonable(X.iloc[i][names[j]]), "contribution": round(float(mat[i, j]), 4)}
                for j in order
                if abs(mat[i, j]) > 1e-4
            ]
        )
    return out


def _jsonable(v: Any) -> Any:
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 2)
    if isinstance(v, np.integer):
        return int(v)
    return v


def psi(reference: dict[str, Any], current: pd.DataFrame) -> dict[str, float]:
    """Population Stability Index per feature against the training profile."""
    eps = 1e-6
    out = {}
    for c, spec in reference["numeric"].items():
        edges = np.array(spec["edges"])
        s = current[c].dropna().clip(edges[0], edges[-1])
        counts, _ = np.histogram(s, bins=edges)
        cur = counts / max(counts.sum(), 1)
        ref = np.array(spec["freq"])
        out[c] = float(np.sum((cur - ref) * np.log((cur + eps) / (ref + eps))))
    for c, freq in reference["categorical"].items():
        cur_freq = current[c].astype(str).value_counts(normalize=True)
        cats = set(freq) | set(cur_freq.index)
        out[c] = float(
            sum((cur_freq.get(k, 0) - freq.get(k, 0)) * np.log((cur_freq.get(k, 0) + eps) / (freq.get(k, 0) + eps)) for k in cats)
        )
    return out


def psi_status(value: float) -> str:
    return "stable" if value < 0.1 else "moderate" if value < 0.25 else "significant"
