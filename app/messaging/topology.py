from faststream.rabbit import RabbitQueue


PAYMENTS_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    # Окончательно отклонённые сообщения RabbitMQ переносит в payments.dead.
    arguments={
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.dead",
    },
)
