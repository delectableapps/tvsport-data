"""
sources/fixtures_premierleague.py - RESTORED ORIGINAL
"""

import re
import logging
from datetime import date, datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}

PL_FIXTURE_CHANGES_URL = (
    "https://www.premierleague.com/en/news/4606462/"
    "premier-league-fixture-changes-announced-for-april-2026"
)

PL_FULL_SCHEDULE_URL = "https://www.live-footballontv.com/live-premier-league-football-on-tv.html"

EPL_TEAMS_2526 = [
    "Arsenal", "Aston Villa", "AFC Bournemouth", "Brentford", "Brighton",
    "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham",
    "Leeds United", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Sunderland",
    "Tottenham Hotspur", "West Ham United", "Wolverhampton Wanderers",
]

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


def _normalise(name):
    n = name.strip().lower().replace("&", "and").replace(".", "").replace("'", "").replace("-", " ")
    return TEAM_ALIASES.get(n, n)


def _canonical_team(name):
    n = _normalise(name)
    for team in EPL_TEAMS_2526:
        if _normalise(team) == n:
            return team
    for team in EPL_TEAMS_2526:
        if n in _normalise(team) or _normalise(team) in n:
            return team
    return name.title()


def _make_key(home, away):
    return f"{_normalise(home)} v {_normalise(away)}"


def _bst_to_utc(date_str, time_bst):
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        offset = 1 if 3 < dt.month < 11 else 0
        dt_utc = dt - timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _is_saturday_3pm_blackout(date_str, time_bst):
    try:
        dt = datetime.strptime(f"{date_str} {time_bst}", "%Y-%m-%d %H:%M")
        return dt.weekday() == 5 and time_bst == "15:00"
    except Exception:
        return False


def _parse_sky_channels(text):
    channels = []
    for ch in ["Sky Sports Main Event", "Sky Sports Premier League",
               "Sky Sports Football", "Sky Sports Action", "Sky Sports Ultra HDR", "Sky Sports+"]:
        if ch.lower() in text.lower():
            channels.append(ch)
    if not channels and "Sky Sports" in text:
        channels = ["Sky Sports Main Event", "Sky Sports Premier League"]
    return channels


def scrape_fixture_changes():
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

    matchday_pat = re.compile(r"^MW(\d+)$")
    date_pat = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})\s+(\w+)(?:\s+\d{4})?$",
        re.IGNORECASE
    )
    fix_time_pat = re.compile(r"^(\d{2}:\d{2})\s+(.+?)\s+v\s+(.+?)(?:\s+\((.+?)\))?$")
    fix_notime_pat = re.compile(r"^([A-Z][a-zA-Z\s\']+?)\s+v\s+([A-Z][a-zA-Z\s\']+?)(?:\s+\*+)?$")

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

        m = fix_time_pat.match(line)
        if m:
            kickoff_time = m.group(1)
            home = _canonical_team(m.group(2).strip())
            away = _canonical_team(m.group(3).strip())
            broadcaster_raw = m.group(4) or ""
            key = _make_key(home, away)
            uk_broadcaster = None
            uk_channels = []
            if "Sky Sports" in broadcaster_raw:
                uk_broadcaster = "Sky Sports"
                uk_channels = _parse_sky_channels(broadcaster_raw)
            elif "TNT" in broadcaster_raw:
                uk_broadcaster = "TNT Sports"
                uk_channels = ["TNT Sports 1", "TNT Sports Ultimate", "HBO Max"]
            results[key] = {
                "home": home, "away": away, "date": current_date,
                "kickoff_utc": _bst_to_utc(current_date, kickoff_time),
                "kickoff_local": kickoff_time,
                "uk_blackout": _is_saturday_3pm_blackout(current_date, kickoff_time),
                "uk_broadcaster": uk_broadcaster, "uk_channels": uk_channels,
                "matchday": current_matchday, "competition": "EPL", "fixture_key": key,
            }
            continue

        m = fix_notime_pat.match(line)
        if m and current_dow == "saturday":
            home_raw = m.group(1).strip()
            away_raw = m.group(2).strip()
            if len(home_raw) < 3 or len(away_raw) < 3:
                continue
            if any(c.isdigit() for c in home_raw + away_raw):
                continue
            home = _canonical_team(home_raw)
            away = _canonical_team(away_raw)
            key = _make_key(home, away)
            results[key] = {
                "home": home, "away": away, "date": current_date,
                "kickoff_utc": _bst_to_utc(current_date, "15:00"),
                "kickoff_local": "15:00", "uk_blackout": True,
                "uk_broadcaster": None, "uk_channels": [],
                "matchday": current_matchday, "competition": "EPL", "fixture_key": key,
            }

    logger.info(f"Scraped {len(results)} EPL fixtures from PL fixture changes page")
    return results


def get_all_fixtures(days_ahead=30):
    fixtures = scrape_fixture_changes()

    if len(fixtures) < 5:
        logger.warning("PL fixture changes returned few results, trying backup source")
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from sources.uk_live_footballontv import scrape as scrape_lftv
        backup = scrape_lftv("EPL")
        for key, data in backup.items():
            if key not in fixtures:
                fixtures[key] = data
        logger.info(f"After backup: {len(fixtures)} total EPL fixtures")

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
        blackout = "BLACKOUT" if fx.get("uk_blackout") else fx.get("uk_broadcaster", "TBC")
        print(f"  {fx['date']} {fx['kickoff_local']}  {fx['home']} v {fx['away']}  {blackout}")
