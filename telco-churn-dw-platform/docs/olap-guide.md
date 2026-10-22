# OLAP guide

`POST /api/v1/analytics/olap/query`

```json
{
  "measures": ["customer_count", "churned_count", "churn_rate_pct"],
  "rows": ["contract_type"],
  "columns": [],
  "filters": {},
  "operation": "drilldown",
  "source": "current",
  "limit": 1000
}
```

- **Measures**: `customer_count`, `churned_count`, `churn_rate_pct`, `avg_monthly_charges`, `sum_total_charges`, `avg_tenure_months`, `avg_churn_probability`.
- **Dimensions (`source: current`)**: `contract_type`, `paperless_billing`, `payment_method`, `is_automatic`, `internet_service`, `phone_service`, `multiple_lines`, `online_security`, `online_backup`, `device_protection`, `tech_support`, `streaming_tv`, `streaming_movies`, `tenure_band`, `partner`, `dependents`, `gender`, `senior_citizen`, `churn_label`.
- **Dimensions (`source: history`)**: `contract_type`, `paperless_billing`, `payment_method`, `internet_service`, `tenure_band`, `churn_label`, `year`, `quarter`, `month` (from the daily `fact_customer_churn_history`; counts are customer-days).

Anything else is rejected with 422. The response contains `columns`, `rows`, `row_count`, `truncated`, `elapsed_ms`, and for pivots a `pivot` matrix.

## Roll-up

Subtotals at every level of the row hierarchy; subtotal cells are labelled `(All)` and `grouping_level` tells the level.

```json
{ "rows": ["contract_type", "payment_method"], "operation": "rollup", "measures": ["customer_count", "churn_rate_pct"] }
```

Time roll-up month → quarter → year:

```json
{ "rows": ["year", "quarter", "month"], "operation": "rollup", "source": "history", "measures": ["customer_count"] }
```

SQL generated: `GROUP BY ROLLUP (contract_type, payment_method)`.

## Drill-down

Add the next dimension to `rows`: `contract_type` → `contract_type, payment_method` → `+ internet_service`.

```json
{ "rows": ["contract_type", "payment_method", "internet_service"], "operation": "drilldown" }
```

## Slice

Fix exactly one dimension to one value:

```json
{ "rows": ["payment_method"], "filters": { "contract_type": ["Month-to-month"] }, "operation": "slice" }
```

## Dice

Filter on several dimensions with value lists:

```json
{ "rows": ["contract_type"], "filters": { "contract_type": ["One year", "Two year"], "payment_method": ["Electronic check", "Mailed check"] }, "operation": "dice" }
```

## Pivot

Rows × columns matrix (the PWA can swap them):

```json
{ "rows": ["contract_type"], "columns": ["internet_service"], "operation": "pivot", "measures": ["churn_rate_pct"] }
```

## Acceptance figures

| Query | Expected |
|---|---|
| rows `contract_type` | Month-to-month 1,655 / 3,875 (42.71%) · One year 166 / 1,473 (11.27%) · Two year 48 / 1,695 (2.83%) |
| rows `tenure_band` | 0–12: 1,037 / 2,186 (47.44%) |
| rows `payment_method` | Electronic check 1,071 / 2,365 (45.29%) |

These are checked automatically by `transform/dbt_telco/scripts/reconcile.py` and by `services/analytics_api/tests/test_api_integration.py`.

## Pre-aggregated views

`olap.mv_churn_by_contract_payment` (ROLLUP), `olap.mv_churn_by_tenure_band` (ROLLUP) and `olap.mv_churn_cube` (CUBE over contract, payment, internet service and tenure band; `grouping_id` 0–15) are refreshed `CONCURRENTLY` after every dbt run, so readers are never blocked. They can be queried directly with the read-only `dw_analytics` role, for example from Grafana.
