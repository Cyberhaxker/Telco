"""Against a real warehouse: DW_TEST_META_DSN (dw_meta role) and optional DBT_TEST_MANIFEST."""

import os

import pytest
from fastapi.testclient import TestClient
from metadata_api.config import Settings
from metadata_api.main import build_app

pytestmark = pytest.mark.integration
DSN = os.environ.get("DW_TEST_META_DSN")


@pytest.fixture(scope="module")
def client():
    if not DSN:
        pytest.skip("DW_TEST_META_DSN not set")
    s = Settings(dw_dsn=DSN, auth_disabled=True, dbt_manifest_path=os.environ.get("DBT_TEST_MANIFEST", "/nonexistent"))
    with TestClient(build_app(s)) as c:
        yield c


def test_datasets_and_dictionary(client):
    assert client.get("/api/v1/meta/datasets?layer=marts").json()["total"] >= 8
    r = client.get("/api/v1/meta/dictionary?table=marts.dim_payment")
    assert r.status_code == 200 and r.json()["total"] == 2
    assert (
        client.get("/api/v1/meta/dictionary?table=marts.dim_payment", headers={"If-None-Match": r.headers["etag"]}).status_code
        == 304
    )


def test_dictionary_update_with_optimistic_locking(client):
    entry = client.get("/api/v1/meta/dictionary?table=marts.dim_payment").json()["items"][0]
    body = {
        "business_name": entry["business_name"],
        "description": "Edited in test",
        "is_pii": entry["is_pii"],
        "is_protected_attribute": entry["is_protected_attribute"],
        "allowed_values": entry["allowed_values"],
        "example_value": entry["example_value"],
        "version": entry["version"],
    }
    r = client.put(f"/api/v1/meta/dictionary/{entry['column_id']}", json=body)
    assert r.status_code == 200 and r.json()["version"] == entry["version"] + 1
    stale = client.put(f"/api/v1/meta/dictionary/{entry['column_id']}", json=body)
    assert stale.status_code == 409


def test_dimension_members(client):
    r = client.get("/api/v1/meta/dimensions/payment_method/members")
    assert len(r.json()["members"]) == 4
    assert client.get("/api/v1/meta/dimensions/pg_shadow/members").status_code == 404


def test_quality_runs(client):
    runs = client.get("/api/v1/meta/quality/runs?source=dbt").json()
    assert runs["total"] >= 1
    detail = client.get(f"/api/v1/meta/quality/runs/{runs['items'][0]['run_id']}").json()
    assert detail["results"] and detail["status"] == "pass"


def test_lineage_from_real_manifest(client):
    if not os.environ.get("DBT_TEST_MANIFEST"):
        pytest.skip("DBT_TEST_MANIFEST not set")
    g = client.get("/api/v1/meta/lineage/fact_customer_churn").json()
    names = {n["name"] for n in g["nodes"]}
    assert {"int_customer_current", "dim_customer", "churn_flat"} <= names
