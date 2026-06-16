# syntax=docker.io/docker/dockerfile:1.4
# ============================================================================
# Sports Platform - Unified Multi-Stage Dockerfile
# ============================================================================
# Build with: docker build -t sports-platform/poller:latest .
# ============================================================================

# ----------------------------------------------------------------------------
# STAGE 1: Base - Common dependencies for all services
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Common system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  ntpsec-ntpdate \
  gcc \
  && rm -rf /var/lib/apt/lists/*

# Common Python deps
RUN pip install --no-cache-dir \
  kafka-python==2.0.2 \
  pandas \
  httpx \
  numpy \
  requests==2.31.0 \
  prometheus-client==0.19.0 > =2.0.0 > =0.27.0 > =1.24.0

WORKDIR /app

# ----------------------------------------------------------------------------
# STAGE 2: Poller - Kafka, database, cache clients
# ----------------------------------------------------------------------------
FROM base AS poller-stage

RUN pip install --no-cache-dir \
  confluent-kafka==2.3.0 \
  pyignite==0.3.2 \
  psycopg2-binary==2.9.9 \
  aiohttp==3.9.1 \
  nba_api==1.8.0 \
  playwright>=1.57.0 \
  click>=8.0.0 \
  structlog>=23.0.0 \
  rich>=13.0.0 \
  pyyaml>=6.0

# Create poller user
RUN useradd --create-home --shell /bin/bash poller \
  && chown -R poller:poller /home/poller

# Set working directory to poller home
WORKDIR /home/poller

# Copy source and switch user
COPY --chown=poller:poller src/ /home/poller/src/
COPY --chown=poller:poller scripts/ntp-sync.sh /usr/local/bin/ntp-sync
COPY --chown=poller:poller scripts/unified-poller-entrypoint.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/ntp-sync /usr/local/bin/unified-poller-entrypoint.sh

USER poller

# Run entrypoint directly (no NTP sync - use host time)
CMD ["/usr/local/bin/unified-poller-entrypoint.sh"]

# ----------------------------------------------------------------------------
# STAGE 3: Config Server - FastAPI + scheduling
# ----------------------------------------------------------------------------
FROM base AS config-server-stage

RUN pip install --no-cache-dir \
  fastapi==0.109.0 \
  uvicorn[standard]==0.27.0 \
  pydantic==2.5.3 \
  opentelemetry-api==1.21.0 \
  opentelemetry-sdk==1.21.0 \
  opentelemetry-instrumentation-fastapi==0.42b0 \
  python-json-logger==2.0.7 \
  rich==13.7.0

# Copy full src directory for all dependencies
COPY --chown=appuser:appgroup src/ /app/src/

EXPOSE 8081

CMD ["uvicorn", "src.scheduler_config_api.main:app", "--host", "0.0.0.0", "--port", "8081"]

# ----------------------------------------------------------------------------
# STAGE 4: OpenTelemetry - Full instrumentation
# ----------------------------------------------------------------------------
FROM poller-stage AS otel-stage

ARG OTEL_VERSION=1.21.0
ARG OTEL_INSTRUMENTATION_VERSION=0.42b0

RUN pip install --no-cache-dir \
  opentelemetry-api==${OTEL_VERSION} \
  opentelemetry-sdk==${OTEL_VERSION} \
  opentelemetry-exporter-otlp==${OTEL_VERSION} \
  opentelemetry-exporter-otlp-proto-grpc==${OTEL_VERSION} \
  opentelemetry-instrumentation==${OTEL_INSTRUMENTATION_VERSION} \
  opentelemetry-instrumentation-kafka-python==${OTEL_INSTRUMENTATION_VERSION} \
  opentelemetry-instrumentation-fastapi==${OTEL_INSTRUMENTATION_VERSION}

ENV OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317" \
  OTEL_SERVICE_NAME="sports-platform"

# ----------------------------------------------------------------------------
# STAGE 5: Final - The unified poller image (default target)
# ----------------------------------------------------------------------------
FROM poller-stage AS final

# Copy OTEL instrumentation from otel stage
COPY --from=otel-stage /usr/local/lib/python3.11/site-packages/opentelemetry* /usr/local/lib/python3.11/site-packages/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1
