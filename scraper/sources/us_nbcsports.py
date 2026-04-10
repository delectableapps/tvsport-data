"""
sources/us_nbcsports.py
========================
Scrapes NBC Sports for US EPL channel assignments (NBC / USA Network / Peacock).
Source: https://www.nbcsports.com/soccer/news/premier-league-2025-26-fixtures-...

Also handles CBS Sports for UCL US assignments.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
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
    "Accept-Language": "en-US,en;q=0.9",
}

NBC_EPL_URL = (
    "https://www.nbcsports.com/soccer/news/"
    "premier-league-2025-26-fixtures-released-dates-schedule-how-to-watch-live"
)

CBS_UCL_URL = (
    "https://www.cbssports.com/soccer/news/"
    "champions-league-live-stream-schedule-how-to-watch-quarterfinals/"
)


def _normalise_team(name: str) -> str:
    replacements = {
        "wolverhampton wanderers": "wolverhampton",
        "wolverhampton w": "wolverhampton",
        "manchester city": "manchester city",
        "manchester united": "manchester united",
        "nottingham forest": "nottingham forest",
        "afc bournemouth": "afc bournemouth",
        "brighton & hove albion": "brighton",
        "brighton and hove albion": "brighton",
        "tottenham hotspur": "tottenham hotspur",
        "newcastle united": "newcastle united",
    }
    n = name.strip().lower().replace("&", "and").replace(".", "").replace("'", "").replace("-", " ")
    return replacements.get(n, n)


def _make_fixture_key(home: str, away: str) -> str:
    return f"{_normalise_team(home)} v {_normalise_team(away)}"


def _et_to_utc(date_str: str, time_str: str, ampm: str) -> str:
    """Convert ET time to UTC. ET = UTC-5 (EST) or UTC-4 (EDT, Mar-Nov)."""
    try:
        hour, minute = map(int, time_str.split(":"))
        if ampm.lower() == "pm" and hour != 12:
            hour += 12
        elif ampm.lower() == "am" and hour == 12:
            hour = 0
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
        # April = EDT (UTC-4)
        month = dt.month
        offset = 4 if 3 <= month <= 11 else 5
        dt_utc = dt + timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        logger.debug(f"ET→UTC conversion failed: {e}")
        return None


def scrape_epl() -> dict:
    """
    Scrape NBC Sports EPL schedule page.
    Returns { fixture_key: { us_channels, us_broadcaster, kickoff_utc_approx } }

    NBC pattern examples from page:
    "Friday 10 April 3pm ET: West Ham United v Wolverhampton Wanderers — Watch on USA"
    "Saturday 11 April 7:30am ET: Arsenal v AFC Bournemouth — Watch on USA"
    "Saturday 11 April 10am ET: Brentford v Everton — Watch live on Peacock"
    "Saturday 11 April 12:30pm ET: Liverpool v Fulham — NBC — Watch online via NBC.com & Watch live on Peacock"
    """
    try:
        r = requests.get(NBC_EPL_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch NBC Sports: {e}")
        return {}

    results = {}

    # Pattern to match fixture lines
    # "Day DD Month HH:MMam/pm ET: Team1 v Team2 — Watch on CHANNEL"
    fixture_pattern = re.compile(
        r"(\w+day)\s+(\d{1,2})\s+(\w+)\s+"      # Day DD Month
        r"(\d{1,2}(?::\d{2})?)(am|pm)\s+ET:\s+"  # Time ET:
        r"([^—]+?)\s*[—-]+\s*"                    # Teams —
        r"(.+?)(?:\n|$)",                          # Channel info
        re.IGNORECASE
    )

    MONTH_MAP = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }

    # Extract text from page
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")

    # Find the schedule section
    schedule_start = text.find("Friday 10 April")
    if schedule_start == -1:
        schedule_start = text.find("Saturday 11 April")
    if schedule_start == -1:
        # Search for any upcoming date
        schedule_start = 0

    text_section = text[max(0, schedule_start - 200):]

    for match in fixture_pattern.finditer(text_section):
        day_name = match.group(1)
        day_num = int(match.group(2))
        month_name = match.group(3).lower()
        time_str = match.group(4)
        ampm = match.group(5)
        teams_raw = match.group(6).strip()
        channel_raw = match.group(7).strip()

        month_num = MONTH_MAP.get(month_name, 0)
        if not month_num:
            continue

        from datetime import date
        year = date.today().year
        if month_num < date.today().month - 1:
            year += 1

        try:
            date_str = f"{year}-{month_num:02d}-{day_num:02d}"
        except Exception:
            continue

        # Normalise time (handle "7:30" and "3" formats)
        if ":" not in time_str:
            time_str = f"{time_str}:00"

        kickoff_utc = _et_to_utc(date_str, time_str, ampm)

        # Parse teams
        if " v " in teams_raw:
            parts = teams_raw.split(" v ", 1)
        elif " vs " in teams_raw.lower():
            parts = re.split(r"\s+vs\.?\s+", teams_raw, 1, re.IGNORECASE)
        else:
            continue

        if len(parts) != 2:
            continue

        home = parts[0].strip()
        away = parts[1].strip()
        fixture_key = _make_fixture_key(home, away)

        # Parse US channel
        channels = []
        broadcaster = "NBC Sports / Peacock"

        channel_lower = channel_raw.lower()
        if "nbc " in channel_lower or channel_raw.strip() == "NBC":
            channels = ["NBC", "Peacock"]
        elif "usa" in channel_lower:
            channels = ["USA Network", "Peacock"]
        elif "peacock" in channel_lower:
            channels = ["Peacock"]
        elif "telemundo" in channel_lower:
            channels = ["Telemundo", "Peacock"]
            broadcaster = "Telemundo / NBC"
        else:
            channels = ["Peacock"]  # Default

        results[fixture_key] = {
            "home": home,
            "away": away,
            "date": date_str,
            "kickoff_utc": kickoff_utc,
            "us_broadcaster": broadcaster,
            "us_channels": " · ".join(channels),
        }

    logger.info(f"Scraped {len(results)} EPL fixtures from NBC Sports")
    return results


def scrape_ucl() -> dict:
    """
    Scrape CBS Sports UCL schedule for US channel assignments.
    UCL in US: Paramount+ (streaming), CBS Sports Network, CBS (big matches)
    Returns { fixture_key: { us_channels, us_broadcaster } }
    """
    try:
        r = requests.get(CBS_UCL_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch CBS Sports: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    results = {}

    # CBS pattern: "Home vs Away — Paramount+ / CBS Sports"
    fixture_pattern = re.compile(
        r"([A-Z][a-zA-Z\s\.]+?)\s+(?:vs?\.?|v)\s+([A-Z][a-zA-Z\s\.]+?)"
        r"\s*[—-]+\s*(Paramount\+.*?|CBS.*?)(?:\n|$)",
        re.IGNORECASE
    )

    for match in fixture_pattern.finditer(text):
        home = match.group(1).strip()
        away = match.group(2).strip()
        channel_raw = match.group(3).strip()

        # Only keep football team names (filter out garbage)
        if len(home) < 3 or len(away) < 3:
            continue
        if any(c.isdigit() for c in home + away):
            continue

        fixture_key = _make_fixture_key(home, away)

        channels_str = channel_raw
        if "CBS Sports" in channel_raw and "Paramount" in channel_raw:
            channels_str = "Paramount+ · CBS Sports Network"
        elif "Paramount" in channel_raw:
            channels_str = "Paramount+"
        elif "CBS" in channel_raw:
            channels_str = "CBS Sports Network"

        results[fixture_key] = {
            "home": home,
            "away": away,
            "us_broadcaster": "CBS Sports / Paramount+",
            "us_channels": channels_str,
        }

    logger.info(f"Scraped {len(results)} UCL fixtures from CBS Sports")
    return results


def scrape_all() -> dict:
    """Return combined US EPL + UCL data."""
    epl = scrape_epl()
    ucl = scrape_ucl()
    for key, data in ucl.items():
        data["competition"] = "UCL"
        epl[key] = data
    for key in epl:
        if "competition" not in epl[key]:
            epl[key]["competition"] = "EPL"
    return epl


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_all()
    print(f"\nTotal US fixtures: {len(results)}")
    for key, data in list(results.items())[:8]:
        print(f"\n{key}: {data.get('us_channels')} ({data.get('competition')})")
