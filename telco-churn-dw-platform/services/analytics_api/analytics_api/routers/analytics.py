from __future__ import annotations

import hashlib
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from telco_common.auth import Principal, require_roles
from telco_common.pagination import Page, PageParams, page_params
from telco_common.problems import ProblemError

from ..deps import CacheDep, ModelsDep, PoolDep, SettingsDep, fetch, to_json_value
from ..olap import CURRENT_DIMENSIONS, HISTORY_DIMENSIONS, MEASURES, OlapQuery, build, pivot

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

Viewer = Annotated[Principal, Depends(require_roles("viewer", "analyst"))]
Analyst = Annotated[Principal, Depends(require_roles("analyst"))]

YesNo = Literal["Yes", "No"]
Addon = Literal["Yes", "No", "No internet service"]


# ------------------------------------------------------------------ OLAP
@router.get("/olap/dimensions")
async def olap_dimensions(_: Analyst, pool: PoolDep, cache: CacheDep) -> dict[str, Any]:
    async def produce() -> dict[str, Any]:
        members: dict[str, list[str]] = {}
        for d, col in CURRENT_DIMENSIONS.items():
            _, rows = await fetch(pool, f'select distinct "{col}"::text from olap.churn_flat order by 1')  # col from whitelist
            members[d] = [r[0] for r in rows]
        return {
            "dimensions": members,
            "history_dimensions": list(HISTORY_DIMENSIONS),
            "measures": list(MEASURES),
            "operations": ["rollup", "drilldown", "slice", "dice", "pivot"],
        }

    value, _ = await cache.get_or_set("olap:dimensions", produce)
    return value  # type: ignore[no-any-return]


@router.post("/olap/query", summary="Run an OLAP query (roll-up, drill-down, slice, dice, pivot)")
async def olap_query(q: OlapQuery, _: Analyst, pool: PoolDep, cache: CacheDep, settings: SettingsDep) -> dict[str, Any]:
    key = "olap:" + hashlib.sha256(q.model_dump_json().encode()).hexdigest()

    async def produce() -> dict[str, Any]:
        query, params = build(q)
        started = time.perf_counter()
        cols, rows = await fetch(pool, query, params)
        truncated = len(rows) > q.limit
        rows = rows[: q.limit]
        out_rows = [[to_json_value(v) for v in r] for r in rows]
        result: dict[str, Any] = {
            "query": q.model_dump(),
            "columns": cols,
            "rows": out_rows,
            "row_count": len(out_rows),
            "truncated": truncated,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        if q.columns and q.operation != "rollup":
            result["pivot"] = pivot(q, cols, [tuple(r) for r in out_rows])
        return result

    value, cached = await cache.get_or_set(key, produce)
    return {**value, "cached": cached}


# ------------------------------------------------------------------ KPIs
@router.get("/kpis")
async def kpis(_: Viewer, pool: PoolDep, cache: CacheDep, settings: SettingsDep) -> dict[str, Any]:
    async def produce() -> dict[str, Any]:
        _, rows = await fetch(
            pool,
            """
            select count(*), sum(churn_flag), round(100.0 * sum(churn_flag) / nullif(count(*), 0), 2),
                   round(avg(monthly_charges), 2), round(avg(churn_probability), 4), max(snapshot_date)
            from olap.churn_flat""",
        )
        total, churned, rate, avg_monthly, avg_prob, snapshot = rows[0]
        _, risk = await fetch(
            pool,
            """
            select count(*) filter (where p.risk_band = 'high'), count(*) filter (where p.risk_band = 'medium'),
                   max(p.scored_at)
            from ml.current_predictions p
            join olap.churn_flat f on f.customer_id = p.customer_id and f.churn_flag = 0""",
        )
        high, medium, scored_at = risk[0]
        _, by_contract = await fetch(
            pool,
            """
            select contract_type, customer_count, churned_count, churn_rate_pct
            from olap.mv_churn_by_contract_payment where payment_method = '(All)' and contract_type <> '(All)'
            order by contract_type""",
        )
        _, by_tenure = await fetch(
            pool,
            """
            select tenure_band, customer_count, churned_count, churn_rate_pct
            from olap.mv_churn_by_tenure_band where tenure_band <> '(All)' order by tenure_band_order""",
        )
        _, by_payment = await fetch(
            pool,
            """
            select payment_method, customer_count, churned_count, churn_rate_pct
            from olap.mv_churn_cube where grouping_id = 11 order by churn_rate_pct desc""",
        )
        conv = lambda rs: [{"label": r[0], "customers": r[1], "churned": r[2], "churn_rate_pct": to_json_value(r[3])} for r in rs]  # noqa: E731
        return {
            "total_customers": total,
            "churned_customers": churned,
            "churn_rate_pct": to_json_value(rate),
            "avg_monthly_charges": to_json_value(avg_monthly),
            "avg_churn_probability": to_json_value(avg_prob),
            "high_risk_active_customers": high,
            "medium_risk_active_customers": medium,
            "snapshot_date": to_json_value(snapshot),
            "scored_at": to_json_value(scored_at),
            "high_risk_threshold": settings.ml_high_risk_threshold,
            "churn_by_contract": conv(by_contract),
            "churn_by_tenure_band": conv(by_tenure),
            "churn_by_payment_method": conv(by_payment),
        }

    value, cached = await cache.get_or_set("kpis", produce)
    return {**value, "cached": cached}


# ------------------------------------------------------------------ predictions
PREDICTION_COLUMNS = """
    p.customer_id, p.churn_probability, p.predicted_label, p.risk_band, p.top_factors, p.model_version, p.scored_at,
    f.contract_type, f.payment_method, f.internet_service, f.tenure_months, f.tenure_band,
    f.monthly_charges, f.churn_label
"""


def _prediction(cols: list[str], r: tuple[Any, ...]) -> dict[str, Any]:
    return {c: to_json_value(v) for c, v in zip(cols, r, strict=True)}


@router.get("/predictions", response_model=Page[dict[str, Any]])
async def list_predictions(
    _: Analyst,
    pool: PoolDep,
    page: Annotated[PageParams, Depends(page_params)],
    risk: Annotated[Literal["high", "medium", "low"] | None, Query()] = None,
    contract_type: Annotated[str | None, Query(max_length=20)] = None,
    min_probability: Annotated[float | None, Query(ge=0, le=1)] = None,
    include_churned: bool = False,
    sort: Annotated[
        Literal["probability_desc", "probability_asc", "monthly_charges_desc", "tenure_asc"], Query()
    ] = "probability_desc",
) -> Page[dict[str, Any]]:
    where = ["true"]
    params: list[Any] = []
    if not include_churned:
        where.append("f.churn_flag = 0")
    if risk:
        where.append("p.risk_band = %s")
        params.append(risk)
    if contract_type:
        where.append("f.contract_type = %s")
        params.append(contract_type)
    if min_probability is not None:
        where.append("p.churn_probability >= %s")
        params.append(min_probability)
    order = {
        "probability_desc": "p.churn_probability desc",
        "probability_asc": "p.churn_probability asc",
        "monthly_charges_desc": "f.monthly_charges desc",
        "tenure_asc": "f.tenure_months asc",
    }[sort]
    base = f"from ml.current_predictions p join olap.churn_flat f on f.customer_id = p.customer_id where {' and '.join(where)}"
    _, total = await fetch(pool, f"select count(*) {base}", params)
    cols, rows = await fetch(
        pool,
        f"select {PREDICTION_COLUMNS} {base} order by {order}, p.customer_id limit %s offset %s",
        [*params, page.limit, page.offset],
    )
    return Page(items=[_prediction(cols, r) for r in rows], total=total[0][0], limit=page.limit, offset=page.offset)


@router.get("/predictions/{customer_id}")
async def get_prediction(customer_id: str, _: Analyst, pool: PoolDep) -> dict[str, Any]:
    cols, rows = await fetch(
        pool,
        f"""
        select {PREDICTION_COLUMNS}, f.gender, f.senior_citizen, f.partner, f.dependents, f.paperless_billing,
               f.phone_service, f.multiple_lines, f.online_security, f.online_backup, f.device_protection,
               f.tech_support, f.streaming_tv, f.streaming_movies, f.total_charges
        from olap.churn_flat f left join ml.current_predictions p on p.customer_id = f.customer_id
        where f.customer_id = %s""",
        [customer_id],
    )
    if not rows:
        raise ProblemError(404, "Not Found", f"Customer {customer_id} is not in the warehouse")
    out = _prediction(cols, rows[0])
    out["customer_id"] = customer_id
    out["note"] = "Top factors show how much the model relies on each attribute for this customer, not what causes churn."
    return out


class Profile(BaseModel):
    """A customer profile to score. Protected attributes are not used by the model."""

    tenure_months: int = Field(ge=0, le=600)
    monthly_charges: float = Field(gt=0, le=10000)
    total_charges: float | None = Field(default=None, ge=0)
    partner: YesNo
    dependents: YesNo
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


@router.post("/predict", summary="Score an ad-hoc customer profile with the champion model")
async def predict(profile: Profile, _: Analyst, models: ModelsDep) -> dict[str, Any]:
    try:
        return models.predict(profile.model_dump())
    except LookupError as exc:
        raise ProblemError(503, "Service Unavailable", str(exc), headers={"Retry-After": "60"}) from exc


# ------------------------------------------------------------------ models
@router.get("/models")
async def model_registry(_: Analyst, pool: PoolDep, models: ModelsDep, settings: SettingsDep) -> dict[str, Any]:
    cols, rows = await fetch(
        pool,
        """
        select run_id, training_run_id, algorithm, holdout_metrics, cv_metrics, confusion_matrix, threshold,
               feature_importance, registered_version, is_champion, trained_at
        from ml.model_runs
        where training_run_id = (select training_run_id from ml.model_runs order by trained_at desc limit 1)
           or is_champion
        order by trained_at desc, algorithm""",
    )
    runs = [{c: to_json_value(v) for c, v in zip(cols, r, strict=True)} for r in rows]
    fcols, frows = await fetch(
        pool,
        """
        select attribute, group_value, n, positive_rate, tpr, fpr from ml.fairness_metrics
        where run_id = (select run_id from ml.model_runs where is_champion order by trained_at desc limit 1)
        order by attribute, group_value""",
    )
    dcols, drows = await fetch(
        pool,
        """
        select feature, psi, status, computed_at from ml.drift_metrics
        where scoring_run_id = (select scoring_run_id from ml.drift_metrics order by computed_at desc limit 1)
        order by psi desc""",
    )
    champ = models.champion
    return {
        "model_name": settings.ml_model_name,
        "champion": None
        if champ is None
        else {"version": champ.version, "algorithm": champ.algorithm, "threshold": champ.threshold, "loaded_from": champ.source},
        "runs": runs,
        "fairness": [{c: to_json_value(v) for c, v in zip(fcols, r, strict=True)} for r in frows],
        "drift": [{c: to_json_value(v) for c, v in zip(dcols, r, strict=True)} for r in drows],
        "baseline": {
            "LogisticRegression": {"accuracy": 0.8055, "precision": 0.6572, "recall": 0.5588, "f1": 0.6040, "roc_auc": 0.8419},
            "DecisionTree": {"accuracy": 0.7984, "precision": 0.6347, "recall": 0.5668, "f1": 0.5989, "roc_auc": 0.8282},
            "RandomForest": {"accuracy": 0.7587, "precision": 0.5311, "recall": 0.7754, "f1": 0.6304, "roc_auc": 0.8410},
            "GradientBoosting": {"accuracy": 0.8055, "precision": 0.6761, "recall": 0.5134, "f1": 0.5836, "roc_auc": 0.8455},
        },
    }
