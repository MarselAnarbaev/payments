import asyncio
import logging
from datetime import datetime, timezone

from faststream.rabbit import RabbitBroker
from pamqp.commands import Basic
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Outbox
from app.db.session import session_factory
from app.messaging.topology import PAYMENTS_QUEUE


logger = logging.getLogger(__name__)


async def publish_pending(broker: RabbitBroker) -> int:
    count = 0
    async with session_factory() as session:
        async with session.begin():
            # SKIP LOCKED позволяет нескольким publisher-процессам не брать одну запись.
            rows = (
                await session.scalars(
                    select(Outbox)
                    .where(Outbox.published_at.is_(None))
                    .order_by(Outbox.created_at, Outbox.id)
                    .limit(20)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                confirmation = await broker.publish(
                    row.payload,
                    queue=PAYMENTS_QUEUE,
                    message_id=str(row.id),
                    persist=True,
                    mandatory=True,
                )
                if not isinstance(confirmation, Basic.Ack):
                    raise RuntimeError(f"RabbitMQ did not confirm outbox message {row.id}: {confirmation!r}")
                # Ставим отметку только после подтверждения брокера.
                row.published_at = datetime.now(timezone.utc)
                count += 1
    return count


async def run_outbox_publisher(broker: RabbitBroker) -> None:
    while True:
        try:
            count = await publish_pending(broker)
            if count == 0:
                await asyncio.sleep(get_settings().outbox_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox publication failed; will retry")
            await asyncio.sleep(get_settings().outbox_poll_seconds)
