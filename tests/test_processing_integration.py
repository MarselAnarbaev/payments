import asyncio
import os
import uuid
from decimal import Decimal

import httpx
import pytest

from app.consumer import processor
from app.db.models import Payment
from app.db.session import engine, session_factory


@pytest.mark.skipif(not os.getenv("RUN_DB_INTEGRATION"), reason="requires running PostgreSQL")
@pytest.mark.parametrize("gateway_result, expected_status", [(0.1, "succeeded"), (0.95, "failed")])
def test_gateway_webhook_and_duplicate_delivery(monkeypatch, gateway_result, expected_status) -> None:
    events = []
    original_client = httpx.AsyncClient

    def receive(request: httpx.Request) -> httpx.Response:
        events.append((request.headers["Idempotency-Key"], request.content))
        return httpx.Response(204)

    monkeypatch.setattr(processor.random, "uniform", lambda low, high: 0)
    monkeypatch.setattr(processor.random, "random", lambda: gateway_result)
    monkeypatch.setattr(
        processor.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(receive)),
    )
    payment_id = uuid.uuid4()

    async def exercise() -> None:
        async with session_factory() as session:
            async with session.begin():
                session.add(
                    Payment(
                        id=payment_id,
                        amount=Decimal("125.50"),
                        currency="RUB",
                        description="integration test",
                        metadata_json={},
                        idempotency_key=f"integration-{payment_id}",
                        request_hash="test",
                        webhook_url="https://example.com/hook",
                    )
                )
        await processor.process_once(payment_id)
        await processor.process_once(payment_id)
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id)
            assert payment.status == expected_status
            assert payment.processed_at is not None
            assert payment.webhook_sent_at is not None
            await session.delete(payment)
            await session.commit()
        await engine.dispose()

    asyncio.run(exercise())
    assert len(events) == 1
    assert events[0][0] == f"payment.result:{payment_id}"
