FROM python:3.11-slim

ARG VERSION=1.0.0
ARG BUILD_DATE

LABEL maintainer="sports-platform"
LABEL version="${VERSION}"
LABEL description="Kafka to Ignite consumer for NBA data pipeline"
LABEL org.opencontainers.image.source="https://github.com/sports-platform/sports-platform"

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PYTHONPATH=/app

WORKDIR /app

RUN groupadd --gid 1000 appgroup \
  && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
  && rm -rf /var/lib/apt/lists/*

COPY --chown=appuser:appgroup pyproject.toml .
COPY --chown=appuser:appgroup src/ src/

RUN pip install --no-cache-dir -e /app

USER appuser

CMD ["python", "-m", "src.data_pipeline.kafka_ignite_consumer"]
