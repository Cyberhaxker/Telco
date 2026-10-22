"""Single-record CRUD for customers and subscriptions (used by the PWA forms when online)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from telco_common.auth import Principal, require_roles
from telco_common.pagination import Page, PageParams, page_params
from telco_common.problems import ProblemError
from telco_common.records import validate_record

from ..deps import SessionDep, wake_relay
from ..models import AuditLog, Customer
from ..schemas import CustomerIn, CustomerOut, CustomerUpdate, SubscriptionIn, SubscriptionUpdate
from ..service import CUSTOMER_FIELDS, customer_to_dict, record_from_db, subscription_to_dict, upsert_record

router = APIRouter(prefix="/api/v1/ingest", tags=["records"])

Writer = Annotated[Principal, Depends(require_roles("data_entry"))]
Reader = Annotated[Principal, Depends(require_roles("data_entry", "data_steward"))]


def _out(c: Customer) -> CustomerOut:
    return CustomerOut(**customer_to_dict(c), subscription=subscription_to_dict(c))


def _load(session: SessionDep, customer_id: str, lock: bool = False) -> Customer:
    stmt = select(Customer).where(Customer.customer_id == customer_id).options(selectinload(Customer.subscription))
    if lock and session.bind is not None and session.bind.dialect.name == "mysql":
        stmt = stmt.with_for_update()
    c = session.execute(stmt).scalar_one_or_none()
    if c is None:
        raise ProblemError(404, "Not Found", f"Customer {customer_id} does not exist")
    return c


def _conflict(c: Customer, client_version: int) -> ProblemError:
    return ProblemError(
        409,
        "Conflict",
        "The record was changed by someone else. Review the server version and resubmit.",
        type_="https://telco.local/problems/version-conflict",
        conflicts=[
            {
                "customer_id": c.customer_id,
                "server_version": c.version,
                "client_version": client_version,
                "server_record": record_from_db(c) or customer_to_dict(c),
            }
        ],
    )


def _validated_full(record: dict[str, Any]):  # type: ignore[no-untyped-def]
    rec, errors = validate_record(record, 0)
    if rec is None:
        raise ProblemError(
            422,
            "Unprocessable Content",
            "Record failed validation",
            type_="https://telco.local/problems/validation",
            errors=[e.as_dict() for e in errors],
        )
    return rec


# ------------------------------------------------------------------ customers
@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    session: SessionDep,
    _: Reader,
    page: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(max_length=20, description="customer_id prefix")] = None,
) -> Page[CustomerOut]:
    base = select(Customer)
    if search:
        base = base.where(or_(Customer.customer_id.like(f"{search}%")))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.options(selectinload(Customer.subscription))
        .order_by(Customer.updated_at.desc(), Customer.customer_id)
        .limit(page.limit)
        .offset(page.offset)
    ).scalars()
    return Page(items=[_out(c) for c in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, session: SessionDep, _: Reader, response: Response) -> CustomerOut:
    c = _load(session, customer_id)
    response.headers["ETag"] = f'"{c.version}"'
    return _out(c)


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(body: CustomerIn, session: SessionDep, principal: Writer) -> CustomerOut:
    if session.get(Customer, body.customer_id) is not None:
        raise ProblemError(409, "Conflict", f"Customer {body.customer_id} already exists; use PUT to update it")
    c = Customer(**body.model_dump(), version=1)
    session.add(c)
    session.flush()
    session.add(
        AuditLog(
            actor=principal.username, action="create", entity="customer", entity_id=c.customer_id, after_json=customer_to_dict(c)
        )
    )
    session.commit()
    session.refresh(c)
    return _out(c)


@router.put("/customers/{customer_id}", response_model=CustomerOut, dependencies=[Depends(wake_relay)])
def update_customer(customer_id: str, body: CustomerUpdate, session: SessionDep, principal: Writer) -> CustomerOut:
    c = _load(session, customer_id, lock=True)
    if body.version != c.version:
        raise _conflict(c, body.version)
    full = record_from_db(c)
    if full is not None:
        rec = _validated_full({**full, **body.model_dump(exclude={"version"}), "version": body.version})
        result = upsert_record(session, rec, actor=principal.username, batch_id=None)
        if result.status == "conflict":
            raise _conflict(c, body.version)
    else:
        before = customer_to_dict(c)
        for f in CUSTOMER_FIELDS:
            setattr(c, f, getattr(body, f))
        c.version += 1
        session.flush()
        session.add(
            AuditLog(
                actor=principal.username,
                action="update",
                entity="customer",
                entity_id=c.customer_id,
                before_json=before,
                after_json=customer_to_dict(c),
            )
        )
    session.commit()
    session.refresh(c)
    return _out(c)


# ------------------------------------------------------------------ subscriptions
@router.get("/subscriptions", response_model=Page[dict[str, Any]])
def list_subscriptions(
    session: SessionDep,
    _: Reader,
    page: Annotated[PageParams, Depends(page_params)],
    customer_id: str | None = None,
) -> Page[dict[str, Any]]:
    base = select(Customer).where(Customer.subscription.has())
    if customer_id:
        base = base.where(Customer.customer_id == customer_id)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.options(selectinload(Customer.subscription)).order_by(Customer.customer_id).limit(page.limit).offset(page.offset)
    ).scalars()
    return Page(items=[s for c in rows if (s := subscription_to_dict(c))], total=total, limit=page.limit, offset=page.offset)


def _write_subscription(
    session: SessionDep, principal: Principal, customer_id: str, fields: dict[str, Any], version: int, must_be_new: bool
) -> CustomerOut:
    c = _load(session, customer_id, lock=True)
    if must_be_new and c.subscription is not None:
        raise ProblemError(409, "Conflict", f"Customer {customer_id} already has a subscription; use PUT")
    if not must_be_new and c.subscription is None:
        raise ProblemError(404, "Not Found", f"Customer {customer_id} has no subscription; use POST")
    if version != c.version:
        raise _conflict(c, version)
    record = {"customer_id": c.customer_id, **{f: getattr(c, f) for f in CUSTOMER_FIELDS}, **fields, "version": version}
    record["senior_citizen"] = int(record["senior_citizen"])
    rec = _validated_full(record)
    result = upsert_record(session, rec, actor=principal.username, batch_id=None)
    if result.status == "conflict":
        raise _conflict(c, version)
    if result.status == "unchanged" and must_be_new:
        raise ProblemError(409, "Conflict", "Subscription already exists")
    session.commit()
    session.refresh(c)
    return _out(c)


@router.post(
    "/subscriptions", response_model=CustomerOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(wake_relay)]
)
def create_subscription(body: SubscriptionIn, session: SessionDep, principal: Writer) -> CustomerOut:
    fields = body.model_dump(exclude={"customer_id", "version"})
    return _write_subscription(session, principal, body.customer_id, fields, body.version, must_be_new=True)


@router.put("/subscriptions/{customer_id}", response_model=CustomerOut, dependencies=[Depends(wake_relay)])
def update_subscription(customer_id: str, body: SubscriptionUpdate, session: SessionDep, principal: Writer) -> CustomerOut:
    fields = body.model_dump(exclude={"version"})
    return _write_subscription(session, principal, customer_id, fields, body.version, must_be_new=False)
