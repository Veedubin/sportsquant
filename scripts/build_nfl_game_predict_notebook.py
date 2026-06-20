"""Build the NFL game prediction notebook programmatically.

Avoids the previous markdown-cell-with-execution_count JSON bug that
broke CI: this writes a clean notebook where every markdown cell has
no execution_count or outputs keys, and every code cell has matching
source and outputs in canonical nbformat.

Run:  python scripts/build_nfl_game_predict_notebook.py
Output: notebooks/football/04_nfl_game_predict.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.12",
    },
}

cells: list[nbf.NotebookNode] = []


def md(text: str) -> nbf.NotebookNode:
    """Return a clean markdown cell (no execution metadata)."""
    cell = nbf.v4.new_markdown_cell(text)
    return cell


def code(text: str) -> nbf.NotebookNode:
    """Return a code cell with empty outputs."""
    cell = nbf.v4.new_code_cell(text)
    cell.outputs = []
    cell.execution_count = None
    return cell


# Cell 0 — title
cells.append(
    md(
        """# NFL Game Outcome Prediction (XGBoost)

Predict home win probability, projected spread, and projected total for any NFL game
using team-level rolling aggregates from `nflfastR` and an XGBoost ensemble.

**What's inside:**
- `NFLGamePredictor` — wraps an XGBoost classifier (win probability) plus two
  XGBoost regressors (spread, total).
- `NFLGameFeatures` — 14 hand-engineered team-strength features.
- `train_default_model` — synthetic-data bootstrap so you can run the full
  pipeline without network access. Plug in real `nflfastR` play-by-play to
  retrain for production use.
"""
    )
)


# Cell 1 — imports
cells.append(
    code(
        """from quantitative_sports.models.predictive.nfl_game_model import (
    NFLGameFeatures,
    NFLGamePredictor,
    feature_columns,
    train_default_model,
)
from quantitative_sports.data.nfl import NFLDataConfig, NFLDataPipeline
from quantitative_sports.models.predictive.nfl_game_model import build_features_from_pipeline

print('NFL XGBoost predictor ready')
print('Feature columns:', feature_columns())"""
    )
)


# Cell 2 — train default model
cells.append(
    md(
        """## 1. Train a default model

We bootstrap with a synthetic dataset so the notebook runs offline. For real
production use, swap in `nflfastR` play-by-play + nflverse schedules and call
`predictor.train(real_df)` directly."""
    )
)


cells.append(
    code(
        """predictor = train_default_model(n_games=600, verbose=True)
print('Trained. Feature importances:')
for feat, imp in sorted(predictor.feature_importances.items(), key=lambda x: -x[1]):
    print(f'  {feat:24s} {imp:.4f}')"""
    )
)


# Cell 3 — build features from real pipeline
cells.append(
    md(
        """## 2. Build features for a real game

Pulls rolling team aggregates from nflfastR via the `NFLDataPipeline`. When
network/cache is unavailable the function gracefully returns zero-valued
features so downstream code still runs."""
    )
)


cells.append(
    code(
        """pipeline = NFLDataPipeline(config=NFLDataConfig())
features = build_features_from_pipeline(
    pipeline,
    home_team="KC",
    away_team="BAL",
    season=2024,
    week=10,
)
print('Home team:', features.home_team)
print('Away team:', features.away_team)
print('Home PPG for:', round(features.home_ppg_for, 2))
print('Away PPG for:', round(features.away_ppg_for, 2))
print('PPG differential:', round(features.ppg_differential, 2))
print('Defense differential:', round(features.defense_differential, 2))"""
    )
)


# Cell 4 — predict
cells.append(md("""## 3. Predict the outcome"""))


cells.append(
    code(
        """prediction = predictor.predict(features)
print(f'{prediction.away_team} @ {prediction.home_team}')
print(f'  Home win prob: {prediction.home_win_prob:.1%}')
print(f'  Away win prob: {prediction.away_win_prob:.1%}')
print(f'  Projected spread: {prediction.proj_spread:+.1f}')
print(f'  Projected total: {prediction.proj_total:.1f}')"""
    )
)


# Cell 5 — scenario analysis
cells.append(
    md(
        """## 4. Scenario analysis

Compare win probability across multiple hypothetical matchups to find edges
versus the market line."""
    )
)


cells.append(
    code(
        """matchups = [
    ('KC', 'BAL', 28.0, 22.0, 100.0, 85.0),
    ('KC', 'CAR', 28.0, 15.0, 100.0, 70.0),
    ('KC', 'BUF', 25.0, 25.0, 95.0, 95.0),
    ('CAR', 'KC', 15.0, 28.0, 70.0, 100.0),
]
for home, away, hppg, appg, hqbr, aqbr in matchups:
    f = NFLGameFeatures(
        home_team=home, away_team=away, season=2024, week=10,
        home_ppg_for=hppg, away_ppg_for=appg,
        home_qb_rating=hqbr, away_qb_rating=aqbr,
        home_ppg_against=appg, away_ppg_against=hppg,
    )
    p = predictor.predict(f)
    print(f'  {away:3s} @ {home:3s}  prob(home)={p.home_win_prob:5.1%}  spread={p.proj_spread:+5.1f}  total={p.proj_total:5.1f}')"""
    )
)


# Cell 6 — save model
cells.append(
    md(
        """## 5. Save the trained model

Saved models can be loaded later via `NFLGamePredictor.load(path)` — useful
for production scoring jobs that retrain weekly."""
    )
)


cells.append(
    code(
        """from pathlib import Path
save_path = Path('notebooks/football/cache/nfl_game_model')
save_path.mkdir(parents=True, exist_ok=True)
predictor.save(save_path)
print(f'Saved to {save_path}')
print('Files:', sorted(p.name for p in save_path.iterdir()))

# Round-trip load to confirm
reloaded = NFLGamePredictor.load(save_path)
print('Reloaded home win prob:', reloaded.predict(features).home_win_prob)"""
    )
)


# Cell 7 — summary
cells.append(
    md(
        """## Summary

- The `NFLGamePredictor` exposes three XGBoost sub-models trained jointly on the
  same 14-feature schema.
- Synthetic bootstrap lets you iterate without nflfastR access; production
  training swaps `_generate_synthetic_dataset()` for a real `nflfastR` join
  with nflverse schedules.
- Feature importances surface the model signal at a glance: QB rating, PPG
  differential, and defense differential dominate.
- `NFLDataPipeline.build_features_from_pipeline` is the canonical feature
  builder; it gracefully degrades to zeroed features when network/cache is
  unavailable.

Next steps for production:
1. Replace `_generate_synthetic_dataset()` with real play-by-play joins.
2. Calibrate win probabilities (Platt scaling or isotonic regression).
3. Wire into the `nfl predict-game` CLI for ad-hoc usage.
"""
    )
)


nb.cells = cells

out = Path("notebooks/football/04_nfl_game_predict.ipynb")
out.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, str(out))
print(f"Wrote {out} with {len(cells)} cells")
