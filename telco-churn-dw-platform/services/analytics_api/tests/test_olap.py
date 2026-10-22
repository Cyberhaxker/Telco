import pytest
from analytics_api.olap import OlapQuery, build, pivot
from pydantic import ValidationError


def sql_text(q: OlapQuery) -> tuple[str, list]:
    query, params = build(q)
    return query.as_string(None), params


def test_unknown_dimension_rejected():
    with pytest.raises(ValidationError, match="unknown dimensions"):
        OlapQuery(rows=["contract_type; drop table x"])


def test_unknown_measure_rejected():
    with pytest.raises(ValidationError, match="unknown measures"):
        OlapQuery(measures=["count(*)"])


def test_filter_values_are_bound_not_inlined():
    q = OlapQuery(rows=["contract_type"], filters={"payment_method": ["x' or 1=1 --"]}, operation="dice")
    text, params = sql_text(q)
    assert "or 1=1" not in text
    assert params[0] == ["x' or 1=1 --"]


def test_rollup_uses_grouping_and_all_label():
    text, _ = sql_text(OlapQuery(rows=["contract_type", "payment_method"], operation="rollup"))
    assert "group by rollup" in text and "'(All)'" in text and "grouping_level" in text


def test_slice_requires_single_value():
    with pytest.raises(ValidationError, match="slice"):
        OlapQuery(rows=["payment_method"], filters={"contract_type": ["One year", "Two year"]}, operation="slice")
    OlapQuery(rows=["payment_method"], filters={"contract_type": ["One year"]}, operation="slice")


def test_pivot_requires_rows_and_columns():
    with pytest.raises(ValidationError, match="pivot"):
        OlapQuery(rows=["contract_type"], operation="pivot")


def test_history_source_has_time_dimensions():
    text, _ = sql_text(OlapQuery(rows=["year", "quarter"], source="history", operation="rollup"))
    assert "fact_customer_churn_history" in text
    with pytest.raises(ValidationError):
        OlapQuery(rows=["year"], source="current")


def test_limit_fetches_one_extra_row():
    _, params = sql_text(OlapQuery(rows=["contract_type"], limit=10))
    assert params[-1] == 11


def test_pivot_matrix():
    q = OlapQuery(rows=["contract_type"], columns=["internet_service"], measures=["customer_count"], operation="pivot")
    cols = ["contract_type", "internet_service", "customer_count"]
    rows = [("One year", "DSL", 5), ("One year", "No", 2), ("Two year", "DSL", 7)]
    p = pivot(q, cols, rows)
    assert p["row_keys"] == [["One year"], ["Two year"]]
    assert p["column_keys"] == [["DSL"], ["No"]]
    assert p["values"]["customer_count"] == [[5, 2], [7, None]]
