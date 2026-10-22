"""Feature definitions and the leakage-safe preprocessing pipeline."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ID_COLUMN = "customer_id"
TARGET = "churn"
PROTECTED = ("gender", "senior_citizen")
NUMERIC = ("tenure_months", "monthly_charges", "total_charges")
CATEGORICAL = (
    "partner",
    "dependents",
    "phone_service",
    "multiple_lines",
    "internet_service",
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
    "contract_type",
    "paperless_billing",
    "payment_method",
)


def feature_columns(exclude_protected: bool = True) -> tuple[list[str], list[str]]:
    numeric = list(NUMERIC)
    categorical = list(CATEGORICAL)
    if not exclude_protected:
        numeric.append("senior_citizen")
        categorical.append("gender")
    return numeric, categorical


def build_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    """Imputers, scaler and encoder are fitted inside the model Pipeline, so they
    only ever see the training fold (no leakage from validation or test data)."""
    return ColumnTransformer(
        [
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            (
                "cat",
                Pipeline(
                    [("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]
                ),
                categorical,
            ),
        ]
    )
