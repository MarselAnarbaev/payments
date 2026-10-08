import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from faststream.exceptions import RejectMessage
from pydantic import ValidationError

from app.api.main import app, request_hash
from app.api.schemas import PaymentCreate
from app.core.config import Settings
from app.retry import policy


def body(amount: str = "125.50") -> PaymentCreate:
    return PaymentCreate.model_validate(
        {
            "amount": amount,
            "currency": "RUB",
            "description": "order",
            "metadata": {"order_id": 1},
            "webhook_url": "https://example.com/hook",
        }
    )


def test_payment_input_and_idempotency_fingerprint() -> None:
    assert request_hash(body("125.50")) == request_hash(body("125.5"))
    for amount in ("0", "-1", "NaN", "1.234"):
        with pytest.raises(ValidationError):
            body(amount)
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(body().model_dump() | {"currency": "GBP"})


def test_api_key_required_before_database_access() -> None:
    client = TestClient(app)
    assert client.get(f"/api/v1/payments/{uuid.uuid4()}").status_code == 401
    assert client.post("/api/v1/payments", json=body().model_dump(mode="json")).status_code == 401


def test_api_key_has_no_unsafe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_consumer_retries_three_times_then_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = []
    delays = []

    async def fail(payment_id: uuid.UUID) -> None:
        attempts.append(payment_id)
        raise RuntimeError("webhook unavailable")

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(policy, "process_once", fail)
    monkeypatch.setattr(policy.asyncio, "sleep", fake_sleep)
    payment_id = uuid.uuid4()
    with pytest.raises(RejectMessage):
        asyncio.run(policy.process_with_retry(payment_id))
    assert attempts == [payment_id] * 3
    assert delays == [1, 2]
