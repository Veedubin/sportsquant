"""Alert formatter for different notification channels."""

from quantitative_sports.notifications.models import (
    Alert,
    EVAlert,
    LineMovementAlert,
    InjuryAlert,
    SummaryAlert,
)


class AlertFormatter:
    """Format alerts for different notification channels."""

    @staticmethod
    def format_ev_alert(alert: EVAlert, channel: str = "discord") -> str:
        """Format +EV alert."""
        edge_pct = alert.edge * 100
        conf_pct = alert.confidence
        side_emoji = "📈" if alert.recommended_side == "Over" else "📉"
        severity_emoji = "🚨" if alert.severity == "critical" else "⚠️"

        if channel == "discord":
            return f"""**{severity_emoji} +EV Alert**

**{alert.site}:** {alert.player_name} {side_emoji} {alert.recommended_side} {alert.line} {alert.stat_type}
**Edge:** +{edge_pct:.1f}% | **Confidence:** {conf_pct:.0f}%
**Market Prob:** {alert.market_prob * 100:.1f}% → **Fair Prob:** {alert.fair_prob * 100:.1f}%
**Payout:** {alert.payout_multiplier:.2f}x"""
        elif channel == "slack":
            return f""":rotating_light: *+EV Alert*

*{alert.site}:* {alert.player_name} {alert.recommended_side} {alert.line} {alert.stat_type}
*Edge:* +{edge_pct:.1f}% | *Confidence:* {conf_pct:.0f}%
*Market:* {alert.market_prob * 100:.1f}% → *Fair:* {alert.fair_prob * 100:.1f}%
_Payout: {alert.payout_multiplier:.2f}x_"""
        elif channel == "email":
            return f"""+EV Alert

{alert.player_name} - {alert.recommended_side} {alert.line} {alert.stat_type}
Edge: +{edge_pct:.1f}% | Confidence: {conf_pct:.0f}%
Market: {alert.market_prob * 100:.1f}% → Fair: {alert.fair_prob * 100:.1f}%
Site: {alert.site} | Payout: {alert.payout_multiplier:.2f}x"""
        else:
            return f"[+EV] {alert.player_name} {alert.recommended_side} {alert.line} {alert.stat_type} - Edge: +{edge_pct:.1f}%"

    @staticmethod
    def format_line_movement_alert(alert: LineMovementAlert, channel: str = "discord") -> str:
        """Format line movement alert."""
        movement_abs = abs(alert.movement)
        direction_emoji = "📈" if alert.direction == "up" else "📉"

        if alert.movement > 0:
            direction_text = "moved UP (favorable)"
        else:
            direction_text = "moved DOWN (unfavorable)"

        if channel == "discord":
            return f"""**{direction_emoji} Line Movement**

**{alert.site}:** {alert.player_name} {alert.stat_type}
**Line:** {alert.previous_line} → **{alert.new_line}** ({direction_text})
**Movement:** {movement_abs:.1f} points
**Source:** {alert.market_source}"""
        elif channel == "slack":
            return f""":chart_with_upwards_trend: *Line Movement*

*{alert.site}:* {alert.player_name} {alert.stat_type}
_Line: {alert.previous_line} → *{alert.new_line}* ({direction_text})
Movement: {movement_abs:.1f} points | Source: {alert.market_source}_"""
        elif channel == "email":
            return f"""Line Movement Alert

{alert.player_name} - {alert.stat_type}
Line: {alert.previous_line} → {alert.new_line} ({direction_text})
Movement: {movement_abs:.1f} points | Source: {alert.market_source}
Site: {alert.site}"""
        else:
            return f"[Line Move] {alert.player_name} {alert.stat_type}: {alert.previous_line} → {alert.new_line}"

    @staticmethod
    def format_injury_alert(alert: InjuryAlert, channel: str = "discord") -> str:
        """Format injury alert."""
        status_emoji = {
            "out": "❌",
            "doubtful": "⚠️",
            "questionable": "❓",
            "probable": "✅",
        }.get(alert.player_status, "🏥")

        impact_text = {
            "high": "HIGH IMPACT",
            "medium": "MEDIUM IMPACT",
            "low": "LOW IMPACT",
        }.get(alert.impact, "")

        if channel == "discord":
            props_str = ", ".join(alert.affected_props) if alert.affected_props else "N/A"
            return f"""**{status_emoji} Injury Alert**

**{alert.team}:** {alert.player_name}
**Status:** {alert.player_status.upper()} {status_emoji}
**Impact:** {impact_text}
**Affected Props:** {props_str}"""
        elif channel == "slack":
            props_str = ", ".join(alert.affected_props) if alert.affected_props else "N/A"
            return f""":ambulance: *Injury Alert*

*{alert.team}:* {alert.player_name}
_Status: {alert.player_status.upper()}_
*Impact:* {impact_text}
_Affected Props: {props_str}_"""
        elif channel == "email":
            props_str = ", ".join(alert.affected_props) if alert.affected_props else "N/A"
            return f"""Injury Alert

{alert.player_name} - {alert.team}
Status: {alert.player_status.upper()}
Impact: {impact_text}
Affected Props: {props_str}"""
        else:
            return f"[Injury] {alert.player_name} ({alert.team}): {alert.player_status}"

    @staticmethod
    def format_summary_alert(alert: SummaryAlert, channel: str = "discord") -> str:
        """Format daily summary alert."""
        if channel == "discord":
            top_plays_text = ""
            if alert.top_plays:
                lines = []
                for i, play in enumerate(alert.top_plays[:5], 1):
                    lines.append(
                        f"  {i}. {play.get('player', 'N/A')} {play.get('side', '')} "
                        f"{play.get('line', '')} - Edge: +{play.get('edge', 0):.1f}%"
                    )
                top_plays_text = "\n" + "\n".join(lines)

            ev_text = ""
            if alert.ev_breakdown:
                ev_text = "\n".join(
                    [f"  {site}: {count} plays" for site, count in alert.ev_breakdown.items()]
                )

            return f"""**📊 Daily Summary - {alert.sport}**

**Total Opportunities:** {alert.total_opportunities}
**Top Plays:**{top_plays_text}
**EV Breakdown:**{ev_text}
**Time:** {alert.created_at.strftime("%Y-%m-%d %H:%M")}"""
        elif channel == "slack":
            top_plays_text = ""
            if alert.top_plays:
                lines = []
                for i, play in enumerate(alert.top_plays[:5], 1):
                    lines.append(
                        f"  {i}. {play.get('player', 'N/A')} {play.get('side', '')} "
                        f"{play.get('line', '')} - Edge: +{play.get('edge', 0):.1f}%"
                    )
                top_plays_text = "\n" + "\n".join(lines)

            return f""":bar_chart: *Daily Summary - {alert.sport}*

*Total Opportunities:* {alert.total_opportunities}
*Top Plays:*{top_plays_text}
_Time: {alert.created_at.strftime("%Y-%m-%d %H:%M")}_"""
        elif channel == "email":
            top_plays_text = ""
            if alert.top_plays:
                lines = []
                for i, play in enumerate(alert.top_plays[:5], 1):
                    lines.append(
                        f"{i}. {play.get('player', 'N/A')} {play.get('side', '')} "
                        f"{play.get('line', '')} - Edge: +{play.get('edge', 0):.1f}%"
                    )
                top_plays_text = "\n".join(lines)

            return f"""Daily Summary - {alert.sport}

Total Opportunities: {alert.total_opportunities}

Top Plays:
{top_plays_text}

Time: {alert.created_at.strftime("%Y-%m-%d %H:%M")}"""
        else:
            return f"[Summary] {alert.total_opportunities} opportunities found"

    @classmethod
    def format(cls, alert: Alert, channel: str = "discord") -> str:
        """Format an alert for a specific channel."""
        if isinstance(alert, EVAlert):
            return cls.format_ev_alert(alert, channel)
        elif isinstance(alert, LineMovementAlert):
            return cls.format_line_movement_alert(alert, channel)
        elif isinstance(alert, InjuryAlert):
            return cls.format_injury_alert(alert, channel)
        elif isinstance(alert, SummaryAlert):
            return cls.format_summary_alert(alert, channel)
        else:
            return alert.message
