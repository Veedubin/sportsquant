# SportsQuant — Quantitative Sports Betting Toolkit

**Mathematical toolkit for sports betting. Bring your own data.**

![v0.2.0](https://img.shields.io/badge/version-v0.2.0-blue)
![Tests](https://img.shields.io/badge/tests-775_passing-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

SportsQuant is a professional-grade quantitative analysis toolkit designed for analysts, not tipsters. Think of it as "QuantLib for sports betting"—it provides the rigorous mathematical infrastructure needed to translate raw odds and statistics into actionable, risk-adjusted betting signals.

## Quick Start

```bash
# 1. Install the desktop package
uv add sportsquant[notebook]

# 2. Start the storage layer
cd ~/Projects/Infrastructure/sportsquant
make docker-up

# 3. Open a notebook
uv run jupyter lab labs/01_getting_started.ipynb
```

## Architecture

SportsQuant v0.2.0 is decoupled into three primary layers to ensure scalability and separation of concerns:

```text
+-----------------------+       +-------------------------------------------+
|    Desktop Package    |       |              Docker Compose Stack         |
| (CLI, Library, Labs)   |       | (timescaledb + poller + web dashboard)    |
+-----------+-----------+       +-------------------+-----------------------+
            |                                       |
            |         Data Flow                    |
            |  [ Poller ] ----> [ TimescaleDB ] <---+
            |       |                |
            +-------+----------------+
                    |
                    v
            [ Notebooks / CLI / Web UI ]
```

- **Desktop Package**: The core Python library providing the math, models, and CLI.
- **Infrastructure Stack**: 
    - `timescaledb`: High-performance time-series storage (PG 18 + TimescaleDB 2.28).
    - `sportsquant/poller`: Background container for data collection (Odds API, ESPN).
    - `sportsquant/web`: Operations dashboard for health monitoring and metrics.
- **Data Flow**: The poller fetches live data $\rightarrow$ writes to TimescaleDB $\rightarrow$ consumed by the web dashboard and your analytical notebooks.

## Features

### 🧮 Betting Mathematics
- **Expected Value (EV)**: Precise calculation including implied probability and vig removal.
- **Kelly Criterion**: Full and fractional Kelly sizing for optimal bankroll growth.
- **Middling Detection**: Automatic identification of multi-book spread/total middles.

### 📈 Predictive Modeling
- **NFL Game Prediction**: XGBoost ensemble for win probability, spreads, and totals.
- **Ratings Systems**: Implementation of Elo, Massey, PageRank, and Glicko systems.
- **Custom Strategies**: Extensible registry to define, backtest, and deploy your own logic.

### ⚙️ Infrastructure & Ops
- **Backtesting Engine**: Professional walk-forward validation and parallel execution.
- **Live Data**: Integrated polling for Odds API and ESPN injury reports.
- **Web Ops Dashboard**: Monitor poller health, run history, log tailing, and system metrics.

## Package Layout

```
sportsquant/
├── core/           # Betting math (EV, Kelly, middling, metrics)
├── models/         # XGBoost, ratings, predictive models
├── backtest/       # Backtest engine
├── data/           # Data sources (Odds API, ESPN, nflverse)
├── infra/
│   ├── db/         # TimescaleDB connection, schema, queries, writers
│   └── poller/     # Background data fetcher
├── web/            # FastAPI ops dashboard
└── cli/            # Click commands

labs/               # 10 comprehensive Jupyter walkthroughs
docker/
├── Dockerfile.poller
├── Dockerfile.web
└── init-db.sql     # TimescaleDB schema
docker-compose.yml  # timescaledb + poller + web
```

## Running

### Installation
```bash
uv add sportsquant[notebook]
```

### Usage
```bash
# Run a CLI command
sportsquant nfl predict-game

# Start the docker stack (DB, Poller, Web)
make docker-up

# Run tests
make test
```

## Configuration

```bash
cp .env.example .env
# Edit .env with your Odds API key
# Then: make docker-up
```

## Disclaimer

*SportsQuant is a mathematical toolkit provided for analytical purposes only. It does not provide betting advice or guaranteed returns. You are solely responsible for compliance with your local laws and regulations regarding sports wagering.*
