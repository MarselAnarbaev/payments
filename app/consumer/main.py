import asyncio
import uuid

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.core.config import get_settings
from app.dlq.topology import DEAD_EXCHANGE, DEAD_QUEUE
from app.messaging.topology import PAYMENTS_QUEUE
from app.outbox.publisher import run_outbox_publisher
from app.retry.policy import process_with_retry


broker = RabbitBroker(get_settings().rabbitmq_url)
app = FastStream(broker)
publisher_task: asyncio.Task | None = None


@broker.subscriber(PAYMENTS_QUEUE)
async def handle_payment(message: dict[str, str]) -> None:
    await process_with_retry(uuid.UUID(message["payment_id"]))


@app.after_startup
async def start_publisher() -> None:
    global publisher_task
    # Объявляем DLQ до публикации первого события из outbox.
    exchange = await broker.declare_exchange(DEAD_EXCHANGE)
    queue = await broker.declare_queue(DEAD_QUEUE)
    await queue.bind(exchange, routing_key="payments.dead")
    publisher_task = asyncio.create_task(run_outbox_publisher(broker))


@app.on_shutdown
async def stop_publisher() -> None:
    if publisher_task is not None:
        publisher_task.cancel()
        try:
            await publisher_task
        except asyncio.CancelledError:
            pass
