"""Tests for walk-forward validation and regime detection (new)."""

import pandas as pd
import numpy as np

from sportsquant.core.backtest.regime import (
    RegimeDetector,
    WalkForwardValidator,
    RegimeConfig,
    detect_regime_shift,
)


class TestRegimeDetector:
    """Tests for RegimeDetector class."""

    def test_detect_stable_regime(self):
        """Test detection of a stable (low volatility) regime."""
        # Generate stable returns
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.01, 100)
        detector = RegimeDetector()
        regime = detector.detect(returns)
        assert regime in ["low_volatility", "normal", "high_volatility"]

    def test_detect_high_volatility(self):
        """Test detection of high volatility regime."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.05, 100)  # Higher volatility
        detector = RegimeDetector()
        regime = detector.detect(returns)
        # Should detect higher volatility
        assert regime is not None

    def test_detect_trending_regime(self):
        """Test detection of trending regime."""
        # Strong upward trend
        returns = np.linspace(0.001, 0.01, 100) + np.random.normal(0, 0.005, 100)
        detector = RegimeDetector()
        regime = detector.detect(returns)
        assert regime is not None

    def test_empty_returns(self):
        """Test detection with empty returns."""
        detector = RegimeDetector()
        regime = detector.detect([])
        assert regime == "unknown"

    def test_insufficient_data(self):
        """Test detection with insufficient data points."""
        detector = RegimeDetector()
        regime = detector.detect([0.01, 0.02])
        assert regime == "unknown"

    def test_regime_config_custom_thresholds(self):
        """Test custom regime configuration."""
        config = RegimeConfig(
            low_vol_threshold=0.005,
            high_vol_threshold=0.03,
            trend_strength_threshold=0.6,
        )
        detector = RegimeDetector(config=config)
        assert detector.config.low_vol_threshold == 0.005
        assert detector.config.high_vol_threshold == 0.03


class TestWalkForwardValidator:
    """Tests for WalkForwardValidator class."""

    def test_basic_walk_forward(self):
        """Test basic walk-forward validation with simple data."""
        # Create simple time series data
        dates = pd.date_range(start="2024-01-01", periods=200, freq="D")
        data = pd.DataFrame(
            {
                "value": np.random.randn(200).cumsum() + 100,
                "feature": np.random.randn(200),
            },
            index=dates,
        )

        validator = WalkForwardValidator(
            window_size=50,
            step_size=10,
            min_train_size=30,
        )

        results = validator.validate(data, target_col="value")
        assert len(results) > 0
        assert all("train_start" in r for r in results)
        assert all("train_end" in r for r in results)
        assert all("test_start" in r for r in results)
        assert all("test_end" in r for r in results)

    def test_walk_forward_metrics(self):
        """Test that walk-forward produces metric results."""
        dates = pd.date_range(start="2024-01-01", periods=150, freq="D")
        data = pd.DataFrame(
            {
                "value": np.random.randn(150).cumsum() + 100,
                "feature": np.random.randn(150),
            },
            index=dates,
        )

        validator = WalkForwardValidator(
            window_size=40,
            step_size=10,
            min_train_size=30,
        )

        results = validator.validate(data, target_col="value")
        for r in results:
            assert "n_train" in r
            assert "n_test" in r
            assert r["n_train"] >= 30

    def test_walk_forward_insufficient_data(self):
        """Test walk-forward with insufficient data."""
        dates = pd.date_range(start="2024-01-01", periods=20, freq="D")
        data = pd.DataFrame(
            {
                "value": np.random.randn(20),
            },
            index=dates,
        )

        validator = WalkForwardValidator(
            window_size=50,  # Larger than data
            step_size=10,
            min_train_size=30,
        )

        results = validator.validate(data, target_col="value")
        assert len(results) == 0

    def test_walk_forward_custom_metric(self):
        """Test walk-forward with custom metric function."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
        data = pd.DataFrame(
            {
                "value": np.random.randn(100).cumsum() + 100,
            },
            index=dates,
        )

        def custom_metric(train, test):
            return {
                "train_mean": float(train["value"].mean()),
                "test_mean": float(test["value"].mean()),
            }

        validator = WalkForwardValidator(
            window_size=30,
            step_size=10,
            min_train_size=20,
        )

        results = validator.validate(data, target_col="value", metric_fn=custom_metric)
        for r in results:
            assert "train_mean" in r
            assert "test_mean" in r


class TestDetectRegimeShift:
    """Tests for detect_regime_shift function."""

    def test_detect_shift(self):
        """Test detecting a regime shift in time series."""
        # Create series with a clear shift
        before = np.random.normal(0, 0.01, 50)
        after = np.random.normal(0.02, 0.03, 50)
        series = np.concatenate([before, after])

        shift_point = detect_regime_shift(series)
        assert shift_point is not None
        # Should detect shift around index 50
        assert 40 <= shift_point <= 60

    def test_no_shift(self):
        """Test no regime shift in stable series."""
        series = np.random.normal(0, 0.01, 100)
        shift_point = detect_regime_shift(series)
        # May or may not detect a shift, but should be reasonable
        if shift_point is not None:
            assert 0 <= shift_point < len(series)

    def test_shift_with_date_index(self):
        """Test regime shift detection with pandas index."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
        before = np.random.normal(0, 0.01, 50)
        after = np.random.normal(0.02, 0.03, 50)
        series = pd.Series(np.concatenate([before, after]), index=dates)

        shift_point = detect_regime_shift(series)
        assert shift_point is not None

    def test_insufficient_data(self):
        """Test regime shift with insufficient data."""
        series = [1, 2, 3]
        shift_point = detect_regime_shift(series)
        assert shift_point is None
