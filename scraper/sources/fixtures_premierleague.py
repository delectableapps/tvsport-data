"""
sources/fixtures_premierleague.py
===================================
Gets EPL fixtures using thesportsdb.com API (correct match dates)
supplemented by live-footballontv.com for UK broadcaster info.

TheSportsDB league ID for EPL: 4328
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

# TheSportsDB — EPL league ID 4328, season 2025-2026
TSDB_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsseason.php?id=4328&s=2025-2026"

# UK broadcaster info
LFTV_URL = "https://www.live-footballontv.com/live-premier-league-football-on-tv.html"

# PL fixture changes for blackout + matchday
PL_FIXTURE_CHANGES_URL = (
    "https://www.premierleague.com/en/news/4606462/"
    "premier-league-fixture-changes-announced-for-april-2026"
)

EPL_TEAMS_2526 = [
    "Arsenal", "Aston Villa", "AFC Bournemouth", "Brentford", "Brighton",
    "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham",
    "Leeds United", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Sunderland",
    "Tottenham Hotspur", "West Ham United", "Wolverhampton Wanderers",
]

TEAM_ALIASES = {
    "wolves": "Wolverhampton Wanderers",
    "wolverhampton wanderers": "Wolverhampton Wanderers",
    "wolverhampton": "Wolverhampton Wanderers",
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "newcastle": "Newcastle United",
    "newcastle utd": "Newcastle United",
    "nott'm forest": "Nottingham Forest",
    "notts forest": "Nottingham Forest",
    "nottm forest": "Nottingham Forest",
    "nottingham forest": "Nottingham Forest",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "tottenham hotspur": "Tottenham Hotspur",
    "west ham": "West Ham United",
    "west ham united": "West Ham United",
    "bournemouth": "AFC Bournemouth",
    "afc bournemouth": "AFC Bournemouth",
    "brighton": "Brighton",
    "brighton & hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "leeds": "Leeds United",
    "leeds united": "Leeds United",
    "sunderland afc": "Sunderland",
}


def _normalise(name: str) -> str:
    n = name.strip().lower().replace("&", "and").replace(".", "").replace("'", "").replace("-", " ")
    return TEAM_ALIASES.get(n, n)


def _canonical_team(name: str) -> str:
    n = _normalise(name)
    for team in EPL_TEAMS_2526:
        if _normalise(team) == n:
            return team
    for team in EPL_TEAMS_2526:
        if n in _normalise(team) or _normalise(team) in n:
            return team
    return name.strip()


def _make_key(home: str, away: str) -> str:
    return f"{_normalise(home)} v {_normalise(away)}"


def _bst_to_utc(date_str: str, time_bst: str) -> str:
    """BST (UTC+1 in April-October) to UTC."""
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        month = dt.month
        offset = 1 if 3 < month < 11 else 0
        dt_utc = dt - timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _is_saturday_3pm_blackout(date_str: str, time_bst: str) -> bool:
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        return dt.weekday() == 5 and time_bst == "15:00"
    except Exception:
        return False


def _parse_sky_channels(text: str) -> list:
    channels = []
    for ch in ["Sky Sports Main Event", "Sky Sports Premier League",
               "Sky Sports Football", "Sky Sports Action", "Sky Sports Ultra HDR"]:
        if ch.lower() in text.lower():
            channels.append(ch)
    if not channels and "Sky Sports" in text:
        channels = ["Sky Sports Main Event", "Sky Sports Premier League"]
    return channels


def scrape_tsdb() -> dict:
    """
    Fetch EPL fixtures from thesportsdb.com API.
    Returns { fixture_key: fixture_dict } with correct dates.
    """
    try:
        r = requests.get(TSDB_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error(f"TheSportsDB API failed: {e}")
        return {}

    events = data.get("events") or []
    if not events:
        logger.warning("TheSportsDB returned no events for EPL")
        return {}

    results = {}
    today = date.today()
    cutoff = today + timedelta(days=30)

    for ev in events:
        try:
            date_str = ev.get("dateEvent", "")
            time_str = ev.get("strTime", "00:00:00")[:5]  # "HH:MM"
            home_raw = ev.get("strHomeTeam", "")
            away_raw = ev.get("strAwayTeam", "")

            if not date_str or not home_raw or not away_raw:
                continue

            # Filter to upcoming fixtures in window
            fx_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if fx_date < today or fx_date > cutoff:
                continue

            home = _canonical_team(home_raw)
            away = _canonical_team(away_raw)
            key = _make_key(home, away)

            # Convert UTC time from API to BST for display
            # TheSportsDB returns times in UTC
            try:
                dt_utc = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                month = dt_utc.month
                bst_offset = 1 if 3 < month < 11 else 0
                dt_bst = dt_utc + timedelta(hours=bst_offset)
                kickoff_local = dt_bst.strftime("%H:%M")
                kickoff_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                # Use BST date for blackout check
                bst_date = dt_bst.strftime("%Y-%m-%d")
            except Exception:
                kickoff_local = time_str
                kickoff_utc = f"{date_str}T{time_str}:00Z"
                bst_date = date_str

            uk_blackout = _is_saturday_3pm_blackout(bst_date, kickoff_local)

            results[key] = {
                "home": home,
                "away": away,
                "date": bst_date,
                "kickoff_utc": kickoff_utc,
                "kickoff_local": kickoff_local,
                "uk_blackout": uk_blackout,
                "uk_broadcaster": None,
                "uk_channels": [],
                "matchday": ev.get("intRound"),
                "competition": "EPL",
                "fixture_key": key,
            }
        except Exception as e:
            logger.debug(f"Skipping event: {e}")
            continue

    logger.info(f"TheSportsDB returned {len(results)} EPL fixtures in next 30 days")
    return results


def scrape_lftv_channels() -> dict:
    """
    Scrape live-footballontv.com for UK broadcaster assignments only.
    Returns { fixture_key: { uk_broadcaster, uk_channels, uk_blackout } }
    """
    try:
        r = requests.get(LFTV_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"live-footballontv.com failed: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    results = {}

    for row in soup.find_all(["tr", "li", "div", "p"]):
        text = row.get_text(separator=" ", strip=True)

        # Match: "12:30 Brentford v Fulham TNT Sports 1"
        m = re.search(
            r"(\d{2}:\d{2})\s+([A-Z][^vV\d]+?)\s+v\s+([A-Z][^vV\d]+?)\s+"
            r"(Sky Sports|TNT Sports|BBC|ITV|Amazon)",
            text
        )
        if m:
            home = _canonical_team(m.group(2).strip())
            away = _canonical_team(m.group(3).strip())
            broadcaster = m.group(4)
            key = _make_key(home, away)

            uk_channels = []
            if "Sky Sports" in broadcaster:
                uk_channels = _parse_sky_channels(text)
            elif "TNT" in broadcaster:
                uk_channels = ["TNT Sports 1", "TNT Sports Ultimate", "HBO Max"]
            elif "BBC" in broadcaster:
                uk_channels = ["BBC One", "BBC iPlayer"]

            results[key] = {
                "uk_broadcaster": broadcaster,
                "uk_channels": uk_channels,
            }

    logger.info(f"live-footballontv.com: found {len(results)} UK channel assignments")
    return results


def scrape_fixture_changes() -> dict:
    """
    Scrape PL fixture changes page for blackout flags and matchday numbers.
    """
    try:
        r = requests.get(PL_FIXTURE_CHANGES_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"PL fixture changes failed: {e}")
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

    matchday_pat = re.compile(r"^MW(\d+)$")
    date_pat = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(\d{1,2})\s+(\w+)(?:\s+\d{4})?$", re.IGNORECASE
    )
    fix_pat = re.compile(r"^(\d{2}:\d{2})\s+(.+?)\s+v\s+(.+?)(?:\s+\((.+?)\))?$")
    notime_pat = re.compile(
        r"^([A-Z][a-zA-Z\s\']+?)\s+v\s+([A-Z][a-zA-Z\s\']+?)(?:\s+\*+)?$"
    )

    current_date = None
    current_matchday = None
    current_dow = None
    year = date.today().year

    for line in lines:
        m = matchday_pat.match(line)
        if m:
            current_matchday = int(m.group(1))
            continue

        m = date_pat.match(line)
        if m:
            current_dow = m.group(1).lower()
            day_num = int(m.group(2))
            month_num = MONTH_MAP.get(m.group(3).lower(), 0)
            if month_num:
                adj_year = year + 1 if month_num < date.today().month - 2 else year
                try:
                    current_date = date(adj_year, month_num, day_num).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            continue

        if not current_date:
            continue

        m = fix_pat.match(line)
        if m:
            home = _canonical_team(m.group(2).strip())
            away = _canonical_team(m.group(3).strip())
            key = _make_key(home, away)
            results[key] = {
                "matchday": current_matchday,
                "uk_blackout": _is_saturday_3pm_blackout(current_date, m.group(1)),
            }
            broadcaster_raw = m.group(4) or ""
            if "Sky Sports" in broadcaster_raw:
                results[key]["uk_broadcaster"] = "Sky Sports"
                results[key]["uk_channels"] = _parse_sky_channels(broadcaster_raw)
            elif "TNT" in broadcaster_raw:
                results[key]["uk_broadcaster"] = "TNT Sports"
                results[key]["uk_channels"] = ["TNT Sports 1", "TNT Sports Ultimate", "HBO Max"]
            continue

        m = notime_pat.match(line)
        if m and current_dow == "saturday":
            home = _canonical_team(m.group(1).strip())
            away = _canonical_team(m.group(2).strip())
            if len(m.group(1)) < 3 or len(m.group(2)) < 3:
                continue
            if any(c.isdigit() for c in m.group(1) + m.group(2)):
                continue
            key = _make_key(home, away)
            results[key] = {
                "matchday": current_matchday,
                "uk_blackout": True,
            }

    logger.info(f"PL fixture changes: found {len(results)} entries")
    return results


def get_all_fixtures(days_ahead: int = 30) -> dict:
    """
    Get all EPL fixtures for the next days_ahead days.
    Primary: TheSportsDB API (correct dates and times)
    Supplement: live-footballontv.com (UK broadcaster info)
    Supplement: PL fixture changes page (blackout flags + matchday)
    """
    # Step 1: Get fixtures with correct dates from TheSportsDB
    fixtures = scrape_tsdb()

    if len(fixtures) < 5:
        logger.warning("TheSportsDB returned few EPL fixtures, check API")

    # Step 2: Add UK broadcaster info from live-footballontv.com
    try:
        lftv = scrape_lftv_channels()
        for key, data in lftv.items():
            if key in fixtures:
                fixtures[key]["uk_broadcaster"] = data.get("uk_broadcaster")
                fixtures[key]["uk_channels"] = data.get("uk_channels", [])
    except Exception as e:
        logger.warning(f"live-footballontv.com supplement failed: {e}")

    # Step 3: Add blackout flags + matchday from PL fixture changes
    try:
        pl = scrape_fixture_changes()
        for key, data in pl.items():
            if key in fixtures:
                if data.get("matchday"):
                    fixtures[key]["matchday"] = data["matchday"]
                if data.get("uk_blackout"):
                    fixtures[key]["uk_blackout"] = True
                if data.get("uk_broadcaster") and not fixtures[key].get("uk_broadcaster"):
                    fixtures[key]["uk_broadcaster"] = data["uk_broadcaster"]
                if data.get("uk_channels") and not fixtures[key].get("uk_channels"):
                    fixtures[key]["uk_channels"] = data["uk_channels"]
    except Exception as e:
        logger.warning(f"PL fixture changes supplement failed: {e}")

    # Step 4: Filter to date window
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    filtered = {}
    for key, fx in fixtures.items():
        try:
            fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            if today <= fx_date <= cutoff:
                filtered[key] = fx
        except Exception:
            filtered[key] = fx

    logger.info(f"Filtered to {len(filtered)} EPL fixtures in next {days_ahead} days")
    return filtered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fixtures = get_all_fixtures(30)
    print(f"\nTotal EPL fixtures (30 days): {len(fixtures)}")
    for key, fx in sorted(fixtures.items(), key=lambda x: x[1].get("date", "")):
        blackout = "🚫 BLACKOUT" if fx.get("uk_blackout") else f"📺 {fx.get('uk_broadcaster', 'TBC')}"
        print(f"  {fx['date']} {fx['kickoff_local']}  {fx['home']} v {fx['away']}  {blackout}  MW{fx.get('matchday', '?')}")
