# SportsQuant Tutorial Notebooks

Per-sport Jupyter notebooks demonstrating SportsQuant's quantitative betting toolkit.

## Structure

| Directory | Sport | Notebooks |
|-----------|-------|-----------|
| common/ | Sport-Agnostic | EV Calculation, Kelly Optimization, Parlay Optimization |
| basketball/ | NBA | Backtesting, Ratings Comparison |
| football/ | NFL | Player Props, Backtesting, Power Ratings |

## Quick Start

```bash
cd notebooks/
jupyter lab
```

## Notebook Index

### Common (Sport-Agnostic)
- **01_ev_calculation.ipynb** — Expected value math for any sport
- **02_kelly_optimization.ipynb** — Kelly criterion bet sizing
- **05_parlay_optimization.ipynb** — Parlay/correlated bet optimization

### Basketball (NBA)
- **03_backtesting.ipynb** — Backtest NBA betting strategies
- **04_ratings_comparison.ipynb** — Compare RAPTOR, Massey, PageRank ratings

### Football (NFL)
- **01_nfl_player_props.ipynb** — Evaluate NFL player props with nflfastR data
- **02_nfl_backtest.ipynb** — Backtest NFL betting strategies
- **03_nfl_ratings.ipynb** — NFL team power ratings (Massey, PageRank)