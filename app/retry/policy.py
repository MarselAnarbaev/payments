import asyncio
import logging
import uuid

from faststream.exceptions import RejectMessage

from app.consumer.processor import process_once


logger = logging.getLogger(__name__)


async def process_with_retry(payment_id: uuid.UUID) -> None:
    # Всего три попытки; после последней RabbitMQ направит сообщение в DLQ.
    for attempt in range(1, 4):
        try:
            await process_once(payment_id)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment handling failed on attempt %s of 3", attempt)
            if attempt == 3:
                raise RejectMessage from None
            await asyncio.sleep(2 ** (attempt - 1))
