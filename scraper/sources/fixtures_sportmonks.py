"""
fixtures_sportmonks.py
Fetches Scottish Premiership fixtures via Sportmonks free API.
Free plan covers Scottish Premiership (league ID: 501) only.

API v3 docs: https://docs.sportmonks.com/v3
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

API_KEY  = os.environ.get("SPORTMONKS_API_KEY", "")
API_BASE = "https://api.sportmonks.com/v3/football"

# Free plan: Scottish Premiership = 501 ONLY
# Scottish Championship is NOT on free plan — skip it
LEAGUES = {
    501: {"name": "Scottish Premiership", "code": "SP1"},
}


def _get_headers():
    return {
        "Authorization": API_KEY,
        "Accept": "application/json",
    }


def _fetch_fixtures(league_id: int, days: int = 30) -> list:
    """Fetch upcoming fixtures for a league using the correct v3 filter syntax."""
    now       = datetime.now(timezone.utc)
    date_from = now.strftime("%Y-%m-%d")
    date_to   = (now + timedelta(days=days)).strftime("%Y-%m-%d")

    url = f"{API_BASE}/fixtures/between/{date_from}/{date_to}"
    params = {
        "api_token":    API_KEY,
        "filters":      f"fixtureLeagues:{league_id}",
        "include":      "participants",
        "per_page":     50,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        logger.debug(f"[sportmonks] URL: {resp.url}")

        if resp.status_code == 401:
            logger.warning("[sportmonks] 401 — check SPORTMONKS_API_KEY")
            return []
        if resp.status_code == 403:
            logger.warning(f"[sportmonks] 403 — league {league_id} not on your plan")
            return []
        resp.raise_for_status()
        data = resp.json()

        fixtures = data.get("data", [])
        logger.info(f"[sportmonks] League {league_id}: raw API returned {len(fixtures)} fixtures")

        # Filter to only the requested league — API may return others on free plan
        filtered = [f for f in fixtures if f.get("league_id") == league_id]
        logger.info(f"[sportmonks] League {league_id}: {len(filtered)} after league filter")
        return filtered

    except requests.RequestException as e:
        logger.error(f"[sportmonks] Request failed for league {league_id}: {e}")
        return []


def _parse_fixture(match: dict, comp_info: dict) -> dict | None:
    """Convert a Sportmonks v3 fixture to TVsport format."""
    try:
        # Participants array: each has meta.location = "home" or "away"
        participants = match.get("participants", [])
        home = away = ""
        for p in participants:
            location = (p.get("meta") or {}).get("location", "")
            name = p.get("name", "")
            if location == "home":
                home = name
            elif location == "away":
                away = name

        if not home or not away:
            logger.debug(f"[sportmonks] Could not determine teams for fixture {match.get('id')}")
            return None

        # Kickoff — prefer starting_at string, fallback to timestamp
        starting_at = match.get("starting_at", "")
        if not starting_at:
            ts = match.get("starting_at_timestamp")
            if ts:
                starting_at = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            # Sportmonks returns "YYYY-MM-DD HH:MM:SS" without timezone — treat as UTC
            starting_at = starting_at.replace(" ", "T")
            if not starting_at.endswith("Z") and "+" not in starting_at:
                starting_at += "Z"

        date_slug = starting_at[:10] if starting_at else "unknown"
        fixture_id = f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{date_slug}"

        # Round/matchday
        round_data = match.get("round", {})
        matchday = round_data.get("name") if isinstance(round_data, dict) else None

        return {
            "id":          fixture_id,
            "competition": comp_info["name"],
            "comp_code":   comp_info["code"],
            "home_team":   home,
            "away_team":   away,
            "kickoff":     starting_at,
            "matchday":    matchday,
            "stage":       "REGULAR_SEASON",
            "group":       None,
            "source":      "sportmonks.com",
        }
    except Exception as e:
        logger.debug(f"[sportmonks] Parse error: {e}")
        return None


def scrape_fixtures() -> list:
    """Fetch Scottish Premiership fixtures from Sportmonks."""
    if not API_KEY:
        logger.warning("[sportmonks] No API key — set SPORTMONKS_API_KEY in GitHub secrets")
        return []

    all_fixtures = []
    seen_ids = set()

    for league_id, comp_info in LEAGUES.items():
        logger.info(f"[sportmonks] Fetching {comp_info['name']} (ID: {league_id})...")
        matches = _fetch_fixtures(league_id)

        count = 0
        for match in matches:
            fixture = _parse_fixture(match, comp_info)
            if fixture and fixture["id"] not in seen_ids:
                seen_ids.add(fixture["id"])
                all_fixtures.append(fixture)
                count += 1

        logger.info(f"[sportmonks] {comp_info['name']}: {count} fixtures parsed")

    return all_fixtures
