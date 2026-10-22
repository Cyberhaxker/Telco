"""Runs the API against a real warehouse: set DW_TEST_DSN (dw_analytics role)."""

import os

import pytest
from analytics_api.config import Settings
from analytics_api.main import build_app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration
DSN = os.environ.get("DW_TEST_DSN")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    if not DSN:
        pytest.skip("DW_TEST_DSN not set")
    settings = Settings(
        dw_dsn=DSN, auth_disabled=True, ml_model_dir=str(os.environ.get("ML_TEST_MODEL_DIR", tmp_path_factory.mktemp("m")))
    )
    with TestClient(build_app(settings)) as c:
        yield c


def q(client, **body):
    r = client.post("/api/v1/analytics/olap/query", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    return [dict(zip(data["columns"], row, strict=True)) for row in data["rows"]], data


def test_acceptance_figures(client):
    rows, _ = q(client, rows=["contract_type"], measures=["customer_count", "churned_count", "churn_rate_pct"])
    by = {r["contract_type"]: r for r in rows}
    assert (by["Month-to-month"]["churned_count"], by["Month-to-month"]["customer_count"]) == (1655, 3875)
    assert by["Month-to-month"]["churn_rate_pct"] == 42.71
    assert (by["One year"]["churned_count"], by["One year"]["customer_count"], by["One year"]["churn_rate_pct"]) == (
        166,
        1473,
        11.27,
    )
    assert (by["Two year"]["churned_count"], by["Two year"]["customer_count"], by["Two year"]["churn_rate_pct"]) == (
        48,
        1695,
        2.83,
    )
    rows, _ = q(client, rows=["tenure_band"], measures=["customer_count", "churned_count", "churn_rate_pct"])
    t = {r["tenure_band"]: r for r in rows}["0-12"]
    assert (t["churned_count"], t["customer_count"], t["churn_rate_pct"]) == (1037, 2186, 47.44)
    rows, _ = q(client, rows=["payment_method"], measures=["customer_count", "churned_count", "churn_rate_pct"])
    e = {r["payment_method"]: r for r in rows}["Electronic check"]
    assert (e["churned_count"], e["customer_count"], e["churn_rate_pct"]) == (1071, 2365, 45.29)


def test_rollup_has_grand_total(client):
    rows, _ = q(client, rows=["contract_type", "payment_method"], operation="rollup", measures=["customer_count"])
    total = [r for r in rows if r["contract_type"] == "(All)" and r["payment_method"] == "(All)"]
    assert total and total[0]["customer_count"] == 7043


def test_slice_and_dice(client):
    rows, _ = q(
        client,
        rows=["payment_method"],
        filters={"contract_type": ["Month-to-month"]},
        operation="slice",
        measures=["customer_count"],
    )
    assert sum(r["customer_count"] for r in rows) == 3875
    rows, _ = q(
        client,
        rows=["contract_type"],
        filters={"contract_type": ["One year", "Two year"], "payment_method": ["Electronic check"]},
        operation="dice",
        measures=["customer_count"],
    )
    assert {r["contract_type"] for r in rows} == {"One year", "Two year"}


def test_pivot(client):
    _, data = q(client, rows=["contract_type"], columns=["internet_service"], operation="pivot", measures=["churn_rate_pct"])
    assert data["pivot"]["column_keys"] == [["DSL"], ["Fiber optic"], ["No"]]
    assert len(data["pivot"]["values"]["churn_rate_pct"]) == 3


def test_history_rollup_by_time(client):
    rows, _ = q(client, rows=["year", "quarter", "month"], source="history", operation="rollup", measures=["customer_count"])
    assert rows[-1]["year"] == "(All)" or any(r["year"] == "(All)" for r in rows)


def test_kpis(client):
    r = client.get("/api/v1/analytics/kpis")
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["total_customers"] == 7043 and k["churned_customers"] == 1869 and k["churn_rate_pct"] == 26.54
    assert [c["label"] for c in k["churn_by_tenure_band"]] == ["0-12", "13-24", "25-48", "49-72"]


def test_dimensions(client):
    d = client.get("/api/v1/analytics/olap/dimensions").json()
    assert d["dimensions"]["contract_type"] == ["Month-to-month", "One year", "Two year"]


def test_unknown_customer_is_404_problem(client):
    r = client.get("/api/v1/analytics/predictions/NOPE-00000")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
