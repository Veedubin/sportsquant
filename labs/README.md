# SportsQuant Labs

Ten comprehensive Jupyter notebook walkthroughs that teach you the entire sportsquant system end-to-end.

## Catalog

| # | Lab | Description | Time |
|---|-----|-------------|------|
| 01 | [Getting Started](01_getting_started.ipynb) | Install, configure DB, first query, explore schema | 15 min |
| 02 | [Data Ingestion](02_data_ingestion.ipynb) | How the poller works, query raw data, hypertable internals | 30 min |
| 03 | [Single-Bet EV](03_single_bet_ev.ipynb) | From odds to Kelly-sized bet, implied prob, vig removal | 45 min |
| 04 | [Multi-Book Middling](04_multi_book_middling.ipynb) | Detect and size middles (spread and total) | 45 min |
| 05 | [Building a Backtest](05_building_backtest.ipynb) | Define a strategy, run on history, interpret metrics | 60 min |
| 06 | [NFL Game Prediction (XGBoost)](06_nfl_game_prediction.ipynb) | Train ensemble, predict games, interpret features | 60 min |
| 07 | [Ratings Systems](07_ratings_systems.ipynb) | Elo, Massey, PageRank, Glicko — when to use what | 45 min |
| 08 | [Live Workflow](08_live_workflow.ipynb) | End-to-end: poller → +EV → bet → CLV → result | 45 min |
| 09 | [Building a Custom Strategy](09_custom_strategy.ipynb) | Subclass BaseStrategy, register, backtest, deploy | 45 min |
| 10 | [Production Patterns](10_production_patterns.ipynb) | Scheduling, errors, data quality, alerting, monitoring | 60 min |

## Running the labs

```bash
uv add sportsquant[notebook]
uv run jupyter lab labs/
```

Each lab is self-contained and uses synthetic data fallbacks if the database is empty.

## Prerequisites
- Python 3.12+
- `uv` (recommended) or `pip`
- 4 GB RAM minimum
- For labs that fetch live data: Odds API key (https://the-odds-api.com)
