"""telco_ops initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.String(20), primary_key=True),
        sa.Column("gender", sa.String(10), nullable=False),
        sa.Column("senior_citizen", sa.SmallInteger, nullable=False),
        sa.Column("partner", sa.String(3), nullable=False),
        sa.Column("dependents", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_customers_updated_at", "customers", ["updated_at"])

    op.create_table(
        "subscriptions",
        sa.Column("subscription_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(20), sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("contract_type", sa.String(20), nullable=False),
        sa.Column("paperless_billing", sa.String(3), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("monthly_charges", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_charges", sa.Numeric(12, 2), nullable=True),
        sa.Column("tenure_months", sa.Integer, nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("churned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("churn_date", sa.Date, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tenure_months >= 0", name="ck_subscriptions_tenure"),
        sa.CheckConstraint("monthly_charges > 0", name="ck_subscriptions_monthly"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_subscriptions_updated_at", "subscriptions", ["updated_at"])

    op.create_table(
        "subscription_services",
        sa.Column("subscription_id", sa.BigInteger, sa.ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("phone_service", sa.String(3), nullable=False),
        sa.Column("multiple_lines", sa.String(20), nullable=False),
        sa.Column("internet_service", sa.String(20), nullable=False),
        sa.Column("online_security", sa.String(25), nullable=False),
        sa.Column("online_backup", sa.String(25), nullable=False),
        sa.Column("device_protection", sa.String(25), nullable=False),
        sa.Column("tech_support", sa.String(25), nullable=False),
        sa.Column("streaming_tv", sa.String(25), nullable=False),
        sa.Column("streaming_movies", sa.String(25), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_subscription_services_updated_at", "subscription_services", ["updated_at"])

    op.create_table(
        "ingestion_batches",
        sa.Column("batch_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="form"),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="RECEIVED"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON, nullable=True),
        sa.Column("received_at", sa.DateTime, nullable=False, server_default=NOW),
        sa.Column("processed_at", sa.DateTime, nullable=True),
        sa.CheckConstraint("status IN ('RECEIVED','VALIDATED','PUBLISHED','FAILED')", name="ck_batches_status"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_ingestion_batches_status", "ingestion_batches", ["status"])

    op.create_table(
        "ingestion_errors",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("ingestion_batches.batch_id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_ingestion_errors_batch", "ingestion_errors", ["batch_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("before_json", sa.JSON, nullable=True),
        sa.Column("after_json", sa.JSON, nullable=True),
        sa.Column("at", sa.DateTime, nullable=False, server_default=NOW),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity", "entity_id"])

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("message_key", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime, nullable=True),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_outbox_unpublished", "event_outbox", ["published_at", "id"])
    op.create_index("ix_event_outbox_batch_id", "event_outbox", ["batch_id"])


def downgrade() -> None:
    for table in ("event_outbox", "audit_log", "ingestion_errors", "ingestion_batches",
                  "subscription_services", "subscriptions", "customers"):
        op.drop_table(table)
