#!/usr/bin/env python3
"""Test NBA Stats API fetch with correct headers."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig


def test_stats_api():
    """Test fetching from stats.nba.com with correct headers."""
    
    rate_limit = RateLimitConfig(
        min_interval_s=2.0,
        max_retries=5,
        max_backoff_s=60.0,
        base_backoff_s=5.0,
    )
    
    print("=" * 60)
    print("Testing NBA Stats API with correct headers")
    print("=" * 60)
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"[FAIL] Playwright not installed: {e}")
        return None
    
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        locale="en-US",
    )
    
    # Set correct headers to avoid blocking
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Origin": "https://www.nba.com",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": "https://www.nba.com/",
        "Sec-Ch-Ua": '"Not(A:Brand";v="8", "Chromium";v="144"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    
    context.set_extra_http_headers(headers)
    page = context.new_page()
    
    # Test endpoints
    endpoints = [
        ("CommonAllPlayers", "https://stats.nba.com/stats/commonallplayers", {"LeagueID": "00", "Season": "2024-25", "IsOnlyCurrentSeason": 1}),
        ("LeagueGameFinder", "https://stats.nba.com/stats/leaguegamefinder", {"LeagueID": "00", "Season": "2024-25", "SeasonType": "Regular Season"}),
        ("TeamInfoCommon", "https://stats.nba.com/stats/teaminfocommon", {"LeagueID": "00", "Season": "2024-25", "TeamID": 1610612743}),
    ]
    
    results = {}
    
    for name, url, params in endpoints:
        print(f"\nTesting {name}...")
        
        for attempt in range(rate_limit.max_retries + 1):
            try:
                resp = page.request.get(url, params=params, timeout=30000)
                status = int(getattr(resp, "status", 0))
                
                if status == 200:
                    data = resp.json()
                    results[name] = {"status": 200, "data": data}
                    print(f"  [OK] Status {status}")
                    
                    # Check for resultSet
                    if "resultSets" in data:
                        row_set = data["resultSets"][0].get("rowSet", [])
                        print(f"  [OK] Got {len(row_set)} rows")
                    elif "result" in data:
                        row_set = data["result"].get("data", [])
                        print(f"  [OK] Got {len(row_set)} rows")
                    
                    break
                elif status == 403 or status == 429:
                    print(f"  Blocked (status={status}), backing off...")
                    import time
                    time.sleep(rate_limit.base_backoff_s * (2 ** attempt))
                    continue
                else:
                    print(f"  Status {status}: {resp.text()[:200] if hasattr(resp, 'text') else 'N/A'}")
                    break
                    
            except Exception as e:
                print(f"  Error: {e}")
                import time
                time.sleep(5)
    
    # Cleanup
    context.close()
    browser.close()
    pw.stop()
    
    return results


if __name__ == "__main__":
    results = test_stats_api()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if results:
        for name, result in results.items():
            status = result.get("status", "N/A")
            print(f"  {name}: {'OK' if status == 200 else 'FAILED'} (status={status})")
    else:
        print("  All endpoints FAILED")
    
    print("=" * 60)
