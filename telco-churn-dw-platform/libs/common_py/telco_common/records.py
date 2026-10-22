"""The TelcoRecord contract: JSON Schema validation + business rules + typed model.

The same rules are implemented in the PWA (apps/web/src/lib/validation.ts) so a
record that passes in the browser passes on the server.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field
from referencing import Registry, Resource

YesNo = Literal["Yes", "No"]
Addon = Literal["Yes", "No", "No internet service"]

RECORD_FIELDS: tuple[str, ...] = (
    "customer_id",
    "gender",
    "senior_citizen",
    "partner",
    "dependents",
    "tenure_months",
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
    "monthly_charges",
    "total_charges",
    "churned",
)

# IBM CSV header -> record field
IBM_COLUMN_MAP: dict[str, str] = {
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
    "Churn": "churned",
}


class TelcoRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,19}$")
    gender: Literal["Female", "Male"]
    senior_citizen: Literal[0, 1]
    partner: YesNo
    dependents: YesNo
    tenure_months: int = Field(ge=0, le=600)
    phone_service: YesNo
    multiple_lines: Literal["Yes", "No", "No phone service"]
    internet_service: Literal["DSL", "Fiber optic", "No"]
    online_security: Addon
    online_backup: Addon
    device_protection: Addon
    tech_support: Addon
    streaming_tv: Addon
    streaming_movies: Addon
    contract_type: Literal["Month-to-month", "One year", "Two year"]
    paperless_billing: YesNo
    payment_method: Literal["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"]
    monthly_charges: Decimal = Field(gt=0, le=10000, decimal_places=2)
    total_charges: Decimal | None = Field(default=None, ge=0, le=10_000_000, decimal_places=2)
    churned: bool
    version: int = Field(default=0, ge=0)

    def payload(self) -> dict[str, Any]:
        """JSON-safe dict (Decimals as floats) for Kafka and the outbox."""
        data = self.model_dump(mode="json")
        data["monthly_charges"] = float(self.monthly_charges)
        data["total_charges"] = None if self.total_charges is None else float(self.total_charges)
        return data


@dataclass(frozen=True)
class RowError:
    row: int
    field: str
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"row": self.row, "field": self.field, "code": self.code, "message": self.message}


def contracts_dir() -> Path:
    env = os.environ.get("CONTRACTS_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts"
        if (candidate / "telco-record.v1.schema.json").exists():
            return candidate
    raise FileNotFoundError("contracts directory not found; set CONTRACTS_DIR")


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    base = contracts_dir()
    resources = []
    for f in base.glob("*.schema.json"):
        schema = json.loads(f.read_text())
        res = Resource.from_contents(schema)
        resources.append((f.name, res))
        resources.append((schema["$id"], res))
    registry: Registry = Registry().with_resources(resources)
    record_schema = json.loads((base / "telco-record.v1.schema.json").read_text())
    return Draft202012Validator(record_schema, registry=registry)


def business_rule_errors(rec: dict[str, Any], row: int) -> list[RowError]:
    errors: list[RowError] = []
    tenure = rec.get("tenure_months")
    monthly = rec.get("monthly_charges")
    total = rec.get("total_charges")
    if isinstance(tenure, int) and isinstance(monthly, (int, float)):
        if tenure > 0 and total is None:
            errors.append(
                RowError(row, "total_charges", "required_when_tenure", "total_charges is required when tenure_months > 0")
            )
        if tenure > 0 and isinstance(total, (int, float)) and total + 1e-9 < monthly:
            errors.append(
                RowError(row, "total_charges", "lt_monthly", "total_charges must be >= monthly_charges when tenure_months > 0")
            )
    return errors


def validate_record(rec: Any, row: int) -> tuple[TelcoRecord | None, list[RowError]]:
    if not isinstance(rec, dict):
        return None, [RowError(row, "", "type", "record must be an object")]
    errors: list[RowError] = []
    for err in sorted(_validator().iter_errors(rec), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path)
        if err.validator == "required":
            missing = err.message.split("'")[1] if "'" in err.message else ""
            path = missing or path
        elif err.validator == "additionalProperties":
            path = path or "record"
        errors.append(RowError(row, path, str(err.validator), err.message))
    if errors:
        return None, _dedupe(errors)
    errors = business_rule_errors(rec, row)
    if errors:
        return None, errors
    return TelcoRecord.model_validate(rec), []


def _dedupe(errors: list[RowError]) -> list[RowError]:
    seen: set[tuple[str, str]] = set()
    out = []
    for e in errors:
        key = (e.field, e.code)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def from_ibm_csv_row(row: dict[str, str]) -> dict[str, Any]:
    """Convert one row of the IBM Telco CSV (all strings) into a record dict.

    Values that cannot be converted are passed through unchanged so that
    validation reports them as per-field errors instead of crashing.
    """
    rec: dict[str, Any] = {}
    for src, dst in IBM_COLUMN_MAP.items():
        value: Any = (row.get(src) or "").strip()
        if dst in ("senior_citizen", "tenure_months"):
            value = _to_int(value)
        elif dst == "monthly_charges":
            value = _to_float(value)
        elif dst == "total_charges":
            value = None if value == "" else _to_float(value)
        elif dst == "churned":
            value = {"Yes": True, "No": False}.get(value, value)
        rec[dst] = value
    return rec


def _to_int(v: str) -> Any:
    try:
        return int(v)
    except ValueError:
        return v


def _to_float(v: str) -> Any:
    try:
        return round(float(v), 2)
    except ValueError:
        return v
