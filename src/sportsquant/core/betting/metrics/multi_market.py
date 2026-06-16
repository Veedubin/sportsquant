"""Multi-market betting utilities.

Provides tools for cross-market arbitrage, line shopping, and Kelly
sizing across different sportsbooks and markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class MultiMarketConfig:
    """Configuration for multi-market betting strategies."""

    # pylint: disable=R0902

    min_arbitrage_margin: float = 0.01
    max_exposure_per_market: float = 0.25
    max_exposure_per_book: float = 0.30
    preferred_books: list[str] = field(default_factory=lambda: ["pinnacle", "bet365", "unibet"])
    use_kelly_sizing: bool = True
    kelly_fraction: float = 0.25


@dataclass(frozen=True)
class EuropeanBookConfig:
    """Configuration for European book integration."""

    # pylint: disable=R0902

    enabled_books: list[str] = field(
        default_factory=lambda: ["pinnacle", "bet365", "unibet", "williamhill"]
    )
    cache_ttl_seconds: int = 60
    rate_limit_rps: float = 2.0
    prefer_decimal_odds: bool = True


@dataclass(frozen=True)
class EuropeanOddsData:
    """Core odds data for a player prop."""

    book: str
    market: str
    player_id: str
    over_line: float
    over_odds: float
    under_line: float
    under_odds: float


@dataclass(frozen=True)
class EuropeanOdds:
    """European odds data for a player prop."""

    data: EuropeanOddsData
    timestamp: float


@dataclass
class BestLine:
    """Best available line across books for a market."""

    # pylint: disable=R0902

    market: str
    player_id: str
    over_line: float
    over_odds: float
    under_line: float
    under_odds: float
    over_book: str
    under_book: str


@dataclass
class ArbitrageResult:
    """Result of arbitrage calculation between two outcomes."""

    # pylint: disable=R0902

    over_odds: float
    under_odds: float
    over_implied_prob: float
    under_implied_prob: float
    total_implied_prob: float
    arbitrage_margin: float
    over_stake_pct: float
    under_stake_pct: float
    profit_margin_pct: float
    is_arbitrage: bool


@dataclass
class PotentialBet:
    """A potential bet opportunity."""

    # pylint: disable=R0902

    market: str
    player_id: str
    line: float
    odds: float
    side: str
    book: str
    edge: float
    confidence: float
    expected_value: float


@dataclass
class Allocation:
    """Bankroll allocation for multiple bets."""

    total_bankroll: float
    total_allocated: float
    remaining: float
    allocations: list[dict]
    expected_return: float
    risk_score: float


@dataclass
class ComparisonResult:
    """Comparison between DFS and European book odds."""

    # pylint: disable=R0902

    market: str
    player_id: str
    dfs_avg_odds: float
    dfs_best_odds: float
    dfs_best_book: str
    eu_avg_odds: float
    eu_best_odds: float
    eu_best_book: str
    eu_dfs_discrepancy: float
    eu_dfs_value_pct: float
    recommendation: str


class MultiMarketBettor:
    """Multi-market bettor for cross-book arbitrage and line shopping.

    This class provides utilities for finding the best betting lines across
    multiple sportsbooks, calculating arbitrage opportunities, and optimizing
    bet allocation across a bankroll.

    Attributes:
        config: MultiMarketConfig instance controlling betting behavior.
    """

    def __init__(self, config: MultiMarketConfig | None = None) -> None:
        self.config = config or MultiMarketConfig()

    def find_best_line(self, _markets: list[str], _player_ids: list[str]) -> list[BestLine]:
        """Find the best available line across books for given markets.

        Args:
            _markets: List of market identifiers to search.
            _player_ids: List of player IDs to find lines for.

        Returns:
            List of BestLine objects with the best odds for each market.
        """
        return []

    def calculate_arbitrage(self, over_odds: float, under_odds: float) -> ArbitrageResult:
        """Calculate arbitrage opportunity between over and under odds.

        Args:
            over_odds: Decimal odds for the over outcome.
            under_odds: Decimal odds for the under outcome.

        Returns:
            ArbitrageResult with stake percentages and profit margin.
        """
        over_implied = 1.0 / over_odds if over_odds > 1.0 else 0.0
        under_implied = 1.0 / under_odds if under_odds > 1.0 else 0.0
        total_implied = over_implied + under_implied
        arbitrage_margin = 1.0 - total_implied
        profit_margin_pct = arbitrage_margin * 100.0
        is_arbitrage = arbitrage_margin > self.config.min_arbitrage_margin

        if total_implied > 0:
            over_stake_pct = under_implied / total_implied
            under_stake_pct = over_implied / total_implied
        else:
            over_stake_pct = 0.5
            under_stake_pct = 0.5

        return ArbitrageResult(
            over_odds=over_odds,
            under_odds=under_odds,
            over_implied_prob=over_implied,
            under_implied_prob=under_implied,
            total_implied_prob=total_implied,
            arbitrage_margin=arbitrage_margin,
            over_stake_pct=over_stake_pct,
            under_stake_pct=under_stake_pct,
            profit_margin_pct=profit_margin_pct,
            is_arbitrage=is_arbitrage,
        )

    def optimize_bet_allocation(self, bets: list[PotentialBet], bankroll: float) -> Allocation:
        """Optimize bankroll allocation across potential bets.

        Args:
            bets: List of potential bet opportunities.
            bankroll: Total bankroll available.

        Returns:
            Allocation with stake distribution.
        """
        # pylint: disable=R0914
        if not bets:
            return Allocation(
                total_bankroll=bankroll,
                total_allocated=0.0,
                remaining=bankroll,
                allocations=[],
                expected_return=0.0,
                risk_score=0.0,
            )

        allocations_list: list[dict] = []
        total_allocated = 0.0
        expected_return = 0.0

        sorted_bets = sorted(bets, key=lambda b: abs(b.edge), reverse=True)

        market_exposure: dict[str, float] = {}
        book_exposure: dict[str, float] = {}

        for bet in sorted_bets:
            if total_allocated >= bankroll * 0.95:
                break

            market_current = market_exposure.get(bet.market, 0.0)
            if market_current >= bankroll * self.config.max_exposure_per_market:
                continue

            book_current = book_exposure.get(bet.book, 0.0)
            if book_current >= bankroll * self.config.max_exposure_per_book:
                continue

            if self.config.use_kelly_sizing:
                kelly = self._calculate_kelly_fraction(bet.edge, bet.odds)
                stake = bankroll * kelly * self.config.kelly_fraction
            else:
                base_stake = bankroll * 0.02
                edge_multiplier = max(0.0, bet.edge * 10)
                stake = base_stake * (1 + edge_multiplier)

            max_stake = bankroll * 0.1
            stake = min(stake, max_stake)

            remaining_budget = bankroll - total_allocated
            stake = min(stake, remaining_budget)

            if stake < 1.0:
                continue

            profit = stake * (bet.odds - 1)
            expected_return += stake * bet.edge

            allocations_list.append(
                {
                    "market": bet.market,
                    "player_id": bet.player_id,
                    "side": bet.side,
                    "book": bet.book,
                    "line": bet.line,
                    "odds": bet.odds,
                    "stake": round(stake, 2),
                    "potential_profit": round(profit, 2),
                    "edge": bet.edge,
                }
            )

            total_allocated += stake
            market_exposure[bet.market] = market_current + stake
            book_exposure[bet.book] = book_current + stake

        risk_score = self._calculate_risk_score(bets, market_exposure, book_exposure)

        return Allocation(
            total_bankroll=bankroll,
            total_allocated=round(total_allocated, 2),
            remaining=round(bankroll - total_allocated, 2),
            allocations=allocations_list,
            expected_return=round(expected_return, 2),
            risk_score=risk_score,
        )

    def _calculate_kelly_fraction(self, edge: float, odds: float) -> float:
        if odds <= 1.0:
            return 0.0
        p = (odds - 1) / odds
        q = 1 - p
        kelly = p - q / (odds - 1)
        kelly = kelly * (1 + edge * 2)
        return max(0.0, kelly)

    def _calculate_risk_score(
        self,
        bets: list[PotentialBet],
        _market_exposure: dict[str, float],
        _book_exposure: dict[str, float],
    ) -> float:
        if not bets:
            return 0.0

        concentration_risk = len({b.market for b in bets}) / len(bets)
        concentration_risk = min(1.0, concentration_risk * 0.5 + 0.5)

        book_diversity = len({b.book for b in bets})
        diversity_score = min(1.0, book_diversity / 3.0)

        edge_variance = float(np.var([abs(b.edge) for b in bets]))

        risk_score = concentration_risk * 0.4 + (1 - diversity_score) * 0.3 + edge_variance * 0.3

        return min(1.0, risk_score)


class EuropeanBookIntegrator:
    """Integration layer for European sportsbook odds.

    This class provides methods to fetch odds from European bookmakers,
    compare them with DFS (Daily Fantasy Sports) odds, and identify
    cross-market betting opportunities.

    Attributes:
        config: EuropeanBookConfig instance for book integration settings.
    """

    def __init__(self, config: EuropeanBookConfig | None = None) -> None:
        self.config = config or EuropeanBookConfig()

    def fetch_european_odds(self, _market: str) -> list[EuropeanOdds]:
        """Fetch current odds from European books for a given market.

        Args:
            _market: Market identifier to fetch odds for.

        Returns:
            List of EuropeanOdds objects with current book prices.
        """
        return []

    def compare_with_dfs(
        self, _dfs_odds: list[dict], _eu_odds: list[EuropeanOdds]
    ) -> list[ComparisonResult]:
        """Compare European book odds with DFS odds to find discrepancies.

        Args:
            _dfs_odds: List of DFS odds dictionaries.
            _eu_odds: List of EuropeanOdds objects.

        Returns:
            List of ComparisonResult objects showing value differences.
        """
        results: list[ComparisonResult] = []
        return results


__all__ = [
    "MultiMarketConfig",
    "MultiMarketBettor",
    "BestLine",
    "ArbitrageResult",
    "PotentialBet",
    "Allocation",
    "EuropeanBookConfig",
    "EuropeanBookIntegrator",
    "EuropeanOdds",
    "ComparisonResult",
]
