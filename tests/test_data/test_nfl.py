"""Tests for the NFL pipeline middling + multi-book integration."""

from __future__ import annotations


import pandas as pd

from sportsquant.data.nfl import NFLDataConfig, NFLDataPipeline


def test_detect_middles_delegates_to_strategy() -> None:
    pipeline = NFLDataPipeline()
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": -7.0, "source_id": "BookB"},
        ]
    )
    out = pipeline.detect_middles(df, min_middle_points=1.0)
    assert len(out) == 1
    assert out.iloc[0]["market"] == "spread"


def test_get_multi_book_odds_parses_response(monkeypatch) -> None:
    """httpx is mocked to return a fixture, parser runs end-to-end."""

    payload = [
        {
            "id": "e1",
            "commence_time": "2026-09-07T20:20:00Z",
            "home_team": "Chiefs",
            "away_team": "Ravens",
            "bookmakers": [
                {
                    "title": "DraftKings",
                    "last_update": "2026-09-07T18:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Chiefs", "price": -150},
                                {"name": "Ravens", "price": 130},
                            ],
                        },
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Chiefs", "point": -3.5, "price": -110},
                                {"name": "Ravens", "point": 3.5, "price": -110},
                            ],
                        },
                    ],
                }
            ],
        }
    ]

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list:
            return self._data

    captured: dict = {}

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        captured["url"] = url
        captured["params"] = params
        return FakeResp(payload)

    # Patch the httpx module attribute used inside sportsquant.data.nfl
    monkeypatch.setattr("httpx.get", fake_get)

    pipeline = NFLDataPipeline(config=NFLDataConfig())
    df = pipeline.get_multi_book_odds(api_key="test-key")

    assert "americanfootball_nfl" in captured["url"]
    assert captured["params"]["apiKey"] == "test-key"
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ml_home"] == -150
    assert row["ml_away"] == 130
    assert row["spread_home"] == -3.5
    assert row["source_id"] == "DraftKings"


def test_get_multi_book_odds_raises_without_httpx(monkeypatch) -> None:
    """When httpx is missing the pipeline surfaces a helpful error."""

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ARG001
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pipeline = NFLDataPipeline()
    try:
        pipeline.get_multi_book_odds(api_key="x")
    except ImportError as e:
        assert "httpx" in str(e)
    else:
        raise AssertionError("expected ImportError when httpx missing")
