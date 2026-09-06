"""
fixtures_thesportsdb.py
=======================
Fixture source: TheSportsDB free API (api key: 123, no signup needed)
Covers competitions NOT available on football-data.org free tier:
  - EFL League One
  - EFL League Two
  - National League
  - FA Cup
  - EFL Cup (Carabao Cup)
  - Scottish Championship
  - Scottish Cup
  - Scottish League Cup

Also used as a fallback/supplement for competitions already in football-data.org.

API docs: https://www.thesportsdb.com/documentation
Free tier: 30 requests/minute, no auth needed beyond key=123 in URL
Endpoint:  /api/v1/json/{key}/eventsnextleague.php?id={league_id}
           Returns next 25 upcoming events for a league
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://www.thesportsdb.com/api/v1/json"
API_KEY  = os.environ.get("THESPORTSDB_API_KEY", "123")  # 123 = free key, works without signup

# TheSportsDB league IDs — verified from thesportsdb.com URL structure
# Only competitions NOT already covered by football-data.org free tier
TSDB_COMPETITIONS = {
    # English EFL — verified IDs from thesportsdb.com URLs
    "4396":  {"name": "EFL League One",       "code": "EL1",    "display": "League One",        "days": 21},
    "4397":  {"name": "EFL League Two",       "code": "EL2",    "display": "League Two",        "days": 21},
    "4590":  {"name": "National League",      "code": "NAT",    "display": "National League",   "days": 21},
    "4570":  {"name": "EFL Cup",              "code": "EFLCUP", "display": "EFL Cup",           "days": 30},
    # Scottish — supplement to Sportmonks (which only covers Premiership)
    # REMOVED 6 Sep 2026 — these IDs were WRONG and leaked foreign fixtures:
    #   4344 is Portuguese Primeira Liga (was labelled "FA Cup")
    #   4337 is Dutch Eredivisie          (was labelled "Scottish Cup")
    #   4338 is Belgian Pro League        (was labelled "Scottish Championship")
    # FA Cup / Scottish Cup come from the BBC cups scraper; Scottish
    # Championship is backfilled from liveonsat. Only re-add with IDs
    # verified against thesportsdb.com/league/<id>.
    "4341":  {"name": "Scottish League Cup",  "code": "SLCUP",  "display": "Scottish League Cup","days": 30},
}

# TVsport comp_code → display name mapping (for normalisation)
COMP_CODE_NAMES = {
    "EL1":    "League One",
    "EL2":    "League Two",
    "NAT":    "National League",
    "EFLCUP": "EFL Cup",
    "FACUP":  "FA Cup",
    "SCH":    "Scottish Championship",
    "SCUP":   "Scottish Cup",
    "SLCUP":  "Scottish League Cup",
}


def _headers() -> dict:
    return {"Accept": "application/json"}


def _fetch_next_events(league_id: str, days: int) -> list:
    """
    Fetch upcoming events for a league using TheSportsDB v1 API.
    Uses eventsnextleague.php which returns the next 25 events.
    Note: eventsseason.php requires premium API key - not available on free tier.
    """
    url = f"{API_BASE}/{API_KEY}/eventsnextleague.php"
    params = {"id": league_id}

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code == 429:
            logger.warning(f"[thesportsdb] Rate limited for league {league_id} — waiting 10s")
            time.sleep(10)
            resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[thesportsdb] HTTP {resp.status_code} for league {league_id}")
            return []
        data = resp.json()
        events = data.get("events") or []
        return events
    except requests.RequestException as e:
        logger.error(f"[thesportsdb] Failed to fetch league {league_id}: {e}")
        return []


def _parse_kickoff(date_str: str, time_str: str) -> str | None:
    """
    Parse TheSportsDB date/time strings into UTC ISO format.
    date_str: "2026-04-25"
    time_str: "14:00:00" (UTC)
    Returns: "2026-04-25T14:00:00Z"
    """
    if not date_str:
        return None
    try:
        time_part = time_str.strip() if time_str else "00:00:00"
        # Sometimes time has timezone offset — strip it
        if "+" in time_part:
            time_part = time_part.split("+")[0]
        if len(time_part) == 5:  # "14:00" without seconds
            time_part += ":00"
        dt_str = f"{date_str}T{time_part}"
        dt = datetime.fromisoformat(dt_str)
        # TheSportsDB returns UTC times
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        logger.debug(f"[thesportsdb] Could not parse date '{date_str}' time '{time_str}': {e}")
        return None


def _normalise_event(event: dict, comp_info: dict) -> dict | None:
    """Convert a TheSportsDB event object to TVsport fixture format."""
    try:
        home = event.get("strHomeTeam", "").strip()
        away = event.get("strAwayTeam", "").strip()
        date_str = event.get("dateEvent", "")
        time_str = event.get("strTime", "00:00:00")
        round_num = event.get("intRound")
        stage = event.get("strStatus", "")
        event_id = event.get("idEvent", "")

        if not home or not away or not date_str:
            return None

        kickoff = _parse_kickoff(date_str, time_str)
        if not kickoff:
            return None

        # Only include fixtures within the lookahead window
        ko_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=comp_info["days"])
        if ko_dt < now or ko_dt > cutoff:
            return None

        # Build a stable ID
        fixture_id = f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{date_str}"

        return {
            "id":          fixture_id,
            "competition": comp_info["display"],
            "comp_code":   comp_info["code"],
            "home_team":   home,
            "away_team":   away,
            "kickoff":     kickoff,
            "matchday":    int(round_num) if round_num else None,
            "stage":       stage,
            "group":       None,
            "source":      "thesportsdb",
            "tsdb_id":     event_id,
        }
    except Exception as e:
        logger.debug(f"[thesportsdb] Could not normalise event: {e}")
        return None


def scrape_fixtures() -> list:
    """
    Fetch upcoming fixtures from TheSportsDB for competitions not covered
    by football-data.org free tier.

    Returns list of normalised fixture dicts compatible with merger.py.
    """
    all_fixtures = []
    seen_ids = set()
    request_count = 0

    for league_id, comp_info in TSDB_COMPETITIONS.items():
        logger.info(f"[thesportsdb] Fetching {comp_info['display']} (id={league_id})...")

        # Rate limit: 30 requests/min on free tier — add small delay
        if request_count > 0 and request_count % 25 == 0:
            logger.info("[thesportsdb] Rate limit pause (2s)...")
            time.sleep(2)

        events = _fetch_next_events(league_id, comp_info["days"])
        request_count += 1

        added = 0
        for event in events:
            fixture = _normalise_event(event, comp_info)
            if fixture and fixture["id"] not in seen_ids:
                seen_ids.add(fixture["id"])
                all_fixtures.append(fixture)
                added += 1

        logger.info(f"[thesportsdb] {comp_info['display']}: {added} fixtures added")

    logger.info(f"[thesportsdb] Total: {len(all_fixtures)} fixtures from TheSportsDB")
    return all_fixtures


if __name__ == "__main__":
    # Quick test — run directly to see what comes back
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fixtures = scrape_fixtures()
    print(f"\n{len(fixtures)} fixtures found:")
    for f in fixtures[:10]:
        print(f"  [{f['comp_code']}] {f['home_team']} v {f['away_team']} — {f['kickoff']}")
