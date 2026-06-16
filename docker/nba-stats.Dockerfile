# syntax=docker/dockerfile:1
ARG BASE_IMAGE=python:3.11-slim

FROM ${BASE_IMAGE} as builder

ARG PYTHON_VERSION=3.11

RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
  kafka-python==2.0.2 \
  pandas \
  httpx \
  numpy \
  playwright==1.52.0 \
  pyyaml > =2.0.0 > =0.27.0 > =1.24.0 > =6.0

RUN playwright install chromium

FROM ${BASE_IMAGE}

RUN apt-get update && apt-get install -y --no-install-recommends \
  libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
  libcairo2 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

WORKDIR /app

COPY src/datasource/ /app/src/datasource/

ENV PYTHONPATH=/app

CMD ["python", "-m", "src.datasource.nba_stats.client"]
