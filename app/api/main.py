import hashlib
import json
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_api_key
from app.api.schemas import PaymentAccepted, PaymentCreate, PaymentDetail
from app.db.models import Outbox, Payment
from app.db.session import get_session


app = FastAPI(title="Payment Processing Service", dependencies=[Depends(require_api_key)])


def request_hash(body: PaymentCreate) -> str:
    normalized = body.model_dump(mode="json")
    # Одинаковые суммы вида 125.5 и 125.50 должны иметь один отпечаток запроса.
    normalized["amount"] = str(body.amount.quantize(Decimal("0.01")))
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@app.post("/api/v1/payments", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentAccepted:
    fingerprint = request_hash(body)
    payment_id = uuid.uuid4()
    # Платёж и событие outbox фиксируются атомарно в одной транзакции.
    async with session.begin():
        statement = (
            insert(Payment)
            .values(
                id=payment_id,
                amount=body.amount,
                currency=body.currency,
                description=body.description,
                metadata_json=body.metadata,
                status="pending",
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
                webhook_url=str(body.webhook_url),
            )
            .on_conflict_do_nothing(index_elements=[Payment.idempotency_key])
            .returning(Payment.id)
        )
        inserted_id = await session.scalar(statement)
        if inserted_id is not None:
            session.add(
                Outbox(
                    payment_id=inserted_id,
                    event_type="payment.created",
                    payload={"payment_id": str(inserted_id)},
                )
            )
            payment = await session.get(Payment, inserted_id)
        else:
            # Уникальный ключ также защищает от двух одновременных POST-запросов.
            payment = await session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
            if payment is None:
                raise RuntimeError("Idempotency conflict without existing payment")
            if payment.request_hash != fingerprint:
                raise HTTPException(status_code=409, detail="Idempotency key was used with a different request")
    return PaymentAccepted(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@app.get("/api/v1/payments/{payment_id}", response_model=PaymentDetail)
async def get_payment(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentDetail:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentDetail(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.metadata_json,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        webhook_url=payment.webhook_url,
        created_at=payment.created_at,
        processed_at=payment.processed_at,
        webhook_sent_at=payment.webhook_sent_at,
    )
