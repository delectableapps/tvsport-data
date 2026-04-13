"""
fixtures_footballdata.py
Primary fixture source: football-data.org free API
Covers: EPL, Championship, UCL, UEL, UECL, Bundesliga, La Liga, Serie A,
        Ligue 1, Eredivisie, Primeira Liga, FA Cup, Brazil Serie A

Requires: FOOTBALL_DATA_API_KEY environment variable (free registration at
          football-data.org — takes 30 seconds)
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

API_BASE = "https://api.football-data.org/v4"
API_KEY  = os.environ.get("FOOTBALL_DATA_API_KEY", "")

# football-data.org competition codes → TVsport internal codes + display names
COMPETITIONS = {
    "PL":  {"name": "Premier League",            "code": "PL",  "days": 30},
    "CL":  {"name": "UEFA Champions League",     "code": "CL",  "days": 30},
    # Note: UEL and UECL are not available on football-data.org free tier
    # "EL":  {"name": "UEFA Europa League",       "code": "EL",  "days": 30},
    # "ECL": {"name": "UEFA Conference League",   "code": "ECL", "days": 30},
    "ELC": {"name": "Championship",              "code": "ELC", "days": 14},
    "FL1": {"name": "Ligue 1",                   "code": "FL1", "days": 14},
    "BL1": {"name": "Bundesliga",               "code": "BL1", "days": 14},
    "SA":  {"name": "Serie A",                   "code": "SA",  "days": 14},
    "PD":  {"name": "La Liga",                   "code": "PD",  "days": 14},
    "FAC": {"name": "FA Cup",                    "code": "FAC", "days": 30},
}

# Competitions to show in UK even during blackout (overseas comps never blacked out)
NON_EPL_COMPS = {"CL", "EL", "ECL", "FL1", "BL1", "SA", "PD"}


def _headers() -> dict:
    h = {"X-Auth-Token": API_KEY} if API_KEY else {}
    return h


def _fetch_matches(competition_code: str, days: int) -> list:
    """Fetch upcoming matches for a competition from football-data.org."""
    now = datetime.now(timezone.utc)
    date_from = now.strftime("%Y-%m-%d")
    date_to   = (now + timedelta(days=days)).strftime("%Y-%m-%d")

    url = f"{API_BASE}/competitions/{competition_code}/matches"
    params = {
        "dateFrom": date_from,
        "dateTo":   date_to,
        "status":   "SCHEDULED,TIMED",
    }

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code == 429:
            logger.warning(f"[football-data] Rate limited for {competition_code} — skipping")
            return []
        if resp.status_code == 403:
            logger.warning(f"[football-data] 403 for {competition_code} — check API key")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("matches", [])
    except requests.RequestException as e:
        logger.error(f"[football-data] Failed to fetch {competition_code}: {e}")
        return []


def _normalise_match(match: dict, comp_info: dict) -> dict | None:
    """Convert a football-data.org match object to TVsport fixture format."""
    try:
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        utc_date = match.get("utcDate", "")          # ISO string e.g. 2026-04-19T15:00:00Z
        matchday = match.get("matchday")
        stage    = match.get("stage", "")
        group    = match.get("group", "")

        if not home or not away or not utc_date:
            return None

        return {
            "id":          f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{utc_date[:10]}",
            "competition": comp_info["name"],
            "comp_code":   comp_info["code"],
            "home_team":   home,
            "away_team":   away,
            "kickoff":     utc_date,                 # UTC ISO string
            "matchday":    matchday,
            "stage":       stage,
            "group":       group,
            "source":      "football-data.org",
        }
    except (KeyError, TypeError) as e:
        logger.debug(f"[football-data] Could not normalise match: {e}")
        return None


def scrape_fixtures() -> list:
    """
    Fetch all fixtures from football-data.org free tier.
    Returns list of normalised fixture dicts.
    """
    if not API_KEY:
        logger.warning("[football-data] No API key set — set FOOTBALL_DATA_API_KEY env var. "
                       "Register free at football-data.org (takes 30 seconds).")

    all_fixtures = []
    seen_ids = set()

    for fd_code, comp_info in COMPETITIONS.items():
        logger.info(f"[football-data] Fetching {comp_info['name']} ({fd_code})...")
        matches = _fetch_matches(fd_code, comp_info["days"])

        for match in matches:
            fixture = _normalise_match(match, comp_info)
            if fixture and fixture["id"] not in seen_ids:
                seen_ids.add(fixture["id"])
                all_fixtures.append(fixture)

        logger.info(f"[football-data] {comp_info['name']}: {len(matches)} matches found")

    logger.info(f"[football-data] Total: {len(all_fixtures)} fixtures")
    return all_fixtures
