"""
sources/africa_supersport.py
==============================
Scrapes thesportsdb.com for SuperSport channel schedules (Sub-Saharan Africa).
SuperSport holds EPL and UCL rights across ~48 Sub-Saharan African territories.

SuperSport channels relevant to us:
  - SuperSport Premier League (DStv #203) → EPL
  - SuperSport Football (DStv #205) → UCL + overflow EPL
  - SuperSport Variety 1/2/3/4 → overflow

Source: https://www.thesportsdb.com/channel/1873-supersport-premier-league-Schedule
        https://www.thesportsdb.com/channel/1167-supersport-football-Schedule
"""

import re
import logging
from datetime import datetime, timezone, timedelta, date
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
}

CHANNEL_URLS = {
    "SuperSport Premier League": (
        "https://www.thesportsdb.com/channel/1873-supersport-premier-league-Schedule"
    ),
    "SuperSport Football": (
        "https://www.thesportsdb.com/channel/1167-supersport-football-Schedule"
    ),
}


def _normalise(name: str) -> str:
    return (name.strip().lower()
               .replace("&", "and")
               .replace(".", "")
               .replace("'", "")
               .replace("-", " "))


def _make_key(home: str, away: str) -> str:
    return f"{_normalise(home)} v {_normalise(away)}"


def scrape_channel(channel_name: str, url: str) -> list:
    """
    Scrape a TheSportsDB channel schedule page.
    Returns list of { fixture_key, home, away, date, kickoff_utc, channel }
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch {channel_name}: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    results = []
    TARGET_COMPS = {"premier league", "champions league", "ucl", "epl"}

    # thesportsdb format:
    # "Home vs Away (HH:MM UTC - Day DD Mon YYYY)"
    fixture_pattern = re.compile(
        r"^(.+?)\s+vs\s+(.+?)\s+\((\d{2}:\d{2})\s+UTC\s+-\s+"
        r"(\w{3})\s+(\d{2})\s+(\w{3})\s+(\d{4})\)$",
        re.IGNORECASE
    )

    MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    for line in lines:
        m = fixture_pattern.match(line)
        if not m:
            continue

        home = m.group(1).strip()
        away = m.group(2).strip()
        time_utc = m.group(3)
        day_abbr = m.group(4)
        day_num = int(m.group(5))
        month_abbr = m.group(6).lower()
        year = int(m.group(7))

        month_num = MONTH_MAP.get(month_abbr, 0)
        if not month_num:
            continue

        try:
            dt_utc = datetime(year, month_num, day_num,
                              int(time_utc[:2]), int(time_utc[3:]),
                              tzinfo=timezone.utc)
            kickoff_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            date_str = dt_utc.strftime("%Y-%m-%d")
        except Exception:
            continue

        fixture_key = _make_key(home, away)
        results.append({
            "fixture_key": fixture_key,
            "home": home,
            "away": away,
            "date": date_str,
            "kickoff_utc": kickoff_utc,
            "africa_channel": channel_name,
            "africa_broadcaster": "SuperSport",
        })

    logger.info(f"Found {len(results)} fixtures on {channel_name}")
    return results


def scrape_all(days_ahead: int = 30) -> dict:
    """
    Scrape all SuperSport channels.
    Returns { fixture_key: { africa_broadcaster, africa_channels } }
    """
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    all_fixtures = {}

    for channel_name, url in CHANNEL_URLS.items():
        fixtures = scrape_channel(channel_name, url)
        for fx in fixtures:
            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
                if not (today <= fx_date <= cutoff):
                    continue
            except Exception:
                pass

            key = fx["fixture_key"]
            if key not in all_fixtures:
                all_fixtures[key] = {
                    "africa_broadcaster": "SuperSport",
                    "africa_channels": [],
                    "date": fx["date"],
                    "kickoff_utc": fx["kickoff_utc"],
                }

            ch = fx["africa_channel"]
            if ch not in all_fixtures[key]["africa_channels"]:
                all_fixtures[key]["africa_channels"].append(ch)

    # Assign DStv channel numbers
    for key, data in all_fixtures.items():
        channels = data["africa_channels"]
        if "SuperSport Premier League" in channels:
            data["africa_channel_display"] = "SuperSport Premier League (DStv #203)"
        elif "SuperSport Football" in channels:
            data["africa_channel_display"] = "SuperSport Football (DStv #205)"
        else:
            data["africa_channel_display"] = "SuperSport"

    logger.info(f"Total SuperSport fixtures for next {days_ahead} days: {len(all_fixtures)}")
    return all_fixtures


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_all(30)
    print(f"\nTotal Africa fixtures: {len(results)}")
    for key, data in list(results.items())[:8]:
        print(f"  {data['date']}  {key}  →  {data['africa_channel_display']}")
