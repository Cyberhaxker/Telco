"""OLAP query builder.

Only whitelisted dimensions and measures can be used. Identifiers come from
the whitelist (psycopg.sql.Identifier / fixed SQL fragments) and every filter
value is a bound parameter, so no user input is ever concatenated into SQL.
"""

from __future__ import annotations

from typing import Any, Literal

from psycopg import sql
from pydantic import BaseModel, Field, field_validator, model_validator

# Dimension -> column, per source relation.
CURRENT_DIMENSIONS: dict[str, str] = {
    "contract_type": "contract_type",
    "paperless_billing": "paperless_billing",
    "payment_method": "payment_method",
    "is_automatic": "is_automatic",
    "internet_service": "internet_service",
    "phone_service": "phone_service",
    "multiple_lines": "multiple_lines",
    "online_security": "online_security",
    "online_backup": "online_backup",
    "device_protection": "device_protection",
    "tech_support": "tech_support",
    "streaming_tv": "streaming_tv",
    "streaming_movies": "streaming_movies",
    "tenure_band": "tenure_band",
    "partner": "partner",
    "dependents": "dependents",
    "gender": "gender",
    "senior_citizen": "senior_citizen",
    "churn_label": "churn_label",
}
HISTORY_DIMENSIONS: dict[str, str] = {
    "contract_type": "contract_type",
    "paperless_billing": "paperless_billing",
    "payment_method": "payment_method",
    "internet_service": "internet_service",
    "tenure_band": "tenure_band",
    "churn_label": "churn_label",
    "year": "year",
    "quarter": "quarter",
    "month": "month",
}

MEASURES: dict[str, str] = {
    "customer_count": "count(*)::bigint",
    "churned_count": "sum(churn_flag)::bigint",
    "churn_rate_pct": "round(100.0 * sum(churn_flag) / nullif(count(*), 0), 2)",
    "avg_monthly_charges": "round(avg(monthly_charges), 2)",
    "sum_total_charges": "round(sum(total_charges), 2)",
    "avg_tenure_months": "round(avg(tenure_months), 2)",
    "avg_churn_probability": "round(avg(churn_probability), 5)",
}

SOURCES = {
    "current": sql.SQL("olap.churn_flat"),
    "history": sql.SQL(
        "(select h.*, case h.churn_flag when 1 then 'Yes' else 'No' end as churn_label, "
        "h.date_key / 10000 as year, (h.date_key / 10000) * 10 + ((h.date_key / 100 %% 100) - 1) / 3 + 1 as quarter, "
        "h.date_key / 100 as month from marts.fact_customer_churn_history h) as hist"
    ),
}

Operation = Literal["rollup", "drilldown", "slice", "dice", "pivot"]


class OlapQuery(BaseModel):
    measures: list[str] = Field(default_factory=lambda: ["customer_count", "churned_count", "churn_rate_pct"], min_length=1)
    rows: list[str] = Field(default_factory=list, max_length=4)
    columns: list[str] = Field(default_factory=list, max_length=2)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    operation: Operation = "drilldown"
    source: Literal["current", "history"] = "current"
    limit: int = Field(default=1000, ge=1, le=5000)

    @field_validator("measures")
    @classmethod
    def _known_measures(cls, v: list[str]) -> list[str]:
        unknown = [m for m in v if m not in MEASURES]
        if unknown:
            raise ValueError(f"unknown measures: {', '.join(unknown)}; allowed: {', '.join(MEASURES)}")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _check(self) -> OlapQuery:
        dims = HISTORY_DIMENSIONS if self.source == "history" else CURRENT_DIMENSIONS
        used = self.rows + self.columns + list(self.filters)
        unknown = sorted({d for d in used if d not in dims})
        if unknown:
            raise ValueError(f"unknown dimensions for source '{self.source}': {', '.join(unknown)}")
        if len(set(self.rows + self.columns)) != len(self.rows + self.columns):
            raise ValueError("a dimension cannot appear twice in rows/columns")
        if any(len(v) == 0 or len(v) > 50 for v in self.filters.values()):
            raise ValueError("each filter needs between 1 and 50 values")
        if self.operation == "slice" and (len(self.filters) != 1 or len(next(iter(self.filters.values()))) != 1):
            raise ValueError('slice fixes exactly one dimension to one value, e.g. {"contract_type": ["Month-to-month"]}')
        if self.operation == "dice" and not self.filters:
            raise ValueError("dice needs at least one filter")
        if self.operation == "pivot" and not (self.rows and self.columns):
            raise ValueError("pivot needs at least one row and one column dimension")
        return self


def build(q: OlapQuery) -> tuple[sql.Composed, list[Any]]:
    dims_map = HISTORY_DIMENSIONS if q.source == "history" else CURRENT_DIMENSIONS
    group_dims = q.rows + q.columns
    params: list[Any] = []

    select_parts: list[sql.Composable] = []
    for d in group_dims:
        col = sql.Identifier(dims_map[d])
        if q.operation == "rollup":
            select_parts.append(
                sql.SQL("case when grouping({c}) = 1 then '(All)' else {c}::text end as {a}").format(c=col, a=sql.Identifier(d))
            )
        else:
            select_parts.append(sql.SQL("{c}::text as {a}").format(c=col, a=sql.Identifier(d)))
    if q.operation == "rollup" and group_dims:
        select_parts.append(
            sql.SQL("grouping({}) as grouping_level").format(sql.SQL(", ").join(sql.Identifier(dims_map[d]) for d in group_dims))
        )
    for m in q.measures:
        select_parts.append(sql.SQL("{} as {}").format(sql.SQL(MEASURES[m]), sql.Identifier(m)))

    where_parts: list[sql.Composable] = []
    for d, values in q.filters.items():
        where_parts.append(sql.SQL("{}::text = any(%s)").format(sql.Identifier(dims_map[d])))
        params.append([str(v) for v in values])

    query: list[sql.Composable] = [sql.SQL("select "), sql.SQL(", ").join(select_parts), sql.SQL(" from "), SOURCES[q.source]]
    if where_parts:
        query += [sql.SQL(" where "), sql.SQL(" and ").join(where_parts)]
    if group_dims:
        cols = sql.SQL(", ").join(sql.Identifier(dims_map[d]) for d in group_dims)
        if q.operation == "rollup":
            query += [sql.SQL(" group by rollup ("), cols, sql.SQL(")")]
        else:
            query += [sql.SQL(" group by "), cols]
        order = [sql.SQL("grouping_level")] if q.operation == "rollup" else []
        order += [sql.SQL("{} nulls last").format(sql.Identifier(d)) for d in group_dims]
        query += [sql.SQL(" order by "), sql.SQL(", ").join(order)]
    query += [sql.SQL(" limit %s")]
    params.append(q.limit + 1)  # one extra row tells us the result was truncated
    return sql.Composed(query), params


def pivot(q: OlapQuery, columns: list[str], rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    """Row keys x column keys matrix per measure (for the pivot grid and charts)."""
    idx = {c: i for i, c in enumerate(columns)}
    row_keys: list[list[Any]] = []
    col_keys: list[list[Any]] = []
    cells: dict[tuple[tuple[Any, ...], tuple[Any, ...]], tuple[Any, ...]] = {}
    for r in rows:
        rk = tuple(r[idx[d]] for d in q.rows)
        ck = tuple(r[idx[d]] for d in q.columns)
        if list(rk) not in row_keys:
            row_keys.append(list(rk))
        if list(ck) not in col_keys:
            col_keys.append(list(ck))
        cells[(rk, ck)] = r

    def cell(rk: list[Any], ck: list[Any], m: str) -> Any:
        row = cells.get((tuple(rk), tuple(ck)))
        return None if row is None else row[idx[m]]

    values = {m: [[cell(rk, ck, m) for ck in col_keys] for rk in row_keys] for m in q.measures}
    return {
        "row_dimensions": q.rows,
        "column_dimensions": q.columns,
        "row_keys": row_keys,
        "column_keys": col_keys,
        "values": values,
    }
