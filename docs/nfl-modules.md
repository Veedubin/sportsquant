# NFL / Football Modules

This document covers the NFL-specific surface area added on top of the
generic betting engine. It mirrors the layout in `src/sportsquant/data/nfl.py`,
`src/sportsquant/models/predictive/nfl_game_model.py`, and the multi-book
odds parser.

## Data layer

### `NFLDataPipeline` (`src/sportsquant/data/nfl.py`)

The single canonical entry point for NFL data. Composes:

| Source | Purpose | Status |
|--------|---------|--------|
| `NFLfastRSource` | Player stats from `nflverse-data` GitHub releases | Cached to `cache/nfl/nflfastr_<season>.csv.gz` |
| `ESPNInjurySource` | NFL injury reports from ESPN public API | Live fetch via `ESPNInjuryScraper` |
| `PinnacleNFLOddsSource` | Sharp NFL odds from Pinnacle | Stub (requires Pinnacle partnership) |

Methods:

- `get_player_stats(player_name, stat_types, n_games=10)`
- `get_injury_report()`
- `get_odds(week=None)` — returns Pinnacle lines (stub)
- `get_all_data(week=None)` — combined fetch with `fetched_at` timestamp
- **`get_multi_book_odds(api_key)`** — fetches The Odds API across all books
- **`detect_middles(df)`** — wraps the middling detection strategy

### `parse_game_lines_to_raw(events)` (`src/sportsquant/data/sources/odds_api/game_lines.py`)

Flattens The Odds API event responses into a per-(game, bookmaker) DataFrame.
Handles three market types:

- **h2h** — moneyline (ml_home, ml_away)
- **spreads** — point spread (spread_home, prices)
- **totals** — over/under (total, prices)

Strict output schema:

```
event_id, commence_time, home_team, away_team,
source_id, observed_at, effective_at, available_at,
ml_home, ml_away,
spread_home, spread_home_price, spread_away_price,
total, total_over_price, total_under_price
```

Companion: `parse_outrights_to_futures(events, futures_market=...)` handles
championship / division winner markets.

## Modeling layer

### `NFLGamePredictor` (`src/sportsquant/models/predictive/nfl_game_model.py`)

XGBoost ensemble with three sub-models:

| Model | Target | Use |
|-------|--------|-----|
| `classifier` (XGBClassifier) | home win (0/1) | `predict(...).home_win_prob` |
| `spread_model` (XGBRegressor) | home_score − away_score | `predict(...).proj_spread` |
| `total_model` (XGBRegressor) | home_score + away_score | `predict(...).proj_total` |

**14 features** (all in canonical `feature_columns()` order):

```
home_ppg_for, home_ppg_against, home_yards_per_play, home_turnover_rate,
home_qb_rating, away_ppg_for, away_ppg_against, away_yards_per_play,
away_turnover_rate, away_qb_rating, ppg_differential, defense_differential,
home_advantage, rest_advantage
```

**Training data**: replace `_generate_synthetic_dataset()` with a real
`nflfastR` play-by-play join (`(season, week, home_team, away_team)`)
plus `nflverse` schedules for target labels.

**Save/load**: `NFLGamePredictor.save(path)` writes `classifier.json`,
`spread.json`, `total.json`, `meta.json`. Use `NFLGamePredictor.load(path)`
in production scoring jobs.

### `NFLGameFeatures` (same module)

Dataclass that maps cleanly to the 14-feature schema. Build via:

```python
from sportsquant.models.predictive.nfl_game_model import build_features_from_pipeline

features = build_features_from_pipeline(
    pipeline, home_team="KC", away_team="BAL", season=2024, week=10,
)
```

`build_features_from_pipeline` reads nflfastR player stats and computes
team-level rolling aggregates. Returns zero-valued features when network/
cache is unavailable so downstream code never crashes.

## Strategy layer

### `middling.detect_middles` (`src/sportsquant/core/betting/strategies/middling.py`)

A "middle" exists when two books offer materially different lines on the
same game, allowing a bet on each side that can both win.

| Function | Detects |
|----------|---------|
| `detect_spread_middles(df)` | Best home spread vs best away spread gap |
| `detect_total_middles(df)` | Lowest total (Over) vs highest total (Under) gap |
| `detect_middles(df)` | Both, concatenated |

Threshold: `min_middle_points` (default 1.0).

## CLI

```bash
sportsquant nfl ev           --player "Patrick Mahomes" --stat passing_yards --line 280.5 --odds -110
sportsquant nfl kelly        --edge 0.05 --odds -110 --bankroll 1000
sportsquant nfl backtest     --csv lines.csv --walk-forward
sportsquant nfl ratings      --season 2024 --method massey
sportsquant nfl props        --site prizepicks --min-ev 0.05
sportsquant nfl predict-game --home KC --away BAL --season 2024 --week 10
```

## Notebooks

Five NFL notebooks in `notebooks/football/`:

| # | Topic | Cells |
|---|-------|-------|
| 01 | NFL Player Props (nflfastR EV) | 15 |
| 02 | NFL Backtest (walk-forward) | 14 |
| 03 | NFL Power Ratings | 13 |
| 04 | NFL Game Predict (XGBoost) | 13 |
| 05 | NFL Middling & Multi-Book Odds | 16 |

## Web UI

A new `NFL Game Predictor` page is available at `/nfl-predict` with:

- Team input form (home/away + season/week)
- 10 team-strength feature inputs (PPG for/against, yards/play, etc.)
- Model path override (defaults to synthetic bootstrap)
- Live prediction: home/away win prob, projected spread, projected total
- Top 8 feature importances with horizontal bar chart

`uvicorn sportsquant.web.app:app --port 8080` then visit
`http://localhost:8080/nfl-predict`.

## Tests

762 tests cover the NFL surface:

- `tests/test_data/test_nfl.py` — pipeline integration
- `tests/test_data/test_sources/test_odds_api_game_lines.py` — multi-book parser
- `tests/test_core/test_betting/test_middling.py` — middling strategy
- `tests/test_models/test_predictive/test_nfl_game_model.py` — XGBoost ensemble
- `tests/test_util/test_time_utils.py` — shared helpers
- `tests/test_data/test_sources/test_curated_io.py` — CuratedPaths stub
