"""
fixtures_sportmonks.py
Fetches Scottish Premiership (and Championship) fixtures via Sportmonks free API.
Free plan covers Scottish Premiership forever.

API docs: https://docs.sportmonks.com/football
Base URL: https://api.sportmonks.com/v3/football
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

API_KEY  = os.environ.get("SPORTMONKS_API_KEY", "")
API_BASE = "https://api.sportmonks.com/v3/football"

# Sportmonks league IDs
LEAGUES = {
    501:  {"name": "Scottish Premiership",  "code": "SP1"},
    502:  {"name": "Scottish Championship", "code": "SC1"},
}

HEADERS = {
    "Authorization": API_KEY,
    "Accept": "application/json",
}


def _fetch_fixtures(league_id: int, days: int = 30) -> list:
    """Fetch upcoming fixtures for a league from Sportmonks."""
    now      = datetime.now(timezone.utc)
    date_from = now.strftime("%Y-%m-%d")
    date_to   = (now + timedelta(days=days)).strftime("%Y-%m-%d")

    url = f"{API_BASE}/fixtures/between/{date_from}/{date_to}"
    params = {
        "api_token": API_KEY,
        "filters":   f"leagueIds:{league_id}",
        "include":   "participants",
        "per_page":  50,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            logger.warning("[sportmonks] 401 — check SPORTMONKS_API_KEY secret")
            return []
        if resp.status_code == 403:
            logger.warning(f"[sportmonks] 403 — league {league_id} may not be on free plan")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.RequestException as e:
        logger.error(f"[sportmonks] Request failed for league {league_id}: {e}")
        return []


def _parse_fixture(match: dict, comp_info: dict) -> dict | None:
    """Convert a Sportmonks fixture object to TVsport format."""
    try:
        # Participants array contains home and away team
        participants = match.get("participants", [])
        home = away = ""
        for p in participants:
            meta = p.get("meta", {})
            location = meta.get("location", "")
            name = p.get("name", "")
            if location == "home":
                home = name
            elif location == "away":
                away = name

        if not home or not away:
            # Fallback: try name fields directly
            home = match.get("home_team", {}).get("name", "") if isinstance(match.get("home_team"), dict) else ""
            away = match.get("away_team", {}).get("name", "") if isinstance(match.get("away_team"), dict) else ""

        if not home or not away:
            return None

        # Kickoff time
        starting_at = match.get("starting_at", "") or match.get("starting_at_timestamp", "")
        if isinstance(starting_at, int):
            # Unix timestamp
            kickoff = datetime.fromtimestamp(starting_at, tz=timezone.utc).isoformat()
        else:
            kickoff = starting_at or ""

        date_slug = kickoff[:10] if kickoff else "unknown"
        fixture_id = f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{date_slug}"

        return {
            "id":          fixture_id,
            "competition": comp_info["name"],
            "comp_code":   comp_info["code"],
            "home_team":   home,
            "away_team":   away,
            "kickoff":     kickoff,
            "matchday":    match.get("round", {}).get("name") if isinstance(match.get("round"), dict) else match.get("round"),
            "stage":       "REGULAR_SEASON",
            "group":       None,
            "source":      "sportmonks.com",
        }
    except Exception as e:
        logger.debug(f"[sportmonks] Could not parse fixture: {e}")
        return None


def scrape_fixtures() -> list:
    """Fetch Scottish fixtures from Sportmonks. Returns list of fixture dicts."""
    if not API_KEY:
        logger.warning("[sportmonks] No API key — set SPORTMONKS_API_KEY secret in GitHub")
        return []

    all_fixtures = []
    seen_ids = set()

    for league_id, comp_info in LEAGUES.items():
        logger.info(f"[sportmonks] Fetching {comp_info['name']} (league {league_id})...")
        matches = _fetch_fixtures(league_id)

        for match in matches:
            fixture = _parse_fixture(match, comp_info)
            if fixture and fixture["id"] not in seen_ids:
                seen_ids.add(fixture["id"])
                all_fixtures.append(fixture)

        logger.info(f"[sportmonks] {comp_info['name']}: {len(matches)} fixtures fetched")

    logger.info(f"[sportmonks] Total: {len(all_fixtures)} Scottish fixtures")
    return all_fixtures
