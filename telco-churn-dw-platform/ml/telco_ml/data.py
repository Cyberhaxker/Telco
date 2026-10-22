"""Load the modelling frame from the warehouse (ml.ml_features) or the IBM CSV."""

from __future__ import annotations

import pandas as pd

from .features import CATEGORICAL, ID_COLUMN, NUMERIC, PROTECTED, TARGET

COLUMNS = [ID_COLUMN, *PROTECTED, *NUMERIC, *CATEGORICAL, TARGET]

IBM_TO_FEATURE = {
    "customerID": "customer_id",
    "gender": "gender",
    "SeniorCitizen": "senior_citizen",
    "Partner": "partner",
    "Dependents": "dependents",
    "tenure": "tenure_months",
    "PhoneService": "phone_service",
    "MultipleLines": "multiple_lines",
    "InternetService": "internet_service",
    "OnlineSecurity": "online_security",
    "OnlineBackup": "online_backup",
    "DeviceProtection": "device_protection",
    "TechSupport": "tech_support",
    "StreamingTV": "streaming_tv",
    "StreamingMovies": "streaming_movies",
    "Contract": "contract_type",
    "PaperlessBilling": "paperless_billing",
    "PaymentMethod": "payment_method",
    "MonthlyCharges": "monthly_charges",
    "TotalCharges": "total_charges",
    "Churn": "churn",
}


def load_from_warehouse(dsn: str) -> pd.DataFrame:
    import psycopg

    with psycopg.connect(dsn, application_name="telco-ml") as conn, conn.cursor() as cur:
        cur.execute(f"select {', '.join(COLUMNS)} from ml.ml_features order by customer_id")
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=COLUMNS)
    return _types(df)


def load_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path).rename(columns=IBM_TO_FEATURE)
    df["total_charges"] = pd.to_numeric(df["total_charges"].astype(str).str.strip().replace("", None), errors="coerce")
    df["churn"] = (df["churn"] == "Yes").astype(int)
    return _types(df[COLUMNS])


def _types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("tenure_months", "monthly_charges", "total_charges"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["senior_citizen"] = df["senior_citizen"].astype(int)
    df["churn"] = df["churn"].astype(int)
    for c in CATEGORICAL + ("gender",):
        df[c] = df[c].astype(str)
    return df


def load(dsn: str | None, csv_path: str | None) -> pd.DataFrame:
    if dsn:
        return load_from_warehouse(dsn)
    if csv_path:
        return load_from_csv(csv_path)
    raise RuntimeError("Set DW_DSN (warehouse) or ML_CSV_PATH (CSV) to load training data")
