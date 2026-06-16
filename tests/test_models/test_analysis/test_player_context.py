"""Test script for player context enrichment functionality (migrated from sports-bet)."""

import json

from sportsquant.models.analysis.player_context import get_context_for_prop


def test_context():
    """Test context enrichment for player props."""

    test_cases = [
        {
            "id": "prop001",
            "site": "prizepicks",
            "player_name": "Luka Doncic",
            "player_team": "DAL",
            "stat_type": "Points",
            "matchup": "DAL @ OKC",
        },
        {
            "id": "prop002",
            "site": "prizepicks",
            "player_name": "LeBron James",
            "player_team": "LAL",
            "stat_type": "Points",
            "matchup": "LAL vs BOS",
        },
        {
            "id": "prop003",
            "site": "prizepicks",
            "player_name": "Jayson Tatum",
            "player_team": "BOS",
            "stat_type": "Rebounds",
            "matchup": "BOS @ LAL",
        },
    ]

    print("=" * 60)
    print("PLAYER CONTEXT ENRICHMENT TEST")
    print("=" * 60)

    for prop in test_cases:
        print(f"\n{prop['player_name']} - {prop['stat_type']}")
        print("-" * 40)

        context = get_context_for_prop(prop)

        # Display key context fields
        print(
            f"  Matchup Avg: {context.get('matchup_avg') or 'N/A'} (vs {prop['matchup'].split(' @ ')[-1]})"
        )
        print(f"  Matchup Games: {context.get('matchup_games', 0)}")
        print(f"  Last 5: {context.get('last_5', [])}")
        print(f"  Trend: {context.get('trend') or 'N/A'}")
        print(f"  Trend Avg: {context.get('trend_avg') or 'N/A'}")
        print(f"  Rest Days: {context.get('rest_days') or 'N/A'}")
        print(f"  Rest Impact: {context.get('rest_impact') or 'N/A'}")
        print(f"  Defense Rank: {context.get('defense_rank') or 'N/A'}")
        print(f"  Defense Note: {context.get('defense_note') or 'N/A'}")
        print(f"  Home Avg: {context.get('home_avg') or 'N/A'}")
        print(f"  Away Avg: {context.get('away_avg') or 'N/A'}")

        # Show what the API would return
        print("\n  Full JSON context:")
        print(json.dumps(context, indent=4))

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_context()
