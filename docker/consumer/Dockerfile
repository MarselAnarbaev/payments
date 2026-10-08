FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Consumer и publisher работают от непривилегированного пользователя.
RUN useradd --create-home appuser && chown -R appuser:appuser /srv
USER appuser
CMD ["faststream", "run", "app.consumer.main:app"]
