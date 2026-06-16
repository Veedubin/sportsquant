# ⚠️ DEPRECATED — Use notebooks/ instead

These example notebooks have been migrated to a per-sport structure:

| Old Location | New Location |
|-------------|--------------|
| examples/01_ev_calculation.ipynb | notebooks/common/01_ev_calculation.ipynb |
| examples/02_kelly_optimization.ipynb | notebooks/common/02_kelly_optimization.ipynb |
| examples/03_backtesting.ipynb | notebooks/basketball/03_backtesting.ipynb |
| examples/04_ratings_comparison.ipynb | notebooks/basketball/04_ratings_comparison.ipynb |
| examples/05_parlay_optimization.ipynb | notebooks/common/05_parlay_optimization.ipynb |

New NFL notebooks are available at notebooks/football/.

These files will be removed in v0.3.0.

---

# Examples & Tutorials

This directory provides a curated set of Jupyter notebooks and scripts designed to demonstrate the practical application of the SportsQuant toolkit.

## 📚 Available Examples

### 01. Expected Value Calculation
`01_ev_calculation.ipynb`
- How to derive implied probabilities from various odds formats.
- Calculating edge between model predictions and market prices.
- Identifying positive EV opportunities across different sportsbooks.

### 02. Kelly Optimization
`02_kelly_optimization.ipynb`
- Implementing the Standard Kelly Criterion for bankroll growth.
- Using Fractional Kelly to mitigate volatility and "black swan" events.
- Adaptive sizing based on confidence intervals.

### 03. Strategy Backtesting
`03_backtesting.ipynb`
- Setting up a walk-forward validation pipeline.
- Testing for regime shifts and performance decay.
- Analyzing drawdown, Sharpe ratio, and maximum adverse excursion.

### 04. Rating System Comparison
`04_ratings_comparison.ipynb`
- Comparing RAPTOR, Massey, and PageRank outputs for the same dataset.
- Visualizing the impact of Bayesian shrinkage on player priors.
- Evaluating rating accuracy against actual game outcomes.

## 🚀 Running Examples

To run these examples, ensure you have the environment synced and the required notebooks extension installed:

```bash
uv sync
pip install jupyterlab
jupyter lab
```

## 🛠️ Contributing Examples
If you have developed a novel strategy or a unique analytical approach using SportsQuant, feel free to contribute your notebook to this directory via a Pull Request.
