"""
sources/fixtures_premierleague.py
===================================
Scrapes the Premier League's official fixture changes announcement page
to get the confirmed 30-day EPL schedule including:
  - All fixture dates + kick-off times
  - Which matches are TV-selected (Sky/TNT)
  - Which matches are 3pm Saturday blackouts (not selected = blackout)
  - Venue info

Source: https://www.premierleague.com/en/news/fixture-changes-announced-for-...
Also: https://www.live-footballontv.com/live-premier-league-football-on-tv.html
      (backup for fixture list)
"""

import re
import logging
from datetime import date, datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Primary: PL fixture changes page
PL_FIXTURE_CHANGES_URL = (
    "https://www.premierleague.com/en/news/4606462/"
    "premier-league-fixture-changes-announced-for-april-2026"
)

# Backup full schedule page
PL_FULL_SCHEDULE_URL = (
    "https://www.live-footballontv.com/live-premier-league-football-on-tv.html"
)

# All 20 EPL teams this season
EPL_TEAMS_2526 = [
    "Arsenal", "Aston Villa", "AFC Bournemouth", "Brentford", "Brighton",
    "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham",
    "Leeds United", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Sunderland",
    "Tottenham Hotspur", "West Ham United", "Wolverhampton Wanderers",
]

# Team name aliases for fuzzy matching
TEAM_ALIASES = {
    "wolves": "Wolverhampton Wanderers",
    "wolverhampton": "Wolverhampton Wanderers",
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "newcastle": "Newcastle United",
    "newcastle utd": "Newcastle United",
    "nott'm forest": "Nottingham Forest",
    "notts forest": "Nottingham Forest",
    "nottm forest": "Nottingham Forest",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "west ham": "West Ham United",
    "bournemouth": "AFC Bournemouth",
    "afc bournemouth": "AFC Bournemouth",
    "brighton": "Brighton",
    "brighton & hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "leeds": "Leeds United",
}


def _normalise(name: str) -> str:
    n = name.strip().lower().replace("&", "and").replace(".", "").replace("'", "").replace("-", " ")
    return TEAM_ALIASES.get(n, n)


def _canonical_team(name: str) -> str:
    """Return canonical team name."""
    n = _normalise(name)
    for team in EPL_TEAMS_2526:
        if _normalise(team) == n:
            return team
    # Fuzzy: check if n is contained in canonical
    for team in EPL_TEAMS_2526:
        if n in _normalise(team) or _normalise(team) in n:
            return team
    return name.title()


def _make_key(home: str, away: str) -> str:
    return f"{_normalise(home)} v {_normalise(away)}"


def _bst_to_utc(date_str: str, time_bst: str) -> str:
    """BST (UTC+1 in April-October) → UTC."""
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        month = dt.month
        offset = 1 if 3 < month < 11 else 0
        dt_utc = dt - timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _is_saturday_3pm_blackout(date_str: str, time_bst: str) -> bool:
    """Return True if this is a 3pm Saturday (UK blackout)."""
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        return dt.weekday() == 5 and time_bst == "15:00"
    except Exception:
        return False


def scrape_fixture_changes() -> dict:
    """
    Scrape the PL fixture changes page.
    Returns { fixture_key: { home, away, date, kickoff_utc, uk_blackout,
                              broadcaster, matchday } }
    """
    try:
        r = requests.get(PL_FIXTURE_CHANGES_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch PL fixture changes: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    results = {}

    MONTH_MAP = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # Parse patterns from PL fixture changes page:
    # "MW32" or "MW33" → matchday marker
    # "Friday 10 April" → date
    # "20:00 West Ham v Wolves (Sky Sports)" → fixture

    matchday_pattern = re.compile(r"^MW(\d+)$")
    date_pattern = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(\d{1,2})\s+(\w+)(?:\s+\d{4})?$",
        re.IGNORECASE
    )
    # Fixture: "20:00 West Ham v Wolves (Sky Sports)"
    # or just: "Brentford v Everton" (no time = 15:00 Saturday default)
    fixture_with_time = re.compile(
        r"^(\d{2}:\d{2})\s+(.+?)\s+v\s+(.+?)(?:\s+\((.+?)\))?$"
    )
    fixture_no_time = re.compile(
        r"^([A-Z][a-zA-Z\s\']+?)\s+v\s+([A-Z][a-zA-Z\s\']+?)(?:\s+\*+)?$"
    )

    current_date = None
    current_matchday = None
    current_day_of_week = None

    year = date.today().year

    for line in lines:
        # Check matchday
        m = matchday_pattern.match(line)
        if m:
            current_matchday = int(m.group(1))
            continue

        # Check date
        m = date_pattern.match(line)
        if m:
            current_day_of_week = m.group(1).lower()
            day_num = int(m.group(2))
            month_name = m.group(3).lower()
            month_num = MONTH_MAP.get(month_name, 0)
            if month_num:
                adj_year = year
                if month_num < date.today().month - 2:
                    adj_year += 1
                try:
                    current_date = date(adj_year, month_num, day_num).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            continue

        if not current_date:
            continue

        # Check fixture with time
        m = fixture_with_time.match(line)
        if m:
            kickoff_time = m.group(1)
            home_raw = m.group(2).strip()
            away_raw = m.group(3).strip()
            broadcaster_raw = m.group(4) or ""

            home = _canonical_team(home_raw)
            away = _canonical_team(away_raw)
            key = _make_key(home, away)

            uk_blackout = _is_saturday_3pm_blackout(current_date, kickoff_time)
            kickoff_utc = _bst_to_utc(current_date, kickoff_time)

            # Parse broadcaster from brackets
            uk_broadcaster = None
            uk_channels = []
            if "Sky Sports" in broadcaster_raw:
                uk_broadcaster = "Sky Sports"
                uk_channels = _parse_sky_channels(broadcaster_raw)
            elif "TNT" in broadcaster_raw:
                uk_broadcaster = "TNT Sports"
                uk_channels = ["TNT Sports 1", "TNT Sports Ultimate", "HBO Max"]

            results[key] = {
                "home": home,
                "away": away,
                "date": current_date,
                "kickoff_utc": kickoff_utc,
                "kickoff_local": kickoff_time,
                "uk_blackout": uk_blackout,
                "uk_broadcaster": uk_broadcaster,
                "uk_channels": uk_channels,
                "matchday": current_matchday,
                "competition": "EPL",
                "fixture_key": key,
            }
            continue

        # Check fixture without time (likely 15:00 Saturday blackout)
        m = fixture_no_time.match(line)
        if m and current_day_of_week == "saturday":
            home_raw = m.group(1).strip()
            away_raw = m.group(2).strip()

            # Skip if looks like a header or navigation element
            if len(home_raw) < 3 or len(away_raw) < 3:
                continue
            if any(c.isdigit() for c in home_raw + away_raw):
                continue

            home = _canonical_team(home_raw)
            away = _canonical_team(away_raw)
            key = _make_key(home, away)

            kickoff_time = "15:00"
            kickoff_utc = _bst_to_utc(current_date, kickoff_time)

            results[key] = {
                "home": home,
                "away": away,
                "date": current_date,
                "kickoff_utc": kickoff_utc,
                "kickoff_local": kickoff_time,
                "uk_blackout": True,  # Saturday 15:00 = always blackout
                "uk_broadcaster": None,
                "uk_channels": [],
                "matchday": current_matchday,
                "competition": "EPL",
                "fixture_key": key,
            }

    logger.info(f"Scraped {len(results)} EPL fixtures from PL fixture changes page")
    return results


def _parse_sky_channels(text: str) -> list:
    """Extract specific Sky Sports channels from text."""
    channels = []
    channel_names = [
        "Sky Sports Main Event",
        "Sky Sports Premier League",
        "Sky Sports Football",
        "Sky Sports Action",
        "Sky Sports Ultra HDR",
        "Sky Sports+",
    ]
    for ch in channel_names:
        if ch.lower() in text.lower():
            channels.append(ch)
    if not channels and "Sky Sports" in text:
        channels = ["Sky Sports Main Event", "Sky Sports Premier League"]
    return channels


def get_all_fixtures(days_ahead: int = 30) -> dict:
    """
    Get all EPL fixtures for the next days_ahead days.
    Uses PL fixture changes page as primary, falls back to live-footballontv.com.
    """
    fixtures = scrape_fixture_changes()

    if len(fixtures) < 5:
        logger.warning("PL fixture changes returned few results, trying backup source")
        # Import backup scraper
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from sources.uk_live_footballontv import scrape as scrape_lftv
        backup = scrape_lftv("EPL")
        for key, data in backup.items():
            if key not in fixtures:
                fixtures[key] = data
        logger.info(f"After backup: {len(fixtures)} total EPL fixtures")

    # Filter to date window
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    filtered = {}
    for key, fx in fixtures.items():
        try:
            fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            if today <= fx_date <= cutoff:
                filtered[key] = fx
        except Exception:
            filtered[key] = fx  # Include if date can't be parsed

    logger.info(f"Filtered to {len(filtered)} EPL fixtures in next {days_ahead} days")
    return filtered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fixtures = get_all_fixtures(30)
    print(f"\nTotal EPL fixtures (30 days): {len(fixtures)}")
    for key, fx in sorted(fixtures.items(), key=lambda x: x[1].get("date", "")):
        blackout = "🚫 BLACKOUT" if fx.get("uk_blackout") else f"📺 {fx.get('uk_broadcaster', 'TBC')}"
        print(f"  {fx['date']} {fx['kickoff_local']}  {fx['home']} v {fx['away']}  {blackout}  MW{fx.get('matchday', '?')}")
