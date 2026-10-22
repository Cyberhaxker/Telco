from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

YesNo = Literal["Yes", "No"]
Addon = Literal["Yes", "No", "No internet service"]


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,19}$")
    gender: Literal["Female", "Male"]
    senior_citizen: Literal[0, 1]
    partner: YesNo
    dependents: YesNo


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gender: Literal["Female", "Male"]
    senior_citizen: Literal[0, 1]
    partner: YesNo
    dependents: YesNo
    version: int = Field(ge=1, description="Server version the client last saw")


class SubscriptionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_type: Literal["Month-to-month", "One year", "Two year"]
    paperless_billing: YesNo
    payment_method: Literal["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"]
    monthly_charges: float = Field(gt=0, le=10000)
    total_charges: float | None = Field(default=None, ge=0)
    tenure_months: int = Field(ge=0, le=600)
    churned: bool = False
    phone_service: YesNo
    multiple_lines: Literal["Yes", "No", "No phone service"]
    internet_service: Literal["DSL", "Fiber optic", "No"]
    online_security: Addon
    online_backup: Addon
    device_protection: Addon
    tech_support: Addon
    streaming_tv: Addon
    streaming_movies: Addon


class SubscriptionIn(SubscriptionFields):
    customer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,19}$")
    version: int = Field(ge=1, description="Current customer version")


class SubscriptionUpdate(SubscriptionFields):
    version: int = Field(ge=1)


class CustomerOut(BaseModel):
    customer_id: str
    gender: str
    senior_citizen: int
    partner: str
    dependents: str
    version: int
    created_at: str | None = None
    updated_at: str | None = None
    subscription: dict[str, Any] | None = None


class BatchResult(BaseModel):
    batch_id: str
    status: Literal["RECEIVED", "VALIDATED", "PUBLISHED", "FAILED"]
    outcome: Literal["ACCEPTED", "PARTIAL", "REJECTED"]
    accepted_count: int
    rejected_count: int
    errors: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    replayed: bool = False


class BatchSummary(BaseModel):
    batch_id: str
    client_id: str
    submitted_by: str
    source: str
    status: str
    record_count: int
    accepted_count: int
    rejected_count: int
    conflict_count: int
    received_at: str
    processed_at: str | None


class CsvUploadResult(BaseModel):
    file_sha256: str
    row_count: int
    accepted_count: int
    rejected_count: int
    conflict_count: int
    batches: list[BatchResult]
