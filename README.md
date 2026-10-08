# Асинхронный сервис процессинга платежей

Реализация задания из `Тестовое PYTHON .pdf`: FastAPI, PostgreSQL, RabbitMQ/FastStream, transactional outbox, consumer, webhook, retry и DLQ.

## Структура

- `app/api/` — HTTP API и авторизация.
- `app/db/` — асинхронные модели SQLAlchemy и сессии.
- `app/outbox/` — публикация сохранённых событий.
- `app/consumer/` — один обработчик платежа и webhook.
- `app/messaging/` — конфигурация очередей и обменников.
- `app/retry/` — три попытки с экспоненциальной задержкой.
- `app/dlq/` — конфигурация dead letter exchange и очереди.
- `alembic/` — миграции PostgreSQL.
- `docker/api/`, `docker/consumer/` — отдельные Dockerfile компонентов.
- `docs/` — описание архитектуры и гарантий.
- `tests/` — проверки контракта и обработки.

## Запуск

1. Скопируйте `.env.example` в `.env` и заполните обязательный `API_KEY` случайным секретом. Без него Compose не запустится.
2. Выполните `docker compose up --build -d`.
3. Откройте `http://localhost:8000/docs` или вызовите API. Миграции запускаются до старта API и consumer отдельным сервисом Compose.

RabbitMQ Management: `http://localhost:15672` (логин и пароль из `.env`). API: `http://localhost:8000`. Значения по умолчанию в `compose.yaml` предназначены только для локальной проверки.

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H 'X-API-Key: YOUR_API_KEY' \
  -H 'Idempotency-Key: order-1001' \
  -H 'Content-Type: application/json' \
  -d '{"amount":"125.50","currency":"RUB","description":"Заказ 1001","metadata":{"order_id":1001},"webhook_url":"https://webhook.site/YOUR_UNIQUE_TOKEN"}'

curl -H 'X-API-Key: YOUR_API_KEY' http://localhost:8000/api/v1/payments/PAYMENT_ID
```

Создание возвращает HTTP 202 с `payment_id`, `status=pending`, `created_at`. Повтор с тем же `Idempotency-Key` и тем же телом возвращает существующий платёж; с другим телом — HTTP 409. GET возвращает все поля платежа, включая время обработки.

Для проверки webhook откройте `https://webhook.site`, скопируйте **Your unique URL** и подставьте его вместо `https://webhook.site/YOUR_UNIQUE_TOKEN`. После обработки запрос появится на этой странице, а `webhook_sent_at` перестанет быть `null`. Адрес `https://example.com/` из Swagger — лишь образец и не принимает уведомления. Для каждого нового платежа используйте новый `Idempotency-Key`; для повторной отправки того же запроса сохраняйте старый ключ.

## Доставка и обработка

API атомарно сохраняет `payments` и `outbox` в одной транзакции. Фоновый publisher внутри процесса consumer берёт неопубликованные записи с `FOR UPDATE SKIP LOCKED`, подтверждённо публикует persistent сообщение в `payments.new`, затем ставит `published_at`. Сбой до подтверждения не помечает запись опубликованной. Сбой после публикации до коммита может дать дубль; consumer повторно не обрабатывает уже завершённый платёж.

Единственный обработчик consumer эмулирует шлюз 2–5 секунд: 90% `succeeded`, 10% `failed`. После записи терминального статуса он отправляет JSON webhook методом POST. Сетевые/внутренние ошибки повторяются до трёх попыток с задержками 1 и 2 секунды. После третьей ошибки сообщение отклоняется и RabbitMQ направляет его в `payments.dead` через `payments.dlx`. Невыполненные webhook можно изучить и повторно опубликовать из DLQ. Сам факт 10% неуспешных платежей является штатным результатом, поэтому webhook отправляется и для них.

Webhook содержит `event_id` (стабильный идентификатор платежа), `payment_id`, `status`, `amount`, `currency`, `processed_at`. Заголовок `Idempotency-Key` равен `event_id`. Доставка webhook имеет семантику at least once: при сбое после приёма webhook, но до фиксации `webhook_sent_at`, клиент может получить его повторно. Получатель должен дедуплицировать по `event_id`.

## Проверки

```bash
docker compose ps
docker compose logs -f api consumer
docker compose exec api python -m pytest -q
docker compose exec -e RUN_DB_INTEGRATION=1 api python -m pytest -q
```

Для остановки: `docker compose down`. Для удаления локальных данных дополнительно укажите `-v`.

