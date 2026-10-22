import json

from metadata_api.lineage import Lineage


def test_lineage_walks_up_and_down(tmp_path):
    manifest = {
        "metadata": {"generated_at": "2026-10-21T00:00:00Z"},
        "nodes": {
            "model.p.stg": {
                "name": "stg",
                "resource_type": "model",
                "schema": "staging",
                "alias": "stg",
                "config": {"materialized": "view"},
            },
            "model.p.fact": {
                "name": "fact",
                "resource_type": "model",
                "schema": "marts",
                "alias": "fact",
                "config": {"materialized": "table"},
            },
            "model.p.mv": {"name": "mv", "resource_type": "model", "schema": "olap", "alias": "mv", "config": {}},
            "test.p.t1": {"name": "t1", "resource_type": "test"},
        },
        "sources": {"source.p.raw.seed": {"name": "seed", "resource_type": "source", "schema": "raw", "identifier": "seed"}},
        "parent_map": {
            "model.p.stg": ["source.p.raw.seed"],
            "model.p.fact": ["model.p.stg"],
            "model.p.mv": ["model.p.fact"],
            "source.p.raw.seed": [],
            "test.p.t1": ["model.p.fact"],
        },
        "child_map": {
            "source.p.raw.seed": ["model.p.stg"],
            "model.p.stg": ["model.p.fact"],
            "model.p.fact": ["model.p.mv", "test.p.t1"],
            "model.p.mv": [],
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    g = Lineage(path).graph("fact")
    assert g is not None
    assert g["upstream"] == ["model.p.stg", "source.p.raw.seed"]
    assert g["downstream"] == ["model.p.mv"]
    assert {"from": "model.p.stg", "to": "model.p.fact"} in g["edges"]
    assert Lineage(path).graph("marts.fact")["model"]["name"] == "fact"
    assert Lineage(path).graph("nope") is None


def test_missing_manifest(tmp_path):
    assert Lineage(tmp_path / "missing.json").available() is False
