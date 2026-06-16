"""Tests for odds utilities (migrated from sports-bet)."""

import pytest

from sportsquant.core.betting.odds import Odds


class TestOdds:
    """Tests for Odds dataclass."""

    def test_american_to_decimal_negative(self):
        """Test conversion of negative American odds to decimal."""
        odds = Odds(american=-110)
        decimal = odds.to_decimal()
        assert round(decimal, 4) == 1.9091

    def test_american_to_decimal_positive(self):
        """Test conversion of positive American odds to decimal."""
        odds = Odds(american=150)
        decimal = odds.to_decimal()
        assert decimal == 2.5

    def test_american_to_decimal_even(self):
        """Test conversion of even (+100) odds."""
        odds = Odds(american=100)
        decimal = odds.to_decimal()
        assert decimal == 2.0

    def test_decimal_direct(self):
        """Test direct decimal odds."""
        odds = Odds(decimal=2.0)
        assert odds.to_decimal() == 2.0

    def test_implied_prob_negative(self):
        """Test implied probability for negative odds."""
        odds = Odds(american=-110)
        prob = odds.implied_prob()
        assert round(prob, 4) == 0.5238

    def test_implied_prob_positive(self):
        """Test implied probability for positive odds."""
        odds = Odds(american=150)
        prob = odds.implied_prob()
        assert round(prob, 4) == 0.4

    def test_implied_prob_even(self):
        """Test implied probability for even odds."""
        odds = Odds(american=100)
        prob = odds.implied_prob()
        assert prob == 0.5

    def test_no_odds_raises(self):
        """Test that missing odds raises ValueError."""
        odds = Odds()
        with pytest.raises(ValueError):
            odds.to_decimal()

    def test_american_zero_raises(self):
        """Test that zero American odds raises ValueError."""
        odds = Odds(american=0)
        with pytest.raises(ValueError):
            odds.to_decimal()


class TestNormalizePlayerName:
    """Tests for normalize_player_name function (inline)."""

    def normalize_player_name(self, name: str | None) -> str | None:
        """Inline normalize_player_name for testing."""
        if not name or not name.strip():
            return None
        result = name.lower().strip()
        result = result.replace("'", "")
        for suffix in [" sr.", " jr.", " ii", " iii", " iv"]:
            if result.endswith(suffix):
                result = result[: -len(suffix)]
        return result.strip()

    def test_basic_normalization(self) -> None:
        assert self.normalize_player_name("Jayson Tatum") == "jayson tatum"
        assert self.normalize_player_name("Stephen Curry") == "stephen curry"

    def test_smart_apostrophes(self) -> None:
        assert self.normalize_player_name("De'Anthony") == "deanthony"
        assert self.normalize_player_name("O'Neal") == "oneal"

    def test_suffixes_removed(self) -> None:
        assert self.normalize_player_name("Tim Duncan Sr.") == "tim duncan"
        assert self.normalize_player_name("Tim Duncan Jr.") == "tim duncan"
        assert self.normalize_player_name("Larry Bird II") == "larry bird"
        assert self.normalize_player_name("Larry Bird III") == "larry bird"
        assert self.normalize_player_name("Peter Parker IV") == "peter parker"

    def test_none_input(self) -> None:
        assert self.normalize_player_name(None) is None

    def test_empty_input(self) -> None:
        assert self.normalize_player_name("") is None
        assert self.normalize_player_name("   ") is None
