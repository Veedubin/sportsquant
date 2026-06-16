# SportsQuant

**QuantLib for sports betting**
A professional-grade quantitative analysis toolkit for building, backtesting, and deploying sports betting strategies.

![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Status: Stable](https://img.shields.io/badge/status-stable-brightgreen)

SportsQuant provides the rigorous mathematical infrastructure required for institutional-grade sports trading. It is designed as a "bring your own data" framework, offering the sophisticated analytical tools needed to translate raw odds and statistics into actionable, risk-adjusted betting signals.

## System Architecture

```text
[ Data Sources ]        [ Data Pipeline ]        [ Modeling Layer ]       [ Execution Layer ]
+---------------+       +----------------+      +------------------+     +------------------+
| Pinnacle API  | ---->  | Kafka Consumers | ---> | Prediction Models| --> | Betting Engine    |
| Odds API      |       | Dual-Write Sync |      | Bayesian Priors   |     | Kelly Optimization|
| NBA Stats     |       | TimescaleDB     |      | Rating Systems   |     | Risk Management   |
| ESPN Injuries |       | Ignite Cache    |      | EV Calculation   |     | Notification Bus |
+---------------+       +----------------+      +------------------+     +------------------+
                                                                                  |
                                                                                  v
                                                                         [ Trading Interface ]
                                                                         (CLI / Discord / API)
```

## Core Capabilities

### Betting Mathematics
Rigorous implementation of betting theory and probability:
- **Kelly Criterion**: Comprehensive support for Standard, Fractional, and Adaptive Kelly strategies to maximize long-term logarithmic growth.
- **Expected Value (EV)**: Precise calculation of edge based on implied probability vs. model-derived probability.
- **Arbitrage Detection**: Real-time identification of risk-free profit opportunities across multiple sportsbooks.

### Portfolio Optimization
Institutional risk management tools to protect capital and optimize returns:
- **Position Sizing**: Dynamic sizing based on confidence intervals and bankroll volatility.
- **Risk Limits**: Hard and soft constraints on total exposure, sport-specific limits, and correlation caps.
- **Market Impact**: Modeling of price slippage and market movement resulting from large bet placement.

### Backtesting Framework
Multi-generational backtesting engine for strategy validation:
- **Walk-Forward Validation**: Rigorous out-of-sample testing to prevent overfitting.
- **Regime-Aware Analysis**: Identification of performance shifts across different seasonal or market regimes.
- **Sensitivity Testing**: Stress-testing strategies against varying odds and win-rate fluctuations.

### Player Ratings & Bayesian Modeling
Advanced statistical modeling for athlete and team evaluation:
- **Rating Systems**: Implementation of RAPTOR (composite), Massey, and PageRank algorithms for hierarchical team and player ranking.
- **Bayesian Shrinkage**: Use of James-Stein estimators to handle small sample sizes and stabilize player priors.
- **Contextual Modeling**: Integration of matchup-specific variables and environmental factors into base ratings.

### Prediction Models
High-performance machine learning pipelines for game outcomes:
- **XGBoost PRA**: Specialized models for Points, Rebounds, and Assists forecasting.
- **Game-Level Modeling**: Probabilistic forecasting for Spreads, Totals, and Moneylines.
- **Simulation**: Monte Carlo engines for simulating thousands of game iterations to derive probability distributions.

### Infrastructure & Observability
Production-ready deployment stack:
- **Orchestration**: Full Kubernetes manifests for scalable deployment.
- **Data Stream**: Kafka-driven pipeline for low-latency data ingestion.
- **Storage**: TimescaleDB for high-performance time-series storage of historical odds.
- **Monitoring**: Grafana dashboards for tracking model performance and system health.

## Installation

SportsQuant utilizes `uv` for high-performance dependency management.

```bash
# Install uv if not already present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync
```

## Quick Start

The following example demonstrates calculating an optimal bet size using the Kelly Criterion.

```python
from sportsquant.core.betting import KellyCalculator, Odds

# Initialize the calculator
kelly = KellyCalculator()

# Define the market odds (American format: -110)
odds = Odds(american=-110)

# Calculate optimal bet fraction given a 5% edge and $1000 bankroll
# edge = (Model Probability * Decimal Odds) - 1
fraction = kelly.calculate(edge=0.05, odds=odds, bankroll=1000)

print(f"Optimal Kelly fraction: {fraction:.2%}")
```

## Package Structure

```text
sportsquant/
├── src/sportsquant/
│   ├── core/               # Mathematical engines (Betting, Risk, Backtesting)
│   ├── models/             # ML and Statistical models (Predictive, Ratings, Analysis)
│   ├── data/               # Ingestion and pipeline (Sources, Pipeline, Schemas)
│   ├── api/                # FastAPI infrastructure and authentication
│   ├── notifications/      # Alerting systems (Discord, Queue)
│   ├── infra/              # Scheduling and polling logic
│   ├── cli/                # Command line interfaces
│   └── util/               # Telemetry, logging, and system metrics
├── k8s/                    # Kubernetes orchestration manifests
├── docker/                 # Containerization definitions
├── docs/                   # Architecture decisions and runbooks
└── tests/                  # Comprehensive test suite
```

## Documentation

Detailed technical documentation, Architecture Decision Records (ADRs), and operational runbooks are available in the `/docs` directory.

## License

This project is licensed under the MIT License.
