import asyncio
import random
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.db.models import Payment
from app.db.session import session_factory


async def process_once(payment_id: uuid.UUID) -> None:
    # Блокировка строки не даёт повторной доставке запустить эмуляцию шлюза ещё раз.
    async with session_factory() as session:
        async with session.begin():
            payment = await session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
            if payment is None:
                raise ValueError(f"Unknown payment: {payment_id}")
            if payment.status == "pending":
                # Отказ шлюза — штатный итог платежа, а не ошибка доставки сообщения.
                await asyncio.sleep(random.uniform(2.0, 5.0))
                payment.status = "succeeded" if random.random() < 0.9 else "failed"
                payment.processed_at = datetime.now(timezone.utc)

    # Статус уже сохранён: при сбое webhook повторяется только уведомление.
    # Вторая блокировка исключает одновременную отправку при дублировании сообщения.
    async with session_factory() as session:
        async with session.begin():
            payment = await session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
            if payment is None:
                raise ValueError(f"Unknown payment: {payment_id}")
            if payment.webhook_sent_at is not None:
                return
            event_id = f"payment.result:{payment.id}"
            payload = {
                "event_id": event_id,
                "payment_id": str(payment.id),
                "status": payment.status,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "processed_at": payment.processed_at.isoformat(),
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    payment.webhook_url,
                    json=payload,
                    headers={"Idempotency-Key": event_id},
                )
                response.raise_for_status()
            payment.webhook_sent_at = datetime.now(timezone.utc)
