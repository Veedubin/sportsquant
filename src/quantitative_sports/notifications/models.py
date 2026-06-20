"""Discord Top Insights canonical data models.

This module defines the canonical data model for Discord webhook insights,
aligned to the spec in discord_webhook_top_insights_spec.md.

Also includes alert models for the notification pipeline (EV, line movement,
injury, and summary alerts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional


# ---------------------------------------------------------------------------
# Discord Insight Models (from sports-analytics)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Team:
    """Team information for matchup display."""

    team_id: str
    name: str
    short_name: str
    abbr: str
    logo_url: str | None = None
    primary_color_hex: str = "#0B1320"
    secondary_color_hex: str = "#000000"

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "short_name": self.short_name,
            "abbr": self.abbr,
            "logo_url": self.logo_url,
            "primary_color_hex": self.primary_color_hex,
            "secondary_color_hex": self.secondary_color_hex,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Team:
        return cls(
            team_id=data.get("team_id", ""),
            name=data.get("name", ""),
            short_name=data.get("short_name", ""),
            abbr=data.get("abbr", ""),
            logo_url=data.get("logo_url"),
            primary_color_hex=data.get("primary_color_hex", "#0B1320"),
            secondary_color_hex=data.get("secondary_color_hex", "#000000"),
        )


@dataclass(frozen=True)
class HeroCard:
    """Hero card configuration for matchup display."""

    title: str
    subtitle: str = "Trending Insights"
    background_theme: str = "teal_plum_gradient"
    image_url: str | None = None
    image_asset_key: str = "matchup_card.png"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "background_theme": self.background_theme,
            "image_url": self.image_url,
            "image_asset_key": self.image_asset_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HeroCard:
        return cls(
            title=data.get("title", ""),
            subtitle=data.get("subtitle", "Trending Insights"),
            background_theme=data.get("background_theme", "teal_plum_gradient"),
            image_url=data.get("image_url"),
            image_asset_key=data.get("image_asset_key", "matchup_card.png"),
        )


@dataclass(frozen=True)
class Event:
    """Game/event information for insights."""

    event_id: str
    start_time_utc: str
    display_time_local: str
    away_team: Team
    home_team: Team
    venue: str = ""
    status: str = "scheduled"
    deeplink_url: str = ""
    hero_card: HeroCard | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "start_time_utc": self.start_time_utc,
            "display_time_local": self.display_time_local,
            "away_team": self.away_team.to_dict(),
            "home_team": self.home_team.to_dict(),
            "venue": self.venue,
            "status": self.status,
            "deeplink_url": self.deeplink_url,
            "hero_card": self.hero_card.to_dict() if self.hero_card else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        hero_data = data.get("hero_card")
        hero_card = HeroCard.from_dict(hero_data) if hero_data else None

        away_team = Team.from_dict(data.get("away_team", {}))
        home_team = Team.from_dict(data.get("home_team", {}))

        return cls(
            event_id=data.get("event_id", ""),
            start_time_utc=data.get("start_time_utc", ""),
            display_time_local=data.get("display_time_local", ""),
            away_team=away_team,
            home_team=home_team,
            venue=data.get("venue", ""),
            status=data.get("status", "scheduled"),
            deeplink_url=data.get("deeplink_url", ""),
            hero_card=hero_card,
        )


@dataclass(frozen=True)
class BookPrice:
    """Sportsbook odds for a pick."""

    book_key: str
    book_name: str
    book_emoji: str = ""
    american_odds: int = 0
    decimal_odds: float = 1.0
    last_updated_utc: str = ""
    book_line: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_key": self.book_key,
            "book_name": self.book_name,
            "book_emoji": self.book_emoji,
            "american_odds": self.american_odds,
            "decimal_odds": self.decimal_odds,
            "last_updated_utc": self.last_updated_utc,
            "book_line": self.book_line,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BookPrice:
        return cls(
            book_key=data.get("book_key", ""),
            book_name=data.get("book_name", ""),
            book_emoji=data.get("book_emoji", ""),
            american_odds=data.get("american_odds", 0),
            decimal_odds=data.get("decimal_odds", 1.0),
            last_updated_utc=data.get("last_updated_utc", ""),
            book_line=data.get("book_line", 0.0),
        )


@dataclass(frozen=True)
class Pick:
    """The actual bet pick."""

    market_key: str
    market_label: str
    subject_type: Literal["player", "team"]
    subject_name: str
    side: Literal["over", "under", "home", "away", "yes", "no"]
    line: float
    unit: str = "count"
    period: str = "game"

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_key": self.market_key,
            "market_label": self.market_label,
            "subject_type": self.subject_type,
            "subject_name": self.subject_name,
            "side": self.side,
            "line": self.line,
            "unit": self.unit,
            "period": self.period,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pick:
        return cls(
            market_key=data.get("market_key", ""),
            market_label=data.get("market_label", ""),
            subject_type=data.get("subject_type", "player"),
            subject_name=data.get("subject_name", ""),
            side=data.get("side", "over"),
            line=data.get("line", 0.0),
            unit=data.get("unit", "count"),
            period=data.get("period", "game"),
        )


@dataclass(frozen=True)
class Confidence:
    """Confidence scoring for an insight."""

    model: str = "hit_rate_v1"
    score_0_to_1: float = 0.0
    sample_size: int = 0
    hit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "score_0_to_1": self.score_0_to_1,
            "sample_size": self.sample_size,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Confidence:
        return cls(
            model=data.get("model", "hit_rate_v1"),
            score_0_to_1=data.get("score_0_to_1", 0.0),
            sample_size=data.get("sample_size", 0),
            hit_count=data.get("hit_count", 0),
        )


@dataclass(frozen=True)
class Insight:
    """A single insight with pick, odds, and confidence."""

    insight_id: str
    rank: int = 0
    category: str = "player_prop_trend"
    statement: str = ""
    pick: Pick | None = None
    pricing: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence | None = None
    context_tags: list[str] = field(default_factory=list)
    deeplink_add_to_betslip_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "rank": self.rank,
            "category": self.category,
            "statement": self.statement,
            "pick": self.pick.to_dict() if self.pick else None,
            "pricing": self.pricing,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "context_tags": self.context_tags,
            "deeplink_add_to_betslip_url": self.deeplink_add_to_betslip_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Insight:
        pick_data = data.get("pick")
        pick = Pick.from_dict(pick_data) if pick_data else None

        confidence_data = data.get("confidence")
        confidence = Confidence.from_dict(confidence_data) if confidence_data else None

        return cls(
            insight_id=data.get("insight_id", ""),
            rank=data.get("rank", 0),
            category=data.get("category", "player_prop_trend"),
            statement=data.get("statement", ""),
            pick=pick,
            pricing=data.get("pricing", {}),
            confidence=confidence,
            context_tags=data.get("context_tags", []),
            deeplink_add_to_betslip_url=data.get("deeplink_add_to_betslip_url", ""),
        )


@dataclass(frozen=True)
class Presentation:
    """Branding and presentation settings."""

    brand_name: str = "Quant-Sports"
    brand_icon_url: str = ""
    accent_color_decimal: int = 4886754
    hero_description: str = "Top insights for matchup"
    footer_text: str = "Trending Insights"

    def to_dict(self) -> dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "brand_icon_url": self.brand_icon_url,
            "accent_color_decimal": self.accent_color_decimal,
            "hero_description": self.hero_description,
            "footer_text": self.footer_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Presentation:
        return cls(
            brand_name=data.get("brand_name", "Quant-Sports"),
            brand_icon_url=data.get("brand_icon_url", ""),
            accent_color_decimal=data.get("accent_color_decimal", 4886754),
            hero_description=data.get("hero_description", "Top insights for matchup"),
            footer_text=data.get("footer_text", "Trending Insights"),
        )


@dataclass(frozen=True)
class InsightFeed:
    """Root canonical model for Discord Top Insights."""

    schema_version: str = "1.0"
    generated_at: str = ""
    league: str = ""
    event: Event | None = None
    insights: list[Insight] = field(default_factory=list)
    presentation: Presentation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "league": self.league,
            "event": self.event.to_dict() if self.event else None,
            "insights": [insight.to_dict() for insight in self.insights],
            "presentation": self.presentation.to_dict() if self.presentation else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InsightFeed:
        event_data = data.get("event")
        event = Event.from_dict(event_data) if event_data else None

        presentation_data = data.get("presentation")
        presentation = Presentation.from_dict(presentation_data) if presentation_data else None

        insights = [Insight.from_dict(insight) for insight in data.get("insights", [])]

        return cls(
            schema_version=data.get("schema_version", "1.0"),
            generated_at=data.get("generated_at", ""),
            league=data.get("league", ""),
            event=event,
            insights=insights,
            presentation=presentation,
        )

    @classmethod
    def from_json(cls, json_str: str) -> InsightFeed:
        """Load from JSON string."""
        import json

        data = json.loads(json_str)
        return cls.from_dict(data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def load(cls, path: str) -> InsightFeed:
        """Load from JSON file."""
        with open(path, "r") as f:
            return cls.from_json(f.read())

    def save(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, "w") as f:
            f.write(self.to_json())


# ---------------------------------------------------------------------------
# Alert Models (from sports-bet)
# ---------------------------------------------------------------------------


class AlertType(str, Enum):
    """Types of alerts."""

    EV = "ev"
    LINE_MOVEMENT = "line_movement"
    INJURY = "injury"
    SUMMARY = "summary"


@dataclass
class Alert:
    """Base alert."""

    id: str
    alert_type: AlertType = None  # type: ignore[assignment]
    created_at: datetime = field(default_factory=datetime.now)
    site: str = ""
    player_name: str = ""
    stat_type: str = ""
    line: float = 0.0
    message: str = ""
    severity: str = "info"  # info, warning, critical
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "created_at": self.created_at.isoformat(),
            "site": self.site,
            "player_name": self.player_name,
            "stat_type": self.stat_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass
class EVAlert(Alert):
    """+EV opportunity alert."""

    edge: float = 0.0
    confidence: float = 0.0
    recommended_side: str = ""  # Over/Under or Higher/Lower
    market_prob: float = 0.0
    fair_prob: float = 0.0
    payout_multiplier: float = 1.0
    stake: Optional[float] = None

    def __post_init__(self):
        self.alert_type = AlertType.EV
        self.severity = (
            "critical" if self.edge >= 0.05 else "warning" if self.edge >= 0.03 else "info"
        )

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "edge": self.edge,
                "confidence": self.confidence,
                "recommended_side": self.recommended_side,
                "market_prob": self.market_prob,
                "fair_prob": self.fair_prob,
                "payout_multiplier": self.payout_multiplier,
                "stake": self.stake,
            }
        )
        return base


@dataclass
class LineMovementAlert(Alert):
    """Line movement alert."""

    previous_line: float = 0.0
    new_line: float = 0.0
    movement: float = 0.0  # positive = moved in favorable direction
    direction: str = ""  # "up" or "down"
    market_source: str = ""

    def __post_init__(self):
        self.alert_type = AlertType.LINE_MOVEMENT
        self.line = self.new_line
        self.movement = self.new_line - self.previous_line
        self.direction = "up" if self.movement > 0 else "down"

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "previous_line": self.previous_line,
                "new_line": self.new_line,
                "movement": self.movement,
                "direction": self.direction,
                "market_source": self.market_source,
            }
        )
        return base


@dataclass
class InjuryAlert(Alert):
    """Injury alert affecting props."""

    team: str = ""
    player_status: str = ""  # out, doubtful, questionable, probable
    affected_props: list[str] = field(default_factory=list)
    impact: str = ""  # high, medium, low

    def __post_init__(self):
        self.alert_type = AlertType.INJURY
        self.severity = (
            "critical"
            if self.player_status in ("out", "doubtful")
            else "warning"
            if self.player_status == "questionable"
            else "info"
        )

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "team": self.team,
                "player_status": self.player_status,
                "affected_props": self.affected_props,
                "impact": self.impact,
            }
        )
        return base


@dataclass
class SummaryAlert(Alert):
    """Daily summary alert."""

    total_opportunities: int = 0
    top_plays: list[dict] = field(default_factory=list)
    ev_breakdown: dict = field(default_factory=dict)
    sport: str = "NBA"

    def __post_init__(self):
        self.alert_type = AlertType.SUMMARY

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "total_opportunities": self.total_opportunities,
                "top_plays": self.top_plays,
                "ev_breakdown": self.ev_breakdown,
                "sport": self.sport,
            }
        )
        return base


# ---------------------------------------------------------------------------
# Discord Embed / Notification Models (from Sports-Platform)
# ---------------------------------------------------------------------------


class NotificationType(Enum):
    """Types of notifications."""

    UA_POOL_UPDATE = "ua_pool_update"
    SCRAPER_START = "scraper_start"
    SCRAPER_COMPLETE = "scraper_complete"
    SCRAPER_ERROR = "scraper_error"
    ODDS_UPDATE = "odds_update"
    SYSTEM_ALERT = "system_alert"
    BET_PLACED = "bet_placed"
    STEAM_MOVE = "steam_move"
    PREDICTION_READY = "prediction_ready"


@dataclass
class DiscordEmbed:
    """Discord embed for rich notifications."""

    title: str
    description: str
    color: int = 0x00FF00
    fields: list[dict[str, object]] = field(default_factory=list)
    footer: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    media: dict[str, str] = field(default_factory=dict)


@dataclass
class BetNotificationData:
    """Data class for bet notification parameters."""

    player_name: str
    market: str
    line: float
    side: str
    stake: float
    odds: float
    edge: float


@dataclass
class SteamNotificationData:
    """Data class for steam move notification parameters."""

    player_name: str
    market: str
    old_line: float
    new_line: float
    direction: str
    movement_pct: float
