"""
sources/asia_scrapers.py
=========================
Scrapes Asian broadcaster schedules for EPL and UCL channel assignments.

Sources:
  - content.astro.com.my → Astro Malaysia (Astro SuperSport 2/3)
  - thesportsdb.com → Star Sports India, beIN Sports channel data
  
beIN Sports channel logic (applied programmatically):
  - Biggest match of the day → beIN Sports HD 1 (flagship)
  - Second match → beIN Sports HD 2
  - Simultaneous games → beIN Sports HD 3, HD 4, HD 5
  - Determined by fixture importance ranking
"""

import re
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional
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

# Astro channel URLs (static HTML)
ASTRO_CHANNELS = {
    "Astro SuperSport 2": "https://content.astro.com.my/channels/beIN-SPORTS-1-236",
    "Astro SuperSport 3": "https://content.astro.com.my/channels/beIN-SPORTS-2-237",
}

# thesportsdb Star Sports channels
THESPORTSDB_CHANNELS = {
    "Star Sports Select HD1": (
        "https://www.thesportsdb.com/channel/1582-star-sports-select-hd1-Schedule"
    ),
}

# beIN importance ranking for channel assignment
# Higher = more important = lower channel number (HD 1 is flagship)
TEAM_IMPORTANCE = {
    "Liverpool": 10, "Manchester City": 10, "Arsenal": 10,
    "Chelsea": 9, "Manchester United": 9, "Tottenham Hotspur": 8,
    "Newcastle United": 8, "Aston Villa": 7, "West Ham United": 7,
    "Paris Saint-Germain": 10, "Real Madrid": 10, "Barcelona": 10,
    "Bayern Munich": 10, "Atlético Madrid": 9, "Sporting CP": 7,
    "Brentford": 5, "Fulham": 5, "Crystal Palace": 5,
    "Everton": 6, "Nottingham Forest": 6, "Leeds United": 6,
    "Sunderland": 5, "Burnley": 5, "Brighton": 6,
    "Wolverhampton Wanderers": 5, "AFC Bournemouth": 5,
}


def _get_fixture_importance(home: str, away: str) -> int:
    """Return importance score for channel assignment."""
    h = TEAM_IMPORTANCE.get(home, 5)
    a = TEAM_IMPORTANCE.get(away, 5)
    return h + a


def assign_bein_channels(fixtures: list) -> list:
    """
    Assign beIN Sports HD channel numbers based on fixture importance.
    Fixtures on same date/time get ranked: highest importance → HD 1.
    Returns fixtures with bein_channel added.
    """
    # Group by date
    by_date = {}
    for fx in fixtures:
        d = fx.get("date", "")
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(fx)

    result = []
    for d, day_fixtures in by_date.items():
        # Sort by importance descending
        day_fixtures.sort(
            key=lambda f: _get_fixture_importance(f.get("home", ""), f.get("away", "")),
            reverse=True
        )
        for i, fx in enumerate(day_fixtures):
            fx["bein_channel"] = f"beIN Sports HD {i + 1}"
            fx["bein_channel_num"] = i + 1
            result.append(fx)

    return result


def scrape_astro(days_ahead: int = 30) -> dict:
    """
    Scrape Astro Malaysia channel pages for EPL/UCL schedule.
    Returns { fixture_key: { astro_channel, date, kickoff_utc } }
    """
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    results = {}

    for channel_name, url in ASTRO_CHANNELS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            logger.warning(f"Failed to fetch Astro {channel_name}: {e}")
            continue

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Astro pages list upcoming matches in format:
        # "Arsenal vs Chelsea" + date/time text
        vs_pattern = re.compile(r"^(.+?)\s+(?:vs\.?|v)\s+(.+?)$", re.IGNORECASE)
        time_pattern = re.compile(r"(\d{1,2}:\d{2})\s*(AM|PM|am|pm)?")
        date_pattern = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4})")

        MONTH_MAP = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        current_date = None
        current_time = None

        for i, line in enumerate(lines):
            dm = date_pattern.search(line)
            if dm:
                day = int(dm.group(1))
                month = MONTH_MAP.get(dm.group(2).lower(), 0)
                year = int(dm.group(3))
                if month:
                    try:
                        current_date = date(year, month, day).strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                continue

            tm = time_pattern.search(line)
            if tm:
                current_time = tm.group(1)
                continue

            vm = vs_pattern.match(line)
            if vm and current_date:
                home = vm.group(1).strip()
                away = vm.group(2).strip()

                if len(home) < 3 or len(away) < 3:
                    continue
                if any(c.isdigit() for c in home + away):
                    continue

                key = f"{home.lower()} v {away.lower()}"
                kickoff_utc = None
                if current_time:
                    # Astro times are in MYT (UTC+8)
                    try:
                        dt = datetime.strptime(
                            f"{current_date} {current_time}", "%Y-%m-%d %H:%M"
                        )
                        dt_utc = dt - timedelta(hours=8)
                        kickoff_utc = dt_utc.replace(tzinfo=timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except Exception:
                        pass

                if key not in results:
                    results[key] = {
                        "home": home,
                        "away": away,
                        "date": current_date,
                        "kickoff_utc": kickoff_utc,
                        "astro_channel": channel_name,
                        "malaysia_broadcaster": "Astro",
                    }

        logger.info(f"Found fixtures on Astro {channel_name}: scraped")

    logger.info(f"Total Astro fixtures: {len(results)}")
    return results


def scrape_star_sports(days_ahead: int = 30) -> dict:
    """
    Scrape thesportsdb for Star Sports India channel schedule.
    Returns { fixture_key: { star_channel, date, kickoff_utc } }
    """
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    results = {}

    for channel_name, url in THESPORTSDB_CHANNELS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            logger.warning(f"Failed to fetch {channel_name}: {e}")
            continue

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # thesportsdb format: "Home vs Away (HH:MM UTC - Day DD Mon YYYY)"
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
                fx_date = dt_utc.date()
                if not (today <= fx_date <= cutoff):
                    continue
                date_str = dt_utc.strftime("%Y-%m-%d")
                kickoff_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue

            key = f"{home.lower()} v {away.lower()}"
            results[key] = {
                "home": home,
                "away": away,
                "date": date_str,
                "kickoff_utc": kickoff_utc,
                "india_channel": channel_name,
                "india_broadcaster": "JioStar / StarSports",
            }

    logger.info(f"Total Star Sports fixtures: {len(results)}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n── Astro Malaysia ──")
    astro = scrape_astro(30)
    print(f"Found: {len(astro)} fixtures")

    print("\n── Star Sports India ──")
    star = scrape_star_sports(30)
    print(f"Found: {len(star)} fixtures")

    print("\n── beIN channel assignment test ──")
    test_fixtures = [
        {"home": "Liverpool", "away": "PSG", "date": "2026-04-14"},
        {"home": "Atlético Madrid", "away": "Barcelona", "date": "2026-04-14"},
        {"home": "Arsenal", "away": "Bournemouth", "date": "2026-04-11"},
    ]
    ranked = assign_bein_channels(test_fixtures)
    for fx in ranked:
        print(f"  {fx['home']} v {fx['away']} → {fx['bein_channel']}")
