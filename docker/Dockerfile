FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright pip install --no-cache-dir playwright==1.57.0 \
    && PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright playwright install --with-deps chromium \
    && PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright playwright install chromium-headless-shell \
    && cp -r /tmp/playwright /app/playwright

COPY pyproject.toml .
COPY nba_stats_package/ ./nba_stats_package/
COPY src/ ./src/

RUN pip install --no-cache-dir psycopg2-binary .

CMD ["python", "-m", "src.unified_poller"]
