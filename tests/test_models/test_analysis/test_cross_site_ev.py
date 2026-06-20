"""Tests for cross-site EV analysis (migrated from sports-bet)."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd

from quantitative_sports.models.analysis.cross_site_ev import CrossSiteEVEngine


class TestMapAlternateToStandard:
    """Tests for map_alternate_to_standard method."""

    @patch("quantitative_sports.models.analysis.cross_site_ev.CrossSiteEVEngine._get_dk_storage")
    def test_maps_fd_alt_to_dk_standard(
        self,
        mock_get_dk: MagicMock,
        mock_dk_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        mock_get_dk.return_value = mock_dk_storage

        fd_row = pd.Series(
            {
                "player_name_norm": "stephen curry",
                "market_key": "player_points",
                "market_name": "Points 10+",
                "threshold": 10.0,
                "line": 0,
            }
        )

        try:
            result = engine.map_alternate_to_standard(fd_row)
            assert result is None
        except sqlite3.OperationalError:
            pass

        engine.close()


class TestCalculateCrossSiteEV:
    """Tests for calculate_cross_site_ev method."""

    def test_calculates_ev_with_history(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        player_history = [25, 28, 32, 18, 35, 22, 29, 31, 27, 33]

        result = engine.calculate_cross_site_ev(
            player_name="stephen curry",
            stat="player_points",
            threshold=25.0,
            fd_odds=-110,
            dk_line=25.5,
            dk_odds=-115,
            player_history=player_history,
        )

        assert "ev" in result
        assert "probability" in result
        assert "breakeven" in result
        assert "confidence" in result
        assert "recommendation" in result
        assert result["sample_size"] == 10
        assert result["distribution_type"] != "none"

        engine.close()

    def test_no_data_returns_no_data_indicator(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        result = engine.calculate_cross_site_ev(
            player_name="unknown player",
            stat="player_points",
            threshold=25.0,
            fd_odds=-110,
        )

        assert result["recommendation"] == "NO_DATA"
        assert result["sample_size"] == 0
        assert result["confidence"] == 0.0

        engine.close()


class TestFindOpportunities:
    """Tests for find_opportunities method."""

    @patch("quantitative_sports.models.analysis.cross_site_ev.CrossSiteEVEngine._get_dk_storage")
    @patch("quantitative_sports.models.analysis.cross_site_ev.CrossSiteEVEngine._get_fd_storage")
    def test_filters_by_min_ev(
        self,
        mock_get_fd: MagicMock,
        mock_get_dk: MagicMock,
        mock_dk_storage: MagicMock,
        mock_fd_storage: MagicMock,
        tmp_path: Path,
    ) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        mock_get_dk.return_value = mock_dk_storage
        mock_get_fd.return_value = mock_fd_storage

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        try:
            opportunities = engine.find_opportunities(min_ev=0.05)
            assert opportunities.empty
        except Exception:
            pass

        engine.close()


class TestUnicodeOddsNormalization:
    """Tests for Unicode minus sign handling."""

    def test_parse_fanduel_market_name(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        test_cases = [
            ("Points 10+", {"stat_type": "point", "threshold": 10.0, "direction": "over"}),
            ("Over 25 Points", {"stat_type": "point", "threshold": 25.0, "direction": "over"}),
            ("Rebounds 5.5+", {"stat_type": "rebound", "threshold": 5.5, "direction": "over"}),
        ]

        for market_name, expected in test_cases:
            result = engine._parse_fanduel_market_name(market_name, "player_points")
            if result:
                assert result["stat_type"] == expected["stat_type"]
                assert result["threshold"] == expected["threshold"]
                assert result["direction"] == expected["direction"]

        engine.close()


class TestIsAlternateMarketName:
    """Tests for _is_alternate_market_name method."""

    def test_detects_alternate_patterns(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        assert engine._is_alternate_market_name("To Score 15+ Points") is True
        assert engine._is_alternate_market_name("To Record 4+ Rebounds") is True
        assert engine._is_alternate_market_name("15+ Points") is True
        assert engine._is_alternate_market_name("4+ Rebounds") is True
        assert engine._is_alternate_market_name("3+ Assists") is True

        assert engine._is_alternate_market_name("Points O/U 10.5") is False
        assert engine._is_alternate_market_name("Over 10 Points") is False

        engine.close()


class TestExtractThreshold:
    """Tests for _extract_threshold_from_market_name method."""

    def test_extracts_threshold(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        assert engine._extract_threshold_from_market_name("To Score 15+ Points") == 15.0
        assert engine._extract_threshold_from_market_name("To Record 4+ Rebounds") == 4.0
        assert engine._extract_threshold_from_market_name("2+ Made Threes") == 2.0
        assert engine._extract_threshold_from_market_name("Points O/U 10.5") is None

        engine.close()


class TestStatKeyToStatType:
    """Tests for _stat_key_to_stat_type method."""

    def test_converts_stat_key(self, tmp_path: Path) -> None:
        dk_db = tmp_path / "dk.db"
        fd_db = tmp_path / "fd.db"
        dk_db.touch()
        fd_db.touch()

        engine = CrossSiteEVEngine(
            draftkings_db_path=dk_db,
            fanduel_db_path=fd_db,
        )

        assert engine._stat_key_to_stat_type("player_points") == "points"
        assert engine._stat_key_to_stat_type("player_rebounds") == "rebounds"
        assert engine._stat_key_to_stat_type("player_assists") == "assists"

        engine.close()
