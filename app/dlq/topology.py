from faststream.rabbit import RabbitExchange, RabbitQueue


DEAD_EXCHANGE = RabbitExchange("payments.dlx", durable=True)
DEAD_QUEUE = RabbitQueue("payments.dead", durable=True, routing_key="payments.dead")
