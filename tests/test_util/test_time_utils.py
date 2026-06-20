"""Tests for time/date utility helpers."""

from __future__ import annotations

import re

from quantitative_sports.util.time_utils import (
    american_to_implied_prob,
    safe_float,
    utc_now_iso,
)


def test_utc_now_iso_format() -> None:
    s = utc_now_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s)


def test_safe_float_handles_none_and_empty() -> None:
    assert safe_float(None) is None
    assert safe_float("") is None
    assert safe_float("   ") is None


def test_safe_float_converts_numbers_and_strings() -> None:
    assert safe_float("3.14") == 3.14
    assert safe_float(42) == 42.0
    assert safe_float(0) == 0.0


def test_safe_float_returns_none_on_garbage() -> None:
    assert safe_float("not a number") is None
    assert safe_float([1, 2]) is None


def test_american_to_implied_prob_negative() -> None:
    # -110 → 110/210 ≈ 0.5238
    prob = american_to_implied_prob(-110)
    assert prob is not None
    assert abs(prob - (110 / 210)) < 1e-9


def test_american_to_implied_prob_positive() -> None:
    # +150 → 100/250 = 0.4
    prob = american_to_implied_prob(150)
    assert prob is not None
    assert abs(prob - 0.4) < 1e-9


def test_american_to_implied_prob_edge_cases() -> None:
    assert american_to_implied_prob(None) is None
    assert american_to_implied_prob(0) is None
    assert american_to_implied_prob("garbage") is None


def test_american_to_implied_prob_string_input() -> None:
    prob = american_to_implied_prob("-110")
    assert prob is not None
    assert abs(prob - (110 / 210)) < 1e-9
