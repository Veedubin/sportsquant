"""Tests for DraftKings utility functions (migrated from sports-bet)."""

from quantitative_sports.data.sources.draftkings.utils import (
    american_to_decimal,
    american_to_prob,
    map_market_name_to_key,
    map_subcategory_id_to_market_key,
    normalize_odds_string,
    normalize_player_name,
    prob_to_american,
    remove_vig_two_way,
)


class TestNormalizeOddsString:
    """Tests for normalize_odds_string function."""

    def test_standard_odds(self) -> None:
        """Test normalization of standard odds string."""
        assert normalize_odds_string("-130") == "-130"
        assert normalize_odds_string("+105") == "+105"

    def test_unicode_minus(self) -> None:
        """Test normalization of Unicode minus sign (U+2212)."""
        # Unicode minus: U+2212 followed by digits represents negative odds
        # For positive odds with Unicode, we'd need to ensure the string starts with +
        assert normalize_odds_string("\u2212130") == "-130"  # Negative odds: -130
        assert normalize_odds_string("\u2212105") == "-105"  # Negative odds: -105
        # Unicode minus at start should be replaced with ASCII minus
        assert normalize_odds_string("\u2212") == "-"  # Just the minus sign

    def test_empty_string(self) -> None:
        """Test empty string handling."""
        assert normalize_odds_string("") == ""
        assert normalize_odds_string(None) is None

    def test_already_normalized(self) -> None:
        """Test string that's already normalized."""
        assert normalize_odds_string("-110") == "-110"
        assert normalize_odds_string("+150") == "+150"


class TestAmericanToProb:
    """Tests for american_to_prob function."""

    def test_negative_odds(self) -> None:
        """Test conversion of negative American odds."""
        # -110: 110/(110+100) = 0.5238
        prob = american_to_prob(-110)
        assert round(prob, 4) == 0.5238

        # -130: 130/(130+100) = 0.5652
        prob = american_to_prob(-130)
        assert round(prob, 4) == 0.5652

    def test_positive_odds(self) -> None:
        """Test conversion of positive American odds."""
        # +100: 100/(100+100) = 0.5
        prob = american_to_prob(100)
        assert prob == 0.5

        # +150: 100/(150+100) = 0.4
        prob = american_to_prob(150)
        assert round(prob, 4) == 0.4

    def test_string_input(self) -> None:
        """Test conversion from string input."""
        prob = american_to_prob("-110")
        assert round(prob, 4) == 0.5238

    def test_unicode_minus_string(self) -> None:
        """Test conversion from string with Unicode minus."""
        # Unicode minus: U+2212
        prob = american_to_prob("\u2212110")
        assert round(prob, 4) == 0.5238

    def test_none_input(self) -> None:
        """Test None input returns 0.0."""
        assert american_to_prob(None) == 0.0

    def test_empty_string(self) -> None:
        """Test empty string returns 0.0."""
        assert american_to_prob("") == 0.0

    def test_invalid_string(self) -> None:
        """Test invalid string returns 0.0."""
        assert american_to_prob("invalid") == 0.0


class TestAmericanToDecimal:
    """Tests for american_to_decimal function."""

    def test_negative_odds(self) -> None:
        """Test conversion of negative American odds to decimal."""
        # -110: 1 + 100/110 = 1.9091
        decimal = american_to_decimal(-110)
        assert round(decimal, 4) == 1.9091

    def test_positive_odds(self) -> None:
        """Test conversion of positive American odds to decimal."""
        # +150: 1 + 150/100 = 2.5
        decimal = american_to_decimal(150)
        assert decimal == 2.5

    def test_plus_100(self) -> None:
        """Test +100 converts to 2.0 decimal."""
        assert american_to_decimal(100) == 2.0

    def test_none_input(self) -> None:
        """Test None input returns 0.0."""
        assert american_to_decimal(None) == 0.0


class TestProbToAmerican:
    """Tests for prob_to_american function."""

    def test_prob_to_american_negative(self) -> None:
        """Test converting probability to negative American odds."""
        # 0.55 -> -122 (approx)
        odds = prob_to_american(0.55)
        assert odds < 0

    def test_prob_to_american_positive(self) -> None:
        """Test converting probability to positive American odds."""
        # 0.35 -> +186 (approx)
        odds = prob_to_american(0.35)
        assert odds > 0

    def test_prob_half(self) -> None:
        """Test 0.5 probability returns +100."""
        assert prob_to_american(0.5) == 100.0

    def test_prob_one(self) -> None:
        """Test probability 1.0 returns infinity."""
        assert prob_to_american(1.0) == float("inf")

    def test_prob_zero(self) -> None:
        """Test probability 0.0 returns negative infinity."""
        assert prob_to_american(0.0) == float("-inf")


class TestRemoveVigTwoWay:
    """Tests for remove_vig_two_way function."""

    def test_remove_vig_balanced(self) -> None:
        """Test removing vig from balanced market."""
        # Both at -110 (50% each raw)
        p_over = 0.4762
        p_under = 0.4762
        devigged = remove_vig_two_way(p_over, p_under)
        assert round(devigged, 4) == 0.5

    def test_remove_vig_unbalanced(self) -> None:
        """Test removing vig from unbalanced market."""
        p_over = 0.55
        p_under = 0.45
        devigged = remove_vig_two_way(p_over, p_under)
        assert round(devigged, 4) == 0.55

    def test_remove_vig_zero_total(self) -> None:
        """Test zero total returns NaN."""
        result = remove_vig_two_way(0.0, 0.0)
        assert result != result  # NaN check

    def test_remove_vig_negative_total(self) -> None:
        """Test negative total returns NaN."""
        # When both probabilities sum to negative (invalid market)
        result = remove_vig_two_way(-0.1, -0.5)
        assert result != result  # NaN check


class TestMapSubcategoryIdToMarketKey:
    """Tests for map_subcategory_id_to_market_key function."""

    def test_points(self) -> None:
        """Test mapping points subcategory."""
        assert map_subcategory_id_to_market_key(12488) == "player_points"

    def test_rebounds(self) -> None:
        """Test mapping rebounds subcategory."""
        assert map_subcategory_id_to_market_key(12492) == "player_rebounds"

    def test_assists(self) -> None:
        """Test mapping assists subcategory."""
        assert map_subcategory_id_to_market_key(12495) == "player_assists"

    def test_threes(self) -> None:
        """Test mapping threes subcategory."""
        assert map_subcategory_id_to_market_key(12497) == "player_threes"

    def test_unknown_subcategory(self) -> None:
        """Test unknown subcategory returns None."""
        assert map_subcategory_id_to_market_key(99999) is None

    def test_string_input(self) -> None:
        """Test string subcategory ID."""
        assert map_subcategory_id_to_market_key("12488") == "player_points"


class TestMapMarketNameToKey:
    """Tests for map_market_name_to_key function."""

    def test_points(self) -> None:
        """Test mapping points market name."""
        assert map_market_name_to_key("Points O/U") == "player_points"
        assert map_market_name_to_key("Victor Wembanyama Points O/U") == "player_points"

    def test_rebounds(self) -> None:
        """Test mapping rebounds market name."""
        assert map_market_name_to_key("Rebounds O/U") == "player_rebounds"

    def test_assists(self) -> None:
        """Test mapping assists market name."""
        assert map_market_name_to_key("Assists O/U") == "player_assists"

    def test_threes(self) -> None:
        """Test mapping threes market name."""
        assert map_market_name_to_key("Three Pointers O/U") == "player_threes"
        assert map_market_name_to_key("Three Pointers Made O/U") == "player_threes"

    def test_steals_blocks(self) -> None:
        """Test mapping steals + blocks market name."""
        assert map_market_name_to_key("Steals + Blocks O/U") == "player_sb"
        assert map_market_name_to_key("Steals & Blocks O/U") == "player_sb"

    def test_triple_double(self) -> None:
        """Test mapping triple double market name."""
        assert map_market_name_to_key("Triple Double") == "player_triple_double"

    def test_double_double(self) -> None:
        """Test mapping double double market name."""
        assert map_market_name_to_key("Double Double") == "player_double_double"

    def test_none_input(self) -> None:
        """Test None input returns None."""
        assert map_market_name_to_key(None) is None

    def test_unknown_market(self) -> None:
        """Test unknown market returns None."""
        assert map_market_name_to_key("Unknown Market") is None


class TestNormalizePlayerName:
    """Tests for normalize_player_name function."""

    def test_basic_normalization(self) -> None:
        """Test basic name normalization."""
        assert normalize_player_name("Jayson Tatum") == "jayson tatum"
        assert normalize_player_name("Stephen Curry") == "stephen curry"

    def test_smart_apostrophes(self) -> None:
        """Test handling of smart apostrophes."""
        assert normalize_player_name("De'Anthony") == "deanthony"
        assert normalize_player_name("O'Neal") == "oneal"

    def test_suffixes_removed(self) -> None:
        """Test common suffixes are removed."""
        assert normalize_player_name("Tim Duncan Sr.") == "tim duncan"
        assert normalize_player_name("Tim Duncan Jr.") == "tim duncan"
        assert normalize_player_name("Larry Bird II") == "larry bird"
        assert normalize_player_name("Larry Bird III") == "larry bird"
        assert normalize_player_name("Peter Parker IV") == "peter parker"

    def test_none_input(self) -> None:
        """Test None input returns None."""
        assert normalize_player_name(None) is None

    def test_empty_input(self) -> None:
        """Test empty input returns None."""
        assert normalize_player_name("") is None
        assert normalize_player_name("   ") is None
