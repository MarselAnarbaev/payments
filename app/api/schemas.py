import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


Currency = Literal["RUB", "USD", "EUR"]
PaymentStatus = Literal["pending", "succeeded", "failed"]


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value


class PaymentAccepted(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime


class PaymentDetail(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "payment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "amount": "125.50",
                "currency": "RUB",
                "description": "Order 1001",
                "metadata": {"order_id": 1001},
                "status": "succeeded",
                "idempotency_key": "order-1001",
                "webhook_url": "https://example.com/payment-webhook",
                "created_at": "2026-10-08T12:41:15.996Z",
                "processed_at": "2026-10-08T12:41:19.996Z",
                "webhook_sent_at": "2026-10-08T12:41:20.996Z",
            }
        },
    )

    payment_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: HttpUrl
    created_at: datetime
    processed_at: datetime | None
    webhook_sent_at: datetime | None
