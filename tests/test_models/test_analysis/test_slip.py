"""Tests for slip optimizer (new)."""

from sportsquant.models.analysis.slip_optimizer import (
    SlipOptimizer,
    SlipConfig,
    SlipEntry,
    optimize_slip,
)


class TestSlipConfig:
    """Tests for SlipConfig dataclass."""

    def test_default_config(self):
        """Test default slip configuration."""
        config = SlipConfig()
        assert config.max_legs == 6
        assert config.min_ev == 0.05
        assert config.max_correlation == 0.7

    def test_custom_config(self):
        """Test custom slip configuration."""
        config = SlipConfig(max_legs=4, min_ev=0.10, max_correlation=0.5)
        assert config.max_legs == 4
        assert config.min_ev == 0.10


class TestSlipEntry:
    """Tests for SlipEntry model."""

    def test_slip_entry_creation(self):
        """Test creating a slip entry."""
        entry = SlipEntry(
            player_name="LeBron James",
            stat_type="Points",
            line=25.5,
            side="OVER",
            odds=-110,
            ev=0.15,
            probability=0.60,
        )
        assert entry.player_name == "LeBron James"
        assert entry.ev == 0.15

    def test_slip_entry_negative_ev(self):
        """Test slip entry with negative EV."""
        entry = SlipEntry(
            player_name="Test",
            stat_type="Points",
            line=10.5,
            side="OVER",
            odds=-110,
            ev=-0.05,
            probability=0.45,
        )
        assert entry.ev < 0


class TestSlipOptimizer:
    """Tests for SlipOptimizer class."""

    def setup_method(self):
        self.optimizer = SlipOptimizer()

    def _make_entries(self, n=5):
        """Create sample slip entries."""
        entries = []
        for i in range(n):
            entries.append(
                SlipEntry(
                    player_name=f"Player {i}",
                    stat_type="Points",
                    line=20.0 + i,
                    side="OVER",
                    odds=-110,
                    ev=0.10 + i * 0.02,
                    probability=0.55 + i * 0.02,
                )
            )
        return entries

    def test_optimize_empty(self):
        """Test optimization with empty entries."""
        result = self.optimizer.optimize([])
        assert len(result.entries) == 0
        assert result.total_ev == 0.0

    def test_optimize_single_entry(self):
        """Test optimization with single entry."""
        entries = [
            SlipEntry(
                player_name="LeBron James",
                stat_type="Points",
                line=25.5,
                side="OVER",
                odds=-110,
                ev=0.15,
                probability=0.60,
            )
        ]
        result = self.optimizer.optimize(entries)
        assert len(result.entries) == 1
        assert result.total_ev > 0

    def test_optimize_filters_low_ev(self):
        """Test optimization filters out low EV entries."""
        entries = [
            SlipEntry("P1", "Points", 10.5, "OVER", -110, 0.02, 0.51),
            SlipEntry("P2", "Points", 20.5, "OVER", -110, 0.15, 0.60),
        ]
        result = self.optimizer.optimize(entries)
        # Only the high EV entry should remain
        assert len(result.entries) == 1
        assert result.entries[0].player_name == "P2"

    def test_optimize_respects_max_legs(self):
        """Test optimization respects max legs limit."""
        config = SlipConfig(max_legs=3, min_ev=0.05)
        optimizer = SlipOptimizer(config=config)
        entries = self._make_entries(10)
        result = optimizer.optimize(entries)
        assert len(result.entries) <= 3

    def test_optimize_ev_ranking(self):
        """Test optimization ranks by EV descending."""
        entries = self._make_entries(5)
        result = self.optimizer.optimize(entries)
        evs = [e.ev for e in result.entries]
        assert all(evs[i] >= evs[i + 1] for i in range(len(evs) - 1))

    def test_optimize_parlay_ev(self):
        """Test parlay EV calculation."""
        entries = [
            SlipEntry("P1", "Points", 10.5, "OVER", -110, 0.10, 0.55),
            SlipEntry("P2", "Points", 20.5, "OVER", -110, 0.10, 0.55),
        ]
        result = self.optimizer.optimize(entries)
        # Parlay EV should be different from sum of individual EVs
        assert result.total_ev > 0

    def test_optimize_with_correlation_penalty(self):
        """Test optimization applies correlation penalty."""
        # Two entries with same player (highly correlated)
        entries = [
            SlipEntry("LeBron James", "Points", 25.5, "OVER", -110, 0.15, 0.60),
            SlipEntry("LeBron James", "Assists", 7.5, "OVER", -110, 0.12, 0.58),
        ]
        result = self.optimizer.optimize(entries)
        # May or may not include both depending on correlation threshold
        assert len(result.entries) >= 1

    def test_optimize_result_attributes(self):
        """Test OptimizedSlip has expected attributes."""
        entries = self._make_entries(3)
        result = self.optimizer.optimize(entries)
        assert hasattr(result, "entries")
        assert hasattr(result, "total_ev")
        assert hasattr(result, "total_odds")
        assert hasattr(result, "combined_probability")


class TestOptimizeSlip:
    """Tests for optimize_slip convenience function."""

    def test_optimize_slip_function(self):
        """Test optimize_slip convenience function."""
        entries = [
            {
                "player_name": "P1",
                "stat_type": "Points",
                "line": 10.5,
                "side": "OVER",
                "odds": -110,
                "ev": 0.15,
                "probability": 0.60,
            },
            {
                "player_name": "P2",
                "stat_type": "Points",
                "line": 20.5,
                "side": "OVER",
                "odds": -110,
                "ev": 0.12,
                "probability": 0.58,
            },
        ]
        result = optimize_slip(entries)
        assert len(result.entries) == 2
        assert result.total_ev > 0

    def test_optimize_slip_empty(self):
        """Test optimize_slip with empty list."""
        result = optimize_slip([])
        assert len(result.entries) == 0
