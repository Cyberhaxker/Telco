from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from telco_ml.config import MLConfig
from telco_ml.data import load_from_csv
from telco_ml.features import PROTECTED, TARGET, feature_columns
from telco_ml.modeling import (
    make_pipeline,
    psi,
    psi_status,
    risk_band,
    select_champion,
    split,
    top_factors,
    train_all,
)

CSV = Path(__file__).resolve().parents[2] / "data/raw/Telco-Customer-Churn.csv"


@pytest.fixture(scope="module")
def df():
    return load_from_csv(str(CSV))


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    return MLConfig(dw_dsn=None, csv_path=str(CSV), tracking_uri=None, model_dir=tmp_path_factory.mktemp("models"))


@pytest.fixture(scope="module")
def trained(df, cfg):
    return train_all(df, cfg)


def test_csv_loads_with_expected_shape(df):
    assert len(df) == 7043
    assert df["total_charges"].isna().sum() == 11
    assert int(df[TARGET].sum()) == 1869


def test_protected_attributes_and_id_are_not_features(cfg):
    numeric, categorical = feature_columns(cfg.exclude_protected)
    features = set(numeric + categorical)
    assert "customer_id" not in features
    assert not features & set(PROTECTED)


def test_preprocessing_is_fitted_on_training_rows_only(df, cfg):
    numeric, categorical = feature_columns(True)
    train, _ = split(df, cfg)
    pipe = make_pipeline(
        __import__("sklearn.linear_model", fromlist=["LogisticRegression"]).LogisticRegression(max_iter=500),
        numeric,
        categorical,
        calibrate=False,
    )
    pipe.fit(train[numeric + categorical], train[TARGET])
    scaler = pipe.named_steps["pre"].named_transformers_["num"].named_steps["scale"]
    imputed_train = train[numeric].fillna(train[numeric].median())
    np.testing.assert_allclose(scaler.mean_, imputed_train.mean().to_numpy(), rtol=1e-9)
    assert not np.allclose(scaler.mean_, df[numeric].fillna(df[numeric].median()).mean().to_numpy(), rtol=1e-6)


def test_all_four_models_trained_and_champion_meets_auc(trained, cfg):
    assert [r.name for r in trained.results] == ["LogisticRegression", "DecisionTree", "RandomForest", "GradientBoosting"]
    champ = select_champion(trained.results, "f1", cfg.min_roc_auc)
    assert champ is not None
    assert champ.holdout["roc_auc"] >= 0.83
    # Baseline from the original study: best F1 0.6304 (RandomForest). Threshold tuning should not do worse.
    assert champ.holdout["f1"] >= 0.60
    for r in trained.results:
        assert set(r.cv) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
        assert sum(r.confusion.values()) == trained.n_test == 1409


def test_training_is_reproducible(df, cfg):
    a = train_all(df, cfg, only=["LogisticRegression"]).results[0]
    b = train_all(df, cfg, only=["LogisticRegression"]).results[0]
    assert a.holdout == b.holdout and a.threshold == b.threshold


def test_fairness_report_covers_protected_groups(trained):
    groups = {(f["attribute"], f["group_value"]) for f in trained.results[0].fairness}
    assert groups == {("gender", "Female"), ("gender", "Male"), ("senior_citizen", "0"), ("senior_citizen", "1")}


def test_top_factors_and_risk_bands(df, trained):
    champ = trained.results[0]
    numeric, categorical = trained.features
    X = df[numeric + categorical].head(5)
    factors = top_factors(champ.pipeline, X, trained.reference["baseline"])
    assert len(factors) == 5 and all(len(f) <= 3 for f in factors)
    assert all({"feature", "value", "contribution"} <= set(item) for f in factors for item in f)
    assert risk_band(0.7, 0.6, 0.3) == "high" and risk_band(0.4, 0.6, 0.3) == "medium" and risk_band(0.1, 0.6, 0.3) == "low"


def test_psi_detects_drift(df, trained):
    stable = psi(trained.reference, df)
    assert all(psi_status(v) == "stable" for v in stable.values())
    shifted = df.copy()
    shifted["monthly_charges"] = shifted["monthly_charges"] * 1.8
    assert psi_status(psi(trained.reference, shifted)["monthly_charges"]) == "significant"


def test_select_champion_respects_auc_floor(trained):
    assert select_champion(trained.results, "f1", 0.99) is None
    cfg_b = replace(MLConfig(), champion_metric="roc_auc")
    best_auc = select_champion(trained.results, cfg_b.champion_metric, 0.8)
    assert best_auc is not None and best_auc.holdout["roc_auc"] == max(r.holdout["roc_auc"] for r in trained.results)
