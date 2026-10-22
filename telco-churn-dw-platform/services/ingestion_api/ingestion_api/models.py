"""telco_ops schema (3NF). Alembic migrations in migrations/ create these tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# BigInteger autoincrement does not work on SQLite (used in unit tests).
BigId = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    gender: Mapped[str] = mapped_column(String(10))
    senior_citizen: Mapped[int] = mapped_column(SmallInteger)
    partner: Mapped[str] = mapped_column(String(3))
    dependents: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    subscription: Mapped[Subscription | None] = relationship(back_populates="customer", uselist=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"), unique=True)
    contract_type: Mapped[str] = mapped_column(String(20))
    paperless_billing: Mapped[str] = mapped_column(String(3))
    payment_method: Mapped[str] = mapped_column(String(30))
    monthly_charges: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_charges: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tenure_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    churned: Mapped[bool] = mapped_column(Boolean, default=False)
    churn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), index=True
    )

    customer: Mapped[Customer] = relationship(back_populates="subscription")
    services: Mapped[SubscriptionServices | None] = relationship(
        back_populates="subscription", uselist=False, cascade="all, delete-orphan"
    )


class SubscriptionServices(Base):
    __tablename__ = "subscription_services"

    subscription_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"), primary_key=True
    )
    phone_service: Mapped[str] = mapped_column(String(3))
    multiple_lines: Mapped[str] = mapped_column(String(20))
    internet_service: Mapped[str] = mapped_column(String(20))
    online_security: Mapped[str] = mapped_column(String(25))
    online_backup: Mapped[str] = mapped_column(String(25))
    device_protection: Mapped[str] = mapped_column(String(25))
    tech_support: Mapped[str] = mapped_column(String(25))
    streaming_tv: Mapped[str] = mapped_column(String(25))
    streaming_movies: Mapped[str] = mapped_column(String(25))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), index=True
    )

    subscription: Mapped[Subscription] = relationship(back_populates="services")


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    client_id: Mapped[str] = mapped_column(String(64))
    submitted_by: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16), default="form")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="RECEIVED", index=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    __table_args__ = (Index("ix_ingestion_errors_batch", "batch_id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("ingestion_batches.batch_id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(16))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())


class EventOutbox(Base):
    """Transactional outbox: events are written with the data change and relayed to Kafka."""

    __tablename__ = "event_outbox"
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    topic: Mapped[str] = mapped_column(String(64))
    message_key: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
