# Unified Poller API Fallback Strategy

**Document Version:** 1.0  
**Date:** January 2026  
**Status:** Technical Specification & Implementation Guide

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Status Matrix](#2-current-status-matrix)
3. [Direct API Implementations](#3-direct-api-implementations)
4. [Selenium Fallback Implementations](#4-selenium-fallback-implementations)
5. [Implementation Guidelines](#5-implementation-guidelines)
6. [Testing Requirements](#6-testing-requirements)
7. [Related Files](#7-related-files)
8. [TODO: Implementation Plan](#8-todo-implementation-plan)

---

## 1. Executive Summary

This document describes the API fallback strategy for the Unified Poller, a CDMA-style coordinated polling system that handles data collection for multiple sports leagues (NBA, NFL, NHL, MLB, F1) from a single container instance.

The fallback strategy ensures data collection resilience when direct API calls fail due to:
- HTTP errors (403 Forbidden, 429 Rate Limited, 500 Server Error)
- Network timeouts or connectivity issues
- API endpoint changes or deprecation

Each league follows a tiered approach:
1. **Tier 1**: Direct API call (preferred, fastest)
2. **Tier 2**: Selenium browser scraping (fallback, slower)
3. **Tier 3**: Error response (graceful degradation)

---

## 2. Current Status Matrix

| League | Direct API | Selenium Fallback | Priority | Status |
|--------|------------|-------------------|----------|--------|
| **NBA** | ✅ stats.nba.com | ✅ Implemented | Done | Production |
| **NHL** | ✅ api-web.nhle.com | ❌ Not implemented | High | Pending |
| **MLB** | ✅ statsapi.mlb.com | ❌ Not implemented | High | Pending |
| **NFL** | ❌ No free API | ❌ Not implemented | Medium | Research |
| **F1** | ❌ No free API | ❌ Not implemented | Low | Research |

### Legend

- ✅ **Implemented**: Feature is complete and tested
- ❌ **Not implemented**: Feature needs to be developed
- ✅🔄 **Partial**: Feature exists but needs improvement
- **Priority**: Development priority (Done, High, Medium, Low)
- **Status**: Current development state

---

## 3. Direct API Implementations

### 3.1 NBA (National Basketball Association)

**Status**: ✅ Production Ready  
**Reference**: [`src/datasource/nba_stats/client.py`](src/datasource/nba_stats/client.py)

#### Endpoint Details

| Component | Value |
|-----------|-------|
| **Base URL** | `https://stats.nba.com/stats` |
| **Schedule Endpoint** | `/schedule` |
| **Scoreboard Endpoint** | `/scoreboard` |
| **Player Stats Endpoint** | `/playerstats` |

#### Required Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "x-nba-stats-token": "true",
}
```

#### Required Parameters (Schedule)

```python
params = {
    "LeagueID": "00",
    "Season": "2025-26",
    "DateFrom": "2026-01-26",
    "DateTo": "2026-01-26",
}
```

#### Response Format

```json
{
  "resultSets": [
    {
      "name": "Schedule",
      "headers": ["GAME_ID", "GAME_DATE", "GAME_TIME", "HOME_TEAM_ID", "HOME_TEAM_ABBREVIATION", "AWAY_TEAM_ID", "AWAY_TEAM_ABBREVIATION", "VENUE", "GAME_STATUS"],
      "rowSet": [
        ["0022400001", "2026-01-26", "19:00:00", "1610612747", "LAL", "1610612748", "LAC", "Crypto.com Arena", "1"]
      ]
    }
  ]
}
```

#### Known Issues

- **Rate Limiting**: NBA API enforces strict rate limits (approx. 100 requests/minute)
- **403 Forbidden**: Missing or incorrect headers trigger immediate blocking
- **Session-Based Auth**: Some endpoints require active session cookies

#### Rate Limit Handling

```python
# From src/unified_poller/async_io_pool.py
class TokenBucketRateLimiter:
    def __init__(self, rate: float, max_tokens: int):
        self.rate = rate  # tokens per second
        self.capacity = max_tokens
```

---

### 3.2 NHL (National Hockey League)

**Status**: ✅ Direct API Working - Selenium Fallback Needed  
**Reference**: [`nhl_ingest/__main__.py`](nhl_ingest/__main__.py)

#### Endpoint Details

| Component | Value |
|-----------|-------|
| **Base URL** | `https://api-web.nhle.com/v1` |
| **Schedule Endpoint** | `/schedule` |
| **Scores Endpoint** | `/schedule` (same as schedule) |

#### Required Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
```

#### Required Parameters (Schedule)

```python
params = {
    "startDate": "2026-01-26",
    "endDate": "2026-01-26",
}
```

#### Response Format

```json
{
  "dayOffset": 0,
  "gameWeek": ["2026-01-26"],
  "gamePk": ["2024021001"],
  "dates": [
    {
      "date": "2026-01-26",
      "totalGames": 1,
      "games": [
        {
          "id": "2024021001",
          "season": "20242025",
          "gameType": "R",
          "status": {
            "statusCode": "1",
            "detailedState": "Scheduled"
          },
          "homeTeam": {
            "id": 10,
            "abbrev": "EDM",
            "name": "Edmonton Oilers"
          },
          "awayTeam": {
            "id": 12,
            "abbrev": "CGY",
            "name": "Calgary Flames"
          },
          "venue": {
            "default": "Rogers Place"
          },
          "startTimeUTC": "2026-01-26T02:00:00Z",
          "easternUTCOffset": "-05:00"
        }
      ]
    }
  ]
}
```

#### Known Issues

- **Timezone Handling**: Times are in UTC, require conversion
- **Game Types**: Regular season (R), Playoffs (P), Preseason (PR)
- **Season Format**: Season uses combined format (e.g., 20242025 for 2024-25)

---

### 3.3 MLB (Major League Baseball)

**Status**: ✅ Direct API Working - Selenium Fallback Needed  
**Reference**: [`mlb_ingest/__main__.py`](mlb_ingest/__main__.py)

#### Endpoint Details

| Component | Value |
|-----------|-------|
| **Base URL** | `https://statsapi.mlb.com/api/v1` |
| **Schedule Endpoint** | `/schedule` |
| **Game Details Endpoint** | `/game/{gamePk}/boxscore` |

#### Required Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
```

#### Required Parameters (Schedule)

```python
params = {
    "date": "2026-01-26",
    "sportId": "1",  # 1 = MLB
    "teamId": "",    # Optional, filters by team
}
```

#### Response Format

```json
{
  "dates": [
    {
      "date": "2026-01-26",
      "totalGames": 1,
      "games": [
        {
          "gamePk": 746999,
          "link": "/api/v1.1/game/746999/boxscore",
          "gameType": "R",
          "season": "2025",
          "gameDate": "2026-01-26T18:05:00Z",
          "status": {
            "abstractGameState": "Preview",
            "codedGameState": "1",
            "detailedState": "Scheduled"
          },
          "teams": {
            "home": {
              "id": 121,
              "name": "New York Mets",
              "abbreviation": "NYM"
            },
            "away": {
              "id": 112,
              "name": "Chicago Cubs",
              "abbreviation": "CHC"
            }
          },
          "venue": {
            "id": 17,
            "name": "Citi Field"
          }
        }
      ]
    }
  ],
  "totalEvents": 0,
  "totalGames": 1
}
```

#### Known Issues

- **Season Timing**: MLB season runs March-October (limited data in off-season)
- **Spring Training**: Uses sportId=14 instead of 1
- **International Games**: May have different gameType codes

---

### 3.4 NFL (National Football League)

**Status**: ❌ No Free API Available  
**Reference**: [`docs/market-research/nfl-market-research.md`](docs/market-research/nfl-market-research.md)

#### Current Status

The NFL does not provide a free public API. The official statistics require partnership arrangements or commercial licensing.

#### Available Data Sources

| Source | Type | Cost | Access Method |
|--------|------|------|---------------|
| **nflverse** | Play-by-play data | Free | GitHub releases (nightly) |
| **Pro-Football-Reference** | Historical stats | Free | Web scraping |
| **NFL.com** | Official stats | Partner only | API access requires approval |

#### Recommended Fallback Strategy

For NFL, browser scraping of Pro-Football-Reference or ESPN is the recommended fallback:

- **Target URL**: `https://www.pro-football-reference.com/years/2025/games.htm`
- **Selector Pattern**: `.game_summary tbody tr`
- **Data Points**: Date, time, team names, final score

---

### 3.5 F1 (Formula 1)

**Status**: ❌ No Free API Available  
**Reference**: [`docs/market-research/f1-market-research.md`](docs/market-research/f1-market-research.md), [`f1_ingest/__main__.py`](f1_ingest/__main__.py)

#### Current Status

F1 has no free official API. The best options are:

| Source | Type | Cost | Update Frequency |
|--------|------|------|------------------|
| **OpenF1** | Telemetry data | Free (non-commercial) | Real-time during sessions |
| **FastF1 Library** | Analysis library | Free | Per session |
| **Jolpica-f1** | Historical database | Free | Per season |

#### Recommended Fallback Strategy

For F1, browser scraping of official F1 website or using FastF1 library:

- **Target URL**: `https://www.formula1.com/en/racing/2025.html`
- **Selector Pattern**: `.race-info .session-info`
- **Data Points**: Race date, time, circuit name, session status

---

## 4. Selenium Fallback Implementations

### 4.1 NBA Selenium Fallback (Reference Implementation)

**Status**: ✅ Implemented  
**Reference**: [`src/datasource/nba_stats/schedule.py`](src/datasource/nba_stats/schedule.py)

#### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NBA Selenium Fallback Architecture                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    NBAScheduleFetcher                            │   │
│  │  - Wraps NBAStatsBrowser for headless scraping                   │   │
│  │  - Fetches schedule from NBA Stats API via browser               │   │
│  │  - Publishes to Kafka topic                                     │   │
│  └───────────────────────────────────┬─────────────────────────────┘   │
│                                      │                                   │
│                                      ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    NBAStatsBrowser                               │   │
│  │  - Playwright wrapper for browser automation                    │   │
│  │  - Handles rate limiting and retries                            │   │
│  │  - Sets NBA-specific headers to bypass blocking                 │   │
│  └───────────────────────────────────┬─────────────────────────────┘   │
│                                      │                                   │
│                                      ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Browser Context                               │   │
│  │  - Headless Chromium browser                                    │   │
│  │  - Custom user agent and headers                                │   │
│  │  - Rate limiting configuration                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Usage Example

```python
from src.datasource.nba_stats.browser import NBAStatsBrowser, RateLimitConfig
from src.datasource.nba_stats.schedule import NBAScheduleFetcher

# Configure rate limiting
rate_limit = RateLimitConfig(
    min_interval_s=1.0,
    max_retries=3,
    max_backoff_s=10.0,
)

# Create browser context
with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
    fetcher = NBAScheduleFetcher(
        browser=browser,
        kafka_producer=mock_producer,  # For testing
        kafka_topic="nba-schedule",
        season="2025-26",
    )
    
    # Fetch today's schedule
    today = datetime.now().strftime("%Y-%m-%d")
    games = fetcher.fetch_schedule(date_from=today, date_to=today)
```

#### Response Format

The Selenium fallback returns data in this format:

```json
{
  "games": [
    {
      "GAME_ID": "0022400001",
      "GAME_DATE": "2026-01-26",
      "GAME_TIME": "19:00:00",
      "HOME_TEAM_ID": "1610612747",
      "HOME_TEAM_ABBREVIATION": "LAL",
      "AWAY_TEAM_ID": "1610612748",
      "AWAY_TEAM_ABBREVIATION": "LAC",
      "VENUE": "Crypto.com Arena",
      "GAME_STATUS": "1"
    }
  ],
  "fetched_via": "selenium"
}
```

### 4.2 NHL Selenium Fallback (To Be Implemented)

**Status**: ❌ Not Implemented  
**Priority**: High  
**Target File**: [`src/unified_poller/main.py`](src/unified_poller/main.py)

#### Target URL

```
https://www.nhl.com/schedule
```

#### Selector Patterns

```python
# Proposed selectors for NHL schedule data
SELECTORS = {
    "game_row": ".sidearm-list-group-item.game-summary",
    "date_header": ".sidearm-list-group-header h3",
    "team_home": ".team-home .team-name",
    "team_away": ".team-away .team-name",
    "game_time": ".game-time span",
    "game_status": ".game-status span",
    "venue": ".venue-link span",
}
```

#### Expected Response Format

```json
{
  "games": [
    {
      "game_id": "2024021001",
      "date": "2026-01-26",
      "time": "02:00:00Z",
      "home_team_id": 10,
      "home_team_abbrev": "EDM",
      "home_team_name": "Edmonton Oilers",
      "away_team_id": 12,
      "away_team_abbrev": "CGY",
      "away_team_name": "Calgary Flames",
      "venue": "Rogers Place",
      "status": "Scheduled"
    }
  ],
  "fetched_via": "selenium"
}
```

#### Error Handling Approach

```python
async def _execute_selenium_fallback_NHL(self, task: PollTask) -> "AsyncIOPool.APIResponse":
    """Execute NHL task using Selenium browser scraping as fallback."""
    try:
        from src.datasource.nhl_stats.schedule import NHLScheduleFetcher
        from src.datasource.nhl_stats.browser import NHLStatsBrowser
        
        logger.info(f"Using Selenium to fetch {task.league} schedule")
        
        # Create browser with NHL-specific configuration
        with NHLStatsBrowser(headless=True) as browser:
            fetcher = NHLScheduleFetcher(
                browser=browser,
                kafka_producer=MockProducer(),
                kafka_topic=f"{task.league.lower()}-schedule",
            )
            
            today = datetime.now().strftime("%Y-%m-%d")
            games = fetcher.fetch_schedule(date_from=today, date_to=today)
            
            return AsyncIOPool.APIResponse(
                success=True,
                data={"games": games, "fetched_via": "selenium"},
                error=None,
                latency_seconds=10.0,
                league=task.league,
                task_type=task.task_type.value,
                sport_key=task.sport_key,
            )
    
    except Exception as e:
        logger.error(f"NHL Selenium fallback failed: {e}")
        return AsyncIOPool.APIResponse(
            success=False,
            data=None,
            error=f"Selenium failed: {e}",
            latency_seconds=0,
            league=task.league,
            task_type=task.task_type.value,
            sport_key=task.sport_key,
        )
```

### 4.3 MLB Selenium Fallback (To Be Implemented)

**Status**: ❌ Not Implemented  
**Priority**: High  
**Target File**: [`src/unified_poller/main.py`](src/unified_poller/main.py)

#### Target URL

```
https://www.mlb.com/schedule?date=2026-01-26
```

#### Selector Patterns

```python
# Proposed selectors for MLB schedule data
SELECTORS = {
    "game_card": ".schedule-card",
    "game_date": ".date-badge .month",
    "game_team_home": ".team-home .team-name",
    "game_team_away": ".team-away .team-name",
    "game_time": ".game-time span",
    "game_status": ".game-status span",
    "game_venue": ".venue-link span",
}
```

#### Expected Response Format

```json
{
  "games": [
    {
      "game_pk": 746999,
      "date": "2026-01-26",
      "time": "18:05:00Z",
      "home_team_id": 121,
      "home_team_name": "New York Mets",
      "home_team_abbrev": "NYM",
      "away_team_id": 112,
      "away_team_name": "Chicago Cubs",
      "away_team_abbrev": "CHC",
      "venue": "Citi Field",
      "status": "Scheduled"
    }
  ],
  "fetched_via": "selenium"
}
```

### 4.4 NFL Selenium Fallback (Research Required)

**Status**: ❌ Not Implemented  
**Priority**: Medium  
**Target File**: [`src/unified_poller/main.py`](src/unified_poller/main.py)

#### Target URL

```
https://www.pro-football-reference.com/years/2025/games.htm
```

#### Selector Patterns

```python
# Proposed selectors for NFL schedule data
SELECTORS = {
    "game_row": "table#games tbody tr",
    "week_header": "table#games thead tr th",
    "team_home": ".home_team a",
    "team_away": ".away_team a",
    "score_home": ".home_score",
    "score_away": ".away_score",
    "game_time": ".game-time",
    "game_location": ".game-location",
}
```

#### Expected Response Format

```json
{
  "games": [
    {
      "game_id": "2025090800",
      "season": 2025,
      "week": 1,
      "date": "2025-09-08",
      "time": "20:20:00Z",
      "home_team_id": 22,
      "home_team_name": "Kansas City Chiefs",
      "home_team_abbrev": "KC",
      "away_team_id": 23,
      "away_team_name": "Houston Texans",
      "away_team_abbrev": "HOU",
      "venue": "GEHA Field at Arrowhead Stadium",
      "status": "Scheduled"
    }
  ],
  "fetched_via": "selenium"
}
```

### 4.5 F1 Selenium Fallback (Research Required)

**Status**: ❌ Not Implemented  
**Priority**: Low  
**Target File**: [`src/unified_poller/main.py`](src/unified_poller/main.py)

#### Target URL

```
https://www.formula1.com/en/racing/2025.html
```

#### Selector Patterns

```python
# Proposed selectors for F1 schedule data
SELECTORS = {
    "race_weekend": ".race-weekend",
    "event_name": ".event-name",
    "event_date": ".event-date",
    "event_time": ".event-time",
    "circuit_name": ".circuit-name",
    "session_info": ".session-info",
}
```

#### Expected Response Format

```json
{
  "events": [
    {
      "event_id": "2025-01",
      "event_name": "Australian Grand Prix",
      "date": "2025-03-16",
      "time": "05:00:00Z",
      "circuit": "Melbourne Grand Prix Circuit",
      "city": "Melbourne",
      "country": "Australia",
      "sessions": [
        {"type": "Practice 1", "time": "2025-03-14T11:30:00Z"},
        {"type": "Practice 2", "time": "2025-03-14T15:00:00Z"},
        {"type": "Qualifying", "time": "2025-03-15T14:00:00Z"},
        {"type": "Race", "time": "2025-03-16T05:00:00Z"}
      ],
      "status": "Scheduled"
    }
  ],
  "fetched_via": "selenium"
}
```

---

## 5. Implementation Guidelines

### 5.1 Creating New Fallback Methods

Follow this pattern when creating new fallback methods:

```python
async def _execute_selenium_fallback_{LEAGUE}(
    self, 
    task: PollTask
) -> "AsyncIOPool.APIResponse":
    """
    Execute {LEAGUE} task using Selenium browser scraping as fallback.
    
    This method is called when the direct API fails with a retryable error
    (403, 429, 500, 502, 503, 504).
    
    Args:
        task: The poll task containing league and task type information
        
    Returns:
        APIResponse with schedule data or error information
    """
    try:
        # Import browser dynamically to avoid dependency issues
        from src.datasource.{league}_stats.browser import (
            {League}StatsBrowser, 
            RateLimitConfig
        )
        from src.datasource.{league}_stats.schedule import (
            {League}ScheduleFetcher
        )
        
        logger.info(
            f"Using Selenium to fetch {task.league} schedule",
            extra={"league": task.league}
        )
        
        # Mock producer for testing
        class MockProducer:
            def __init__(self):
                self.messages = []
            def send(self, topic, **kwargs):
                self.messages.append((topic, kwargs))
            def flush(self):
                pass
        
        mock_producer = MockProducer()
        
        # Create browser with rate limiting
        rate_limit = RateLimitConfig(
            min_interval_s=2.0,
            max_retries=3,
            max_backoff_s=30.0,
        )
        
        with {League}StatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            fetcher = {League}ScheduleFetcher(
                browser=browser,
                kafka_producer=mock_producer,
                kafka_topic=f"{task.league.lower()}-schedule",
                season="2025-26",
            )
            
            today = datetime.now().strftime("%Y-%m-%d")
            games = fetcher.fetch_schedule(date_from=today, date_to=today)
            
            return AsyncIOPool.APIResponse(
                success=True,
                data={"games": games, "fetched_via": "selenium"},
                error=None,
                latency_seconds=10.0,
                league=task.league,
                task_type=task.task_type.value,
                sport_key=task.sport_key,
            )
    
    except ImportError as e:
        logger.error(
            f"Selenium modules not available: {e}",
            extra={"league": task.league}
        )
        return AsyncIOPool.APIResponse(
            success=False,
            data=None,
            error=f"Selenium not available: {e}",
            latency_seconds=0,
            league=task.league,
            task_type=task.task_type.value,
            sport_key=task.sport_key,
        )
    except Exception as e:
        logger.error(
            f"{task.league} Selenium fallback failed: {e}",
            extra={"league": task.league, "error": str(e)}
        )
        return AsyncIOPool.APIResponse(
            success=False,
            data=None,
            error=f"Selenium failed: {e}",
            latency_seconds=0,
            league=task.league,
            task_type=task.task_type.value,
            sport_key=task.sport_key,
        )
```

### 5.2 Updating `_execute_task()` for Fallback Routing

Modify [`src/unified_poller/main.py:293`](src/unified_poller/main.py:293) to route to the appropriate fallback:

```python
async def _execute_task(self, task: PollTask) -> "AsyncIOPool.APIResponse":
    """Execute a single polling task.
    
    Strategy:
    1. Try direct API first (fast, free)
    2. If API fails, fallback to Selenium browser scraping
    3. If all else fails, return error response
    """
    url = self._build_api_url(task)
    headers = self._build_headers(task)
    params = self._build_params(task)
    
    # Skip empty URLs (no API available for this league)
    if not url:
        return AsyncIOPool.APIResponse(
            success=False,
            data=None,
            error=f"No API endpoint configured for {task.league} {task.task_type.value}",
            latency_seconds=0,
            league=task.league,
            task_type=task.task_type.value,
            sport_key=task.sport_key,
        )
    
    async with self.async_pool as pool:
        # Try direct API first
        response = await pool.fetch(
            url=url,
            headers=headers,
            params=params,
            league=task.league,
            task_type=task.task_type.value,
            sport_key=task.sport_key,
        )
        
        # If API succeeded, return response
        if response.success:
            return response
        
        # API failed - try Selenium fallback based on league
        if task.task_type == TaskType.SCHEDULE:
            if task.league == "NBA":
                selenium_response = await self._execute_selenium_fallback(task)
                if selenium_response.success:
                    return selenium_response
            
            elif task.league == "NHL":
                selenium_response = await self._execute_selenium_fallback_NHL(task)
                if selenium_response.success:
                    return selenium_response
            
            elif task.league == "MLB":
                selenium_response = await self._execute_selenium_fallback_MLB(task)
                if selenium_response.success:
                    return selenium_response
            
            elif task.league == "NFL":
                selenium_response = await self._execute_selenium_fallback_NFL(task)
                if selenium_response.success:
                    return selenium_response
            
            elif task.league == "F1":
                selenium_response = await self._execute_selenium_fallback_F1(task)
                if selenium_response.success:
                    return selenium_response
        
        # All methods failed
        logger.warning(
            f"All methods failed for {task.league} {task.task_type.value}",
            extra={"league": task.league, "error": response.error}
        )
        return response
```

### 5.3 Creating Browser Utility Classes

For each league, create a browser utility class following the NBA pattern:

```python
# src/datasource/{league}_stats/browser.py

from __future__ import annotations

import logging
import random
import time
from contextlib import suppress
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]
ParamsDict = dict[str, str | float | bool]


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting during browser scraping."""
    min_interval_s: float = 1.0
    max_retries: int = 5
    max_retry_after_s: float = 60.0
    base_backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    jitter_s: float = 0.25


class RequestLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, cfg: RateLimitConfig) -> None:
        self.cfg = cfg
        self._last_request_ts: float | None = None
    
    def sleep_if_needed(self) -> None:
        if self._last_request_ts is None:
            return
        elapsed = time.time() - self._last_request_ts
        remaining = self.cfg.min_interval_s - elapsed
        if remaining > 0:
            logger.info("rate-limit: sleeping %.2fs", remaining)
            time.sleep(remaining)
    
    def mark_request(self) -> None:
        self._last_request_ts = time.time()
    
    def backoff(self, attempt: int, retry_after_s: Optional[float]) -> None:
        if retry_after_s is not None:
            sleep_s = min(retry_after_s, self.cfg.max_retry_after_s)
        else:
            exp = min(self.cfg.max_backoff_s, self.cfg.base_backoff_s * (2**attempt))
            sleep_s = exp + random.uniform(0.0, self.cfg.jitter_s)
        logger.info(
            "rate-limit: backing off for %.2fs (attempt %d)", sleep_s, attempt + 1
        )
        time.sleep(sleep_s)


class {League}StatsBrowser:
    """Playwright wrapper for {League} Stats API requests."""
    
    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30_000,
        user_agent: str | None = None,
        rate_limit: RateLimitConfig | None = None,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        )
        self.limiter = RequestLimiter(rate_limit or RateLimitConfig())
        
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
    
    def __enter__(self) -> "{League}StatsBrowser":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is required. Install with: pip install playwright && playwright install chromium"
            ) from e
        
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        self._context.set_extra_http_headers(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.{league}.com",
                "Referer": "https://www.{league}.com/",
            }
        )
        self._page = self._context.new_page()
        logger.info("browser: ready (headers set for {League} Stats API)")
        return self
    
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
    
    def close(self) -> None:
        if self._context is not None:
            with suppress(Exception):
                self._context.close()
        if self._browser is not None:
            with suppress(Exception):
                self._browser.close()
        if self._pw is not None:
            with suppress(Exception):
                self._pw.stop()
        
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
    
    @staticmethod
    def _coerce_params(params: Mapping[str, Any] | None) -> ParamsDict | None:
        if not params:
            return None
        out: ParamsDict = {}
        for k, v in params.items():
            if isinstance(v, bool):
                out[str(k)] = v
            elif isinstance(v, int):
                out[str(k)] = v
            elif isinstance(v, float):
                out[str(k)] = v
            elif v is None:
                continue
            else:
                out[str(k)] = str(v)
        return out
    
    @staticmethod
    def _safe_text_preview(resp: Any, limit: int = 300) -> str:
        with suppress(Exception):
            txt = resp.text()
            if txt:
                return str(txt)[:limit]
        return ""
    
    @staticmethod
    def _parse_retry_after(resp: Any) -> Optional[float]:
        with suppress(Exception):
            headers = {str(k).lower(): str(v) for k, v in resp.headers.items()}
            if "retry-after" in headers:
                return float(headers["retry-after"])
        return None
    
    def _should_retry(self, status: int) -> bool:
        return status in (429, 502, 503, 504)
    
    def new_page(self) -> Any:
        if self._context is None:
            raise RuntimeError("Browser context not initialized. Use context manager.")
        return self._context.new_page()
    
    def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> JsonDict:
        if self._page is None:
            raise RuntimeError(
                "{League}StatsBrowser is not started (use as a context manager)."
            )
        
        coerced_params = self._coerce_params(params)
        
        for attempt in range(self.limiter.cfg.max_retries + 1):
            self.limiter.sleep_if_needed()
            logger.info("fetch: %s params=%s", url, dict(coerced_params or {}))
            
            resp = self._page.request.get(
                url, params=coerced_params, timeout=self.timeout_ms
            )
            self.limiter.mark_request()
            
            status = int(getattr(resp, "status", 0))
            if status == 200:
                return resp.json()
            
            if self._should_retry(status):
                retry_after = self._parse_retry_after(resp)
                if attempt >= self.limiter.cfg.max_retries:
                    preview = self._safe_text_preview(resp)
                    raise RuntimeError(
                        f"{League} stats request failed after retries: status={status} preview={preview}"
                    )
                self.limiter.backoff(attempt, retry_after_s=retry_after)
                continue
            
            preview = self._safe_text_preview(resp)
            raise RuntimeError(
                f"{League} stats request failed: status={status} preview={preview}"
            )
        
        raise RuntimeError("unreachable")
```

---

## 6. Testing Requirements

### 6.1 Test Matrix

| League | Direct API Test | Selenium Fallback Test | Response Format Test | Graceful Degradation Test |
|--------|-----------------|------------------------|----------------------|---------------------------|
| **NBA** | ✅ Verify 403/429 handling | ✅ Verify headless scraping | ✅ Verify JSON format | ✅ Verify error response |
| **NHL** | ✅ Verify current API | ⏳ Implement & test | ⏳ Verify JSON format | ⏳ Verify error response |
| **MLB** | ✅ Verify current API | ⏳ Implement & test | ⏳ Verify JSON format | ⏳ Verify error response |
| **NFL** | ⏳ Verify no API exists | ⏳ Research & implement | ⏳ Verify JSON format | ⏳ Verify error response |
| **F1** | ⏳ Verify no API exists | ⏳ Research & implement | ⏳ Verify JSON format | ⏳ Verify error response |

### 6.2 Direct API Failure Tests

Test that the poller correctly detects and handles API failures:

```python
# Test cases for API failure detection
TEST_CASES = [
    {
        "status_code": 403,
        "expected_fallback": True,
        "description": "Forbidden - trigger Selenium fallback"
    },
    {
        "status_code": 429,
        "expected_fallback": True,
        "description": "Rate limited - trigger Selenium fallback"
    },
    {
        "status_code": 500,
        "expected_fallback": True,
        "description": "Server error - trigger Selenium fallback"
    },
    {
        "status_code": 502,
        "expected_fallback": True,
        "description": "Bad gateway - trigger Selenium fallback"
    },
    {
        "status_code": 503,
        "expected_fallback": True,
        "description": "Service unavailable - trigger Selenium fallback"
    },
    {
        "status_code": 504,
        "expected_fallback": True,
        "description": "Gateway timeout - trigger Selenium fallback"
    },
    {
        "status_code": 401,
        "expected_fallback": False,
        "description": "Unauthorized - no fallback, return error"
    },
    {
        "status_code": 404,
        "expected_fallback": False,
        "description": "Not found - no fallback, return error"
    },
]
```

### 6.3 Response Format Validation Tests

Verify that Selenium fallback responses match direct API format:

```python
# Validate response format consistency
def test_response_format():
    """Ensure Selenium fallback matches direct API format."""
    
    # Get direct API response
    direct_response = await fetch_nba_schedule_via_api()
    
    # Get Selenium fallback response
    selenium_response = await fetch_nba_schedule_via_selenium()
    
    # Validate structure
    assert "games" in selenium_response
    assert selenium_response["fetched_via"] == "selenium"
    
    # Validate game object structure
    for game in selenium_response["games"]:
        assert "GAME_ID" in game
        assert "GAME_DATE" in game
        assert "HOME_TEAM_ABBREVIATION" in game
        assert "AWAY_TEAM_ABBREVIATION" in game
        # ... validate all expected fields
```

### 6.4 Graceful Degradation Tests

Test that failures don't crash the poller:

```python
# Test graceful degradation
async def test_graceful_degradation():
    """Ensure failures are handled gracefully."""
    
    poller = UnifiedPoller(config)
    
    # Mock API failure
    with patch.object(poller.async_pool, 'fetch') as mock_fetch:
        mock_fetch.return_value = AsyncIOPool.APIResponse(
            success=False,
            data=None,
            error="API Error",
            latency_seconds=0,
            league="NBA",
            task_type="schedule",
            sport_key="nba",
        )
        
        # Mock Selenium failure
        with patch.object(poller, '_execute_selenium_fallback') as mock_selenium:
            mock_selenium.return_value = AsyncIOPool.APIResponse(
                success=False,
                data=None,
                error="Selenium Error",
                latency_seconds=0,
                league="NBA",
                task_type="schedule",
                sport_key="nba",
            )
            
            # Execute task
            result = await poller._execute_task(task)
            
            # Should return error, not crash
            assert not result.success
            assert "API Error" in result.error
```

### 6.5 Running Tests

```bash
# Run all tests
pytest tests/test_fallback.py -v

# Run specific league tests
pytest tests/test_fallback.py -k "nhl" -v

# Run with coverage
pytest tests/test_fallback.py --cov=src.unified_poller --cov-report=html

# Run integration tests
pytest tests/test_fallback.py -k "integration" -v
```

---

## 7. Related Files

### 7.1 Source Files

| File | Description |
|------|-------------|
| [`src/unified_poller/main.py`](src/unified_poller/main.py) | Main poller implementation with `_execute_task()` |
| [`src/unified_poller/async_io_pool.py`](src/unified_poller/async_io_pool.py) | Async I/O pool with rate limiting |
| [`src/datasource/nba_stats/schedule.py`](src/datasource/nba_stats/schedule.py) | NBA Selenium reference implementation |
| [`src/datasource/nba_stats/browser.py`](src/datasource/nba_stats/browser.py) | NBA browser utility class |
| [`src/datasource/nba_stats/client.py`](src/datasource/nba_stats/client.py) | NBA API client |

### 7.2 Configuration Files

| File | Description |
|------|-------------|
| [`data/nba/config.json`](data/nba/config.json) | NBA league configuration |
| [`data/nhl/config.json`](data/nhl/config.json) | NHL league configuration |
| [`data/mlb/config.json`](data/mlb/config.json) | MLB league configuration |
| [`data/nfl/config.json`](data/nfl/config.json) | NFL league configuration |
| [`data/f1/config.json`](data/f1/config.json) | F1 league configuration |

### 7.3 Documentation Files

| File | Description |
|------|-------------|
| [`docs/market-research/nhl-market-research.md`](docs/market-research/nhl-market-research.md) | NHL market research |
| [`docs/market-research/mlb-market-research.md`](docs/market-research/mlb-market-research.md) | MLB market research |
| [`docs/market-research/nfl-market-research.md`](docs/market-research/nfl-market-research.md) | NFL market research |
| [`docs/market-research/f1-market-research.md`](docs/market-research/f1-market-research.md) | F1 market research |
| [`plans/unified-poller-architecture.md`](plans/unified-poller-architecture.md) | Architecture documentation |

### 7.4 Test Files

| File | Description |
|------|-------------|
| `tests/test_fallback.py` | Fallback strategy tests |
| `tests/test_async_io_pool.py` | Async I/O pool tests |
| `tests/test_nba_selenium.py` | NBA Selenium tests |

---

## 8. TODO: Implementation Plan

### Phase 1: NHL Selenium Fallback (High Priority)

- [ ] Create `src/datasource/nhl_stats/browser.py` with `NHLStatsBrowser` class
- [ ] Create `src/datasource/nhl_stats/schedule.py` with `NHLScheduleFetcher` class
- [ ] Implement `_execute_selenium_fallback_NHL()` in `main.py`
- [ ] Add routing in `_execute_task()` for NHL league
- [ ] Test NHL fallback when direct API returns 403/429/500
- [ ] Verify response format matches NHL API format
- [ ] Update documentation with test results

### Phase 2: MLB Selenium Fallback (High Priority)

- [ ] Create `src/datasource/mlb_stats/browser.py` with `MLBStatsBrowser` class
- [ ] Create `src/datasource/mlb_stats/schedule.py` with `MLBScheduleFetcher` class
- [ ] Implement `_execute_selenium_fallback_MLB()` in `main.py`
- [ ] Add routing in `_execute_task()` for MLB league
- [ ] Test MLB fallback when direct API returns 403/429/500
- [ ] Verify response format matches MLB API format
- [ ] Update documentation with test results

### Phase 3: NFL Research & Fallback (Medium Priority)

- [ ] Research NFL data sources and identify best scraping target
- [ ] Create `src/datasource/nfl_stats/browser.py` with `NFLStatsBrowser` class
- [ ] Create `src/datasource/nfl_stats/schedule.py` with `NFLScheduleFetcher` class
- [ ] Implement `_execute_selenium_fallback_NFL()` in `main.py`
- [ ] Add routing in `_execute_task()` for NFL league
- [ ] Test NFL fallback (expected to always use Selenium)
- [ ] Verify response format for NFL data
- [ ] Update documentation with implementation details

### Phase 4: F1 Research & Fallback (Low Priority)

- [ ] Research F1 data sources (FastF1 library, OpenF1 API)
- [ ] Evaluate whether to use FastF1 library or browser scraping
- [ ] Create `src/datasource/f1_stats/browser.py` with `F1StatsBrowser` class
- [ ] Create `src/datasource/f1_stats/schedule.py` with `F1ScheduleFetcher` class
- [ ] Implement `_execute_selenium_fallback_F1()` in `main.py`
- [ ] Add routing in `_execute_task()` for F1 league
- [ ] Test F1 fallback
- [ ] Verify response format for F1 data
- [ ] Update documentation with implementation details

### Phase 5: Testing & Documentation (Ongoing)

- [ ] Run kubeconform validation on all YAML files
- [ ] Run checkov security scanning on manifests
- [ ] Format all YAML with Prettier
- [ ] Verify Python syntax for all source files
- [ ] Document test results in runbook
- [ ] Update API fallback documentation with new implementations
- [ ] Add integration tests for end-to-end fallback flow

---

## Appendix A: Quick Reference

### API Endpoints Summary

| League | Schedule URL | Scores URL | Status |
|--------|--------------|------------|--------|
| NBA | `https://stats.nba.com/stats/schedule` | `https://stats.nba.com/stats/scoreboard` | ✅ Active |
| NHL | `https://api-web.nhle.com/v1/schedule` | `https://api-web.nhle.com/v1/schedule` | ✅ Active |
| MLB | `https://statsapi.mlb.com/api/v1/schedule` | `https://statsapi.mlb.com/api/v1/schedule` | ✅ Active |
| NFL | N/A (no free API) | N/A | ❌ No API |
| F1 | N/A (no free API) | N/A | ❌ No API |

### HTTP Status Codes and Fallback Behavior

| Status Code | Meaning | Fallback Triggered? | Notes |
|-------------|---------|---------------------|-------|
| 200 | OK | No | Success |
| 401 | Unauthorized | No | Authentication issue |
| 403 | Forbidden | Yes | Likely rate limiting |
| 404 | Not Found | No | Endpoint changed |
| 429 | Too Many Requests | Yes | Rate limit exceeded |
| 500 | Server Error | Yes | Server-side issue |
| 502 | Bad Gateway | Yes | Proxy/gateway issue |
| 503 | Service Unavailable | Yes | Service down |
| 504 | Gateway Timeout | Yes | Timeout issue |

---

*Document Version: 1.0*  
*Generated: January 2026*  
*For: Sports Platform Unified Poller Development*
