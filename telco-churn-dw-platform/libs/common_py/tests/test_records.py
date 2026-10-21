import csv
from pathlib import Path

import pytest

from telco_common.records import from_ibm_csv_row, validate_record

ROOT = Path(__file__).resolve().parents[3]

GOOD = {
    "customer_id": "1234-ABCDE", "gender": "Female", "senior_citizen": 0, "partner": "Yes",
    "dependents": "No", "tenure_months": 5, "phone_service": "Yes", "multiple_lines": "No",
    "internet_service": "Fiber optic", "online_security": "No", "online_backup": "Yes",
    "device_protection": "No", "tech_support": "No", "streaming_tv": "Yes", "streaming_movies": "No",
    "contract_type": "Month-to-month", "paperless_billing": "Yes", "payment_method": "Electronic check",
    "monthly_charges": 80.5, "total_charges": 402.5, "churned": False,
}


def test_valid_record_passes():
    rec, errors = validate_record(GOOD, 0)
    assert errors == []
    assert rec is not None and rec.customer_id == "1234-ABCDE"


@pytest.mark.parametrize(
    ("patch", "field", "code"),
    [
        ({"gender": "X"}, "gender", "enum"),
        ({"tenure_months": -1}, "tenure_months", "minimum"),
        ({"monthly_charges": 0}, "monthly_charges", "exclusiveMinimum"),
        ({"total_charges": 10.0}, "total_charges", "lt_monthly"),
        ({"total_charges": None}, "total_charges", "required_when_tenure"),
        ({"internet_service": "No"}, "online_security", "const"),
        ({"phone_service": "No"}, "multiple_lines", "const"),
        ({"unexpected": 1}, "record", "additionalProperties"),
    ],
)
def test_invalid_records_report_field_errors(patch, field, code):
    rec, errors = validate_record({**GOOD, **patch}, 3)
    assert rec is None
    assert any(e.field == field and e.code == code and e.row == 3 for e in errors), errors


def test_missing_field_reports_field_name():
    data = dict(GOOD)
    del data["gender"]
    _, errors = validate_record(data, 0)
    assert any(e.field == "gender" and e.code == "required" for e in errors)


def test_tenure_zero_allows_null_total():
    rec, errors = validate_record({**GOOD, "tenure_months": 0, "total_charges": None}, 0)
    assert errors == [] and rec is not None


def test_entire_ibm_dataset_is_valid():
    with open(ROOT / "data/raw/Telco-Customer-Churn.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 7043
    bad = [(i, e) for i, r in enumerate(rows) for e in validate_record(from_ibm_csv_row(r), i)[1]]
    assert bad == []


def test_payload_is_json_safe():
    rec, _ = validate_record(GOOD, 0)
    assert rec is not None
    p = rec.payload()
    assert isinstance(p["monthly_charges"], float) and p["churned"] is False
