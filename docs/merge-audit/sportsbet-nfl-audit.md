# Sports-Bet Merge Audit: NFL & Cross-Project Analysis

**Document Version**: 1.0  
**Date**: June 16, 2026  
**Auditor**: Boomerang Architect  
**Scope**: Sports-Bet → Quant-Sports architectural validation (NO code merges)  
**Status**: Complete

---

## 1. Executive Summary

### What Sports-Bet Is

Sports-Bet is a **production-ready, enterprise-grade NBA betting analytics platform**. It is a self-contained application with its own infrastructure stack (Prefect, TimescaleDB, Redis, MLFlow, Grafana), 508 passing tests, 18+ bookmaker integrations, and a complete betting intelligence system (Kelly, EV, Arbitrage, CLV, Settlement). It lives at `/home/jcharles/Projects/python/Sports-Bet/`.

### What Quant-Sports Is

Quant-Sports is a **multi-sport quantitative analysis toolkit** — a "QuantLib for sports betting." It is designed as a library/framework with a CLI, API server, Kafka/Spark data pipeline, Kubernetes deployment manifests, and per-sport evaluator modules. It already has NFL, MLB, NHL, and PGA evaluators. It lives at `/home/jcharles/Projects/Infrastructure/quantitative_sports/`.

### Relationship

| Aspect | Sports-Bet | Quant-Sports |
|--------|-----------|-------------|
| **Role** | Production application | Toolkit/library |
| **Sports** | NBA (NFL/MLB/NHL planned) | NBA, NFL, MLB, NHL, PGA |
| **Orchestration** | Prefect | Kafka + Spark |
| **Deployment** | Docker Compose | Kubernetes |
| **NFL code** | None (planned only) | 1,128 lines (evaluator + rules) |
| **Betting engine** | Production-grade (settlement, CLV) | Canonical (engine, backtest, risk) |
| **Tests** | 508 (NBA-specific) | Multi-module test suite |

### Bottom Line

**Zero code merges recommended.** Sports-Bet and Quant-Sports serve fundamentally different purposes — one is a production application, the other is a toolkit. Quant-Sports's NFL code is already more complete than anything Sports-Bet has planned. The value is in **architectural validation**: Sports-Bet's ADR 005 (modular sport architecture) confirms Quant-Sports's per-sport evaluator approach. Sports-Bet's production patterns (Prefect flows, TimescaleDB hypertables, XGBoost training pipeline) are reference material for future Quant-Sports productionization.

---

## 2. Sports-Bet Architecture Overview

### Directory Structure

```
Sports-Bet/
├── NBA/                    # Active NBA module (42 entries)
│   ├── src/nba/            # Source: analytics, api, betting, db, flows, scrapers, training, utils
│   ├── tests/              # 508 tests (all passing)
│   ├── models/             # XGBoost models (6 files)
│   ├── docker/             # Analytics + Training containers
│   └── docs/               # NBA-specific documentation (12+ files)
├── infra/docker/           # Shared infrastructure (8 services)
├── scripts/                # Data loading utilities (15 files)
├── reports/                # Analysis reports (11 files)
├── tools/                  # Dev utilities (4 files)
├── docs/                   # Master documentation (30+ files)
│   └── adr/                # 7 Architecture Decision Records
├── old-nba/                # Legacy code (reference only)
└── Test_Suite/             # Faker JS mock generators
```

### Key Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | Prefect 3.x (port 4200) | 15+ flows: odds, predictions, training, backup, Discord |
| **Database** | TimescaleDB (9.49 GB, 32 hypertables) | Time-series odds, predictions, betting results |
| **Cache** | Redis 7.x (port 6379) | Prediction caching (58s TTL), bankroll state, arbitrage |
| **ML Models** | XGBoost v2 (70.6% accuracy) | Player props + team game predictions (39 features) |
| **Experiment Tracking** | MLFlow (port 5001) | File-based tracking, weekly training snapshots |
| **Observability** | Grafana + Loki + Tempo | Dashboards, log aggregation, distributed tracing |
| **Alerts** | Discord webhook (480 lines) | Rich embeds, file attachments, arbitrage alerts |
| **Betting Intelligence** | Kelly, EV, Arbitrage, CLV, Settlement | Complete institutional-grade system |

### ADR 005: Modular Sport Architecture

ADR 005 (Accepted, 2024-02) defines the planned multi-sport structure:

```
Sports-Bet/
├── infra/          # Shared infrastructure
├── NBA/            # NBA-specific module (IMPLEMENTED)
├── NFL/            # NFL module (PLANNED — not started)
├── NHL/            # NHL module (PLANNED — not started)
└── MLB/            # MLB module (PLANNED — not started)
```

**Key finding**: The NFL/ directory does not exist. No NFL code has been written. The multi-sport expansion is explicitly deferred in SYSTEM_OVERVIEW.md with trigger condition: "NBA CLV beat rate >55% for 3+ months."

### Technology Stack

| Layer | Sports-Bet Choices |
|-------|-------------------|
| Language | Python 3.11+ (NBA), Python 3.13+ (root) |
| Package manager | uv |
| Orchestration | Prefect |
| Database | TimescaleDB (PostgreSQL extension) |
| Cache | Redis |
| ML | XGBoost, scikit-learn, Optuna |
| API | FastAPI + Uvicorn |
| Observability | OpenTelemetry, structlog, Grafana/Loki/Tempo |
| Containerization | Docker Compose |
| Linting | Ruff (line length 150) |

---

## 3. Module-by-Module Analysis

### Decision Matrix

| Module | Decision | Rationale |
|--------|----------|-----------|
| **Betting calculation docs** (`NBA/docs/BETTING_CALCULATIONS.md`, 1,247 lines) | **Reference only** | Quant-Sports's `core/betting/engine.py` and `core/betting/kelly.py` are the canonical implementations. Formulas are mathematically identical. Sports-Bet's doc is a well-written reference but adds no new math. |
| **ADR 005 (modular architecture)** | **Validate** | Confirms Quant-Sports's per-sport evaluator approach (`models/analysis/evaluators/{nfl,mlb,nhl,pga}_eval.py`). Both projects independently arrived at the same architectural pattern. |
| **ADR 001–004, 006–007** | **Reference** | Prefect, TimescaleDB, XGBoost, Redis, MLFlow, weekly snapshots — all are Sports-Bet infrastructure decisions. Quant-Sports uses Kafka/Spark instead of Prefect, but shares TimescaleDB and XGBoost. |
| **Prefect flows** (15+ files) | **Keep (reference)** | Quant-Sports uses Kafka + Spark for data pipelines. Prefect patterns are valuable reference if Quant-Sports ever needs a lighter-weight orchestration layer for scheduled tasks. |
| **TimescaleDB schema** (`NBA/src/nba/db/schema.sql`, 259 lines) | **Keep (reference)** | Well-designed hypertable patterns (team_odds, player_props partitioned by time). Quant-Sports has its own schemas in `docs/schema-*.sql` but could learn from Sports-Bet's betting-specific hypertable design (rolling_performance, bankroll_history, bet_results, arbitrage_opportunities). |
| **XGBoost trainer** (`NBA/src/nba/training/trainer.py`, 895 lines) | **Keep (reference)** | Production-grade training pipeline with MLFlow integration, chronological split, GPU acceleration, and statistical validation. Pattern reference for Quant-Sports's NFL prediction model. |
| **XGBoost predictor** (`NBA/src/nba/analytics/predictor.py`) | **Keep (reference)** | Model loading, feature engineering, and prediction generation. Pattern for NFL model serving. |
| **Backtesting engine** (`NBA/src/nba/training/backtest.py`, 1,218 lines) | **DISCARD** | Quant-Sports's `core/backtest/engine.py` (403 lines) is the canonical implementation with walk-forward validation, regime-aware analysis, and sensitivity testing. Sports-Bet's backtest is NBA-specific and less sophisticated. |
| **Discord alerts** (`NBA/src/nba/api/discord_webhook.py`, 480 lines) | **Keep (reference)** | Quant-Sports has its own notification module (`notifications/` — 13 files including hero_card.py, discord.py, webhook.py). Sports-Bet's webhook has retry logic and rate-limit handling worth referencing. |
| **NBA scrapers** (5 files) | **Keep** | NBA-specific data sources (The Odds API, NBA.com stats). Not applicable to NFL. |
| **NBA models** (6 XGBoost files) | **Keep** | NBA-specific trained models. Not transferable to NFL. |
| **508 tests** (61 test files) | **Keep** | NBA-specific test suite. Test patterns (pytest markers, coverage config) are reference-quality. |
| **Betting strategy modules** (kelly.py, ev.py, arbitrage.py, clv.py, settlement.py, allocation.py, bankroll.py) | **Reference only** | Quant-Sports has canonical implementations in `core/betting/` and `core/risk/`. Sports-Bet's versions are production-hardened with Redis persistence and Prefect integration — valuable reference for production patterns. |
| **Infrastructure** (`infra/docker/docker-compose.yml`, 382 lines) | **Keep (reference)** | Docker Compose for local dev. Quant-Sports uses Kubernetes for production. Sports-Bet's compose file is a clean reference for local development environments. |
| **old-nba/** | **DISCARD** | Legacy code, explicitly marked "DO NOT MODIFY." No value for merge. |

### Summary

| Category | Count | Decision |
|----------|-------|----------|
| **Keep in Sports-Bet** | 8 modules | NBA-specific code, models, scrapers, tests |
| **Reference only** | 6 modules | Docs, ADRs, betting formulas, flows, schema, trainer |
| **Discard (canonical exists)** | 2 modules | Backtesting engine, old-nba |
| **Validate architecture** | 1 module | ADR 005 confirms Quant-Sports approach |

---

## 4. What Quant-Sports Already Has That Sports-Bet Doesn't

### NFL Evaluator (`nfl_eval.py` — 847 lines)

Located at `src/quantitative_sports/models/analysis/evaluators/nfl_eval.py`. A complete NFL prediction evaluator. Sports-Bet has zero NFL code — the NFL/ directory does not exist.

### NFL Rules Engine (`rules/nfl.py` — 281 lines)

Located at `src/quantitative_sports/models/analysis/rules/nfl.py`. Sport-specific rules for NFL betting evaluation. Combined with the evaluator: **1,128 lines of production NFL code**.

### Multi-Sport Evaluator Architecture

Quant-Sports already has per-sport evaluators matching the pattern Sports-Bet's ADR 005 planned:

| Sport | Evaluator | Rules Engine |
|-------|-----------|--------------|
| **NFL** | `nfl_eval.py` (847 lines) | `rules/nfl.py` (281 lines) |
| **MLB** | `mlb_eval.py` | `rules/mlb.py` |
| **NHL** | `nhl_eval.py` | `rules/nhl.py` |
| **PGA** | `pga_eval.py` | `rules/pga.py` |
| **NBA** | (via DraftKings/FanDuel/PrizePicks/Underdog evaluators) | (via fanduel/underdog rules) |

### Multi-Sport Notebook Structure

```
notebooks/
├── basketball/    # 03_backtesting.ipynb, 04_ratings_comparison.ipynb
├── football/      # (directory exists, notebooks planned)
└── common/        # Shared utilities
```

### CLI with 14+ Commands

`src/quantitative_sports/cli/main.py` (1,163 lines, 31 function definitions) provides a comprehensive CLI wrapping the betting engine, risk management, backtesting, and ratings modules. Entry points: `quantitative_sports`, `quantitative_sports-nba`, `quant-sports-poller`, `quantitative_sports-api`.

### Canonical Betting Engine

`src/quantitative_sports/core/betting/engine.py` (214 lines) — the reference implementation of EV calculation, Kelly criterion, and over/under decision logic. Clean, well-tested, mathematically rigorous.

### Canonical Backtesting Engine

`src/quantitative_sports/core/backtest/engine.py` (403 lines) — walk-forward validation, regime-aware analysis, sensitivity testing. More sophisticated than Sports-Bet's NBA-specific backtest.

### Risk Management Module

`src/quantitative_sports/core/risk/` — portfolio optimization (`portfolio.py`) and market impact modeling (`market_impact.py`). Sports-Bet has bankroll management but no portfolio-level risk tools.

### Notification System with Hero Cards

`src/quantitative_sports/notifications/` (13 files) — includes `hero_card.py` (273 lines) for generating PNG matchup cards with team logos, plus Discord webhook, formatter, builder, and queue modules. More sophisticated than Sports-Bet's single `discord_webhook.py`.

### Kubernetes Deployment

`k8s/` directory with full Kubernetes manifests. Sports-Bet uses Docker Compose only.

### Kafka/Spark Data Pipeline

`src/quantitative_sports/data/` and `src/quantitative_sports/infra/` — Kafka consumers, Spark producers, dual-write synchronization, Ignite cache. Sports-Bet uses Prefect for orchestration.

---

## 5. What Sports-Bet Has That Quant-Sports Could Learn From

### Prefect Orchestration Patterns

Sports-Bet's 15+ Prefect flows demonstrate clean orchestration patterns:
- **Pipeline composition**: `nba_pipeline_flow.py` chains Odds → Predictions → Discord as sub-flows
- **Deployment scripts**: `serve_*.py` files for serving individual flows
- **Observability integration**: Every flow instrumented with OpenTelemetry tracing
- **Retry and error handling**: Built-in Prefect retry logic with exponential backoff

**Value for Quant-Sports**: If Quant-Sports ever needs scheduled task orchestration (daily model retraining, weekly backups), Prefect is lighter-weight than Kafka/Spark for cron-style workflows.

### TimescaleDB Hypertable Design

Sports-Bet's `schema.sql` (259 lines) demonstrates production hypertable patterns:
- **Betting-specific hypertables**: `rolling_performance`, `bankroll_history`, `bet_results`, `arbitrage_opportunities`
- **Composite primary keys**: `(time, event_id, bookmaker, market_type)` for upsert-friendly design
- **JSONB fallback**: `raw_data JSONB` column for flexible schema evolution
- **Compression policies**: Enabled on older chunks

**Value for Quant-Sports**: Quant-Sports has its own schemas (`docs/schema-*.sql`) but could adopt Sports-Bet's betting-specific hypertable patterns for production deployment.

### XGBoost Training Pipeline

Sports-Bet's `trainer.py` (895 lines) is a production-hardened training pipeline:
- **Chronological split**: 85/15 train/validation (prevents look-ahead bias)
- **MLFlow integration**: Automatic experiment tracking, artifact logging
- **Statistical validation**: `ModelValidator` with calibration tests
- **GPU acceleration**: CUDA-enabled training
- **Weekly snapshots**: `data_versioning.py` for reproducible training

**Value for Quant-Sports**: Direct pattern reference when building the NFL prediction model. Quant-Sports already has XGBoost in dependencies.

### Discord Hero Card Notification Format

Sports-Bet's `discord_webhook.py` (480 lines) demonstrates:
- **Retry logic**: Exponential backoff with rate-limit handling (429 responses)
- **Rich embeds**: Color-coded messages with field formatting
- **File attachments**: Excel/CSV/JSON with SHA256 checksums
- **Multi-file uploads**: Batch attachment support

**Value for Quant-Sports**: Quant-Sports's `notifications/` module is more architecturally sophisticated (hero cards, queue, builder pattern) but Sports-Bet's webhook has battle-tested retry logic worth referencing.

### 508-Test Discipline

Sports-Bet's test suite demonstrates:
- **Pytest markers**: `integration`, `benchmark`, `slow` for test categorization
- **Coverage configuration**: Branch coverage with precision reporting
- **Comprehensive betting tests**: 225 tests across Kelly, EV, Arbitrage, CLV, Settlement
- **Integration tests**: 140 tests for multi-bookmaker, line history, schedule, settlement

**Value for Quant-Sports**: Test organization patterns, marker conventions, and coverage configuration.

---

## 6. Recommendations

### 1. Do NOT Merge Code

**Rationale**: Quant-Sports's NFL code (`nfl_eval.py` 847 lines + `rules/nfl.py` 281 lines) is already more complete than anything Sports-Bet has. Sports-Bet has zero NFL code — the NFL/ directory doesn't exist. Merging would mean porting Quant-Sports's NFL code into Sports-Bet, which is backwards. Quant-Sports is the toolkit; Sports-Bet is the application.

### 2. Reference Sports-Bet Patterns for Future Features

| Quant-Sports Future Need | Sports-Bet Reference |
|------------------------|---------------------|
| Production orchestration for scheduled tasks | Prefect flow patterns (`NBA/src/nba/flows/`) |
| Time-series storage for betting results | TimescaleDB hypertable design (`NBA/src/nba/db/schema.sql`) |
| NFL prediction model training | XGBoost trainer pipeline (`NBA/src/nba/training/trainer.py`) |
| Discord alert retry logic | Webhook client (`NBA/src/nba/api/discord_webhook.py`) |
| Test organization at scale | Pytest markers + coverage config (`NBA/pyproject.toml`) |

### 3. Keep Sports-Bet as NBA Production Platform

Sports-Bet is a production application with live infrastructure, 508 tests, and 18+ bookmaker integrations. It serves a different purpose than Quant-Sports (toolkit/library). Do not dilute either project by forcing a merge.

### 4. Bridge via Shared Data Formats

If both projects standardize on the same CSV/Parquet schemas for:
- **NFL lines**: `event_id, bookmaker, market_type, home_odds, away_odds, spread, total, timestamp`
- **Player stats**: `player_id, game_id, stat_type, value, timestamp`
- **Prediction output**: `event_id, market_type, predicted_prob, model_version, timestamp`

Then data can flow between them: Quant-Sports generates predictions, Sports-Bet consumes them for production betting.

### 5. Architectural Validation Complete

ADR 005 (modular sport architecture) independently confirms Quant-Sports's per-sport evaluator design. Both projects arrived at the same pattern: sport-specific modules with shared infrastructure. This is a strong architectural signal — the pattern is correct.

---

## 7. Future Integration Possibilities

### Shared Data Schemas

Define a common NFL data contract:

```text
nfl_lines.csv:
  event_id, week, season, home_team, away_team, commence_time,
  bookmaker, market_type (h2h/spreads/totals),
  home_odds, away_odds, home_spread, away_spread,
  over_under, over_odds, under_odds, timestamp

nfl_player_props.csv:
  event_id, player_id, player_name, stat_type (pass_yds/rush_yds/rec_yds/tds),
  line, over_odds, under_odds, bookmaker, timestamp
```

### Quant-Sports as Analytics Library

Sports-Bet could import Quant-Sports as a dependency:

```python
# Hypothetical future integration
from quantitative_sports.models.analysis.evaluators.nfl_eval import NFLEvaluator
from quantitative_sports.core.betting.engine import decide_over_under

evaluator = NFLEvaluator()
decision = decide_over_under(probability=0.58, odds=Odds(american=-110))
```

This would give Sports-Bet access to Quant-Sports's NFL evaluator, betting engine, and risk management without code duplication.

### MCP Server Bridging

If Quant-Sports exposes its betting engine and evaluators via an MCP server, Sports-Bet could consume them as tools:

```text
Quant-Sports MCP Server:
  - evaluate_nfl_game(event_id, model_version) → prediction
  - calculate_kelly(probability, odds, bankroll) → fraction
  - detect_arbitrage(odds_from_multiple_books) → opportunities
  - backtest_strategy(config) → performance_report

Sports-Bet consumes via MCP client → feeds into Prefect flows
```

### Unified Prediction Output Contract

```json
{
  "event_id": "nfl-2026-week1-kc-vs-bal",
  "sport": "nfl",
  "model_version": "xgboost-nfl-v1",
  "generated_at": "2026-09-07T12:00:00Z",
  "predictions": [
    {
      "market_type": "spreads",
      "predicted_spread": -3.2,
      "confidence": 0.72,
      "edge_vs_pinnacle": 0.04
    }
  ]
}
```

---

## Appendix A: File Counts

| Project | Source Files | Test Files | Documentation | Lines of NFL Code |
|---------|-------------|------------|---------------|-------------------|
| **Sports-Bet** | ~50 (NBA/src/nba/) | 61 (NBA/tests/) | 30+ docs | **0** (NFL/ dir does not exist) |
| **Quant-Sports** | 159 (src/quantitative_sports/) | Multi-module | 10+ docs | **1,128** (nfl_eval.py + rules/nfl.py) |

## Appendix B: Key Files Referenced

| File | Lines | Purpose |
|------|-------|---------|
| `Sports-Bet/docs/adr/005-modular-sport-architecture.md` | 60 | Modular sport architecture decision |
| `Sports-Bet/docs/SYSTEM_OVERVIEW.md` | 1,346 | Complete system state |
| `Sports-Bet/docs/AGENTS.md` | 654 | Master navigation document |
| `Sports-Bet/NBA/src/nba/db/schema.sql` | 259 | TimescaleDB hypertable design |
| `Sports-Bet/NBA/src/nba/training/trainer.py` | 895 | XGBoost training pipeline |
| `Sports-Bet/NBA/src/nba/training/backtest.py` | 1,218 | NBA backtesting engine |
| `Sports-Bet/NBA/src/nba/api/discord_webhook.py` | 480 | Discord webhook client |
| `Sports-Bet/NBA/src/nba/flows/nba_pipeline_flow.py` | 295 | Prefect pipeline orchestration |
| `Sports-Bet/infra/docker/docker-compose.yml` | 382 | Infrastructure services |
| `Quant-Sports/src/quantitative_sports/models/analysis/evaluators/nfl_eval.py` | 847 | NFL prediction evaluator |
| `Quant-Sports/src/quantitative_sports/models/analysis/rules/nfl.py` | 281 | NFL betting rules engine |
| `Quant-Sports/src/quantitative_sports/core/betting/engine.py` | 214 | Canonical betting engine |
| `Quant-Sports/src/quantitative_sports/core/backtest/engine.py` | 403 | Canonical backtesting engine |
| `Quant-Sports/src/quantitative_sports/cli/main.py` | 1,163 | CLI with 14+ commands |
| `Quant-Sports/src/quantitative_sports/notifications/hero_card.py` | 273 | Discord hero card generator |

---

*Audit conducted by Boomerang Architect. No code was modified. All findings based on read-only analysis of both repositories.*
