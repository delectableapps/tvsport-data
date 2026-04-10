"""
sources/uk_tvguide.py
======================
Scrapes tvguide.co.uk/sport/football for UK coverage start times.
This supplements live-footballontv.com by adding the broadcast start time
(when the pre-match show begins) vs the actual kick-off time.

Source: https://www.tvguide.co.uk/sport/football
- Static HTML, no JS rendering needed
- Covers ~7 days ahead
- Provides: coverage start time, channel, kick-off time per fixture
"""

import re
import logging
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.tvguide.co.uk/",
}

BASE_URL = "https://www.tvguide.co.uk/sport/football"


def _normalise_team(name: str) -> str:
    return (name.strip()
               .lower()
               .replace("&", "and")
               .replace(".", "")
               .replace("'", "")
               .replace("-", " "))


def _make_fixture_key(home: str, away: str) -> str:
    return f"{_normalise_team(home)} v {_normalise_team(away)}"


def _bst_to_utc(date_str: str, time_str: str) -> str:
    """Convert BST time on date_str to UTC ISO string."""
    try:
        from datetime import timezone, timedelta
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        month = dt.month
        offset = 1 if 3 < month < 11 else 0
        dt_utc = dt - timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def scrape() -> dict:
    """
    Scrape tvguide.co.uk football listings.
    Returns dict: { fixture_key: { coverage_start, kickoff, channels, broadcaster } }
    """
    try:
        r = requests.get(BASE_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch tvguide.co.uk: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    results = {}

    # TVGuide structure:
    # Date sections marked by h3 with date text
    # Each fixture: div with class containing match info
    # Format: "BROADCAST · HH:MM\nHome v Away\nCompetition\nChannel · HH:MM"

    body_text = soup.get_text(separator="\n")
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    # Identify date sections
    today = date.today()
    date_markers = {
        "today": today.strftime("%Y-%m-%d"),
        "tomorrow": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
    }

    # Also handle named days like "Fri 10 Apr", "Sat 11 Apr"
    day_abbrevs = {
        "mon": 0, "tue": 1, "wed": 2, "thu": 3,
        "fri": 4, "sat": 5, "sun": 6,
    }

    current_date = today.strftime("%Y-%m-%d")

    broadcast_pattern = re.compile(r"^Broadcast\s*·?\s*(\d{2}:\d{2})$", re.IGNORECASE)
    time_only_pattern = re.compile(r"^(\d{2}:\d{2})$")
    named_date_pattern = re.compile(
        r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
        re.IGNORECASE
    )

    MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    # Competitions we care about
    TARGET_COMPS = {
        "English Premier League", "Premier League",
        "UEFA Champions League", "Champions League",
    }

    i = 0
    pending_broadcast_start = None

    while i < len(lines):
        line = lines[i]

        # Check for "Today" / "Tomorrow"
        if line.lower() == "today":
            current_date = date_markers["today"]
            i += 1
            continue
        if line.lower() == "tomorrow":
            current_date = date_markers["tomorrow"]
            i += 1
            continue

        # Check for named date like "Fri 10 Apr" or "Sat 11 Apr"
        m = named_date_pattern.match(line)
        if m:
            day_abbr = m.group(1).lower()
            day_num = int(m.group(2))
            month_abbr = m.group(3).lower()
            month_num = MONTH_MAP.get(month_abbr, 0)
            if month_num:
                year = today.year
                # Handle year rollover
                if month_num < today.month - 1:
                    year += 1
                try:
                    current_date = date(year, month_num, day_num).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            i += 1
            continue

        # Check for "Broadcast · HH:MM" — coverage start time
        bm = broadcast_pattern.match(line)
        if bm:
            pending_broadcast_start = bm.group(1)
            i += 1
            continue

        # Check for kick-off time line (standalone HH:MM after broadcast)
        if time_only_pattern.match(line) and i > 0:
            # This might be a kick-off time
            kickoff_time = line

            # Look ahead for: home v away, competition, channel
            if i + 3 < len(lines):
                teams_line = lines[i + 1]
                comp_line = lines[i + 2]
                channel_line = lines[i + 3]

                # Check if this is a competition we care about
                if any(c.lower() in comp_line.lower() for c in TARGET_COMPS):
                    if " v " in teams_line or "vs" in teams_line.lower():
                        # Parse teams
                        sep = " v " if " v " in teams_line else " vs "
                        parts = teams_line.split(sep, 1)
                        if len(parts) == 2:
                            home = parts[0].strip()
                            away = parts[1].strip()
                            fixture_key = _make_fixture_key(home, away)

                            # Parse channel info
                            # Format: "TNT Sports 1 · 18:00" or just "TNT Sports 1"
                            channel_parts = channel_line.split("·")
                            channel_name = channel_parts[0].strip()
                            broadcast_start_from_channel = None
                            if len(channel_parts) > 1:
                                t = channel_parts[1].strip()
                                if re.match(r"\d{2}:\d{2}", t):
                                    broadcast_start_from_channel = t

                            coverage_start = broadcast_start_from_channel or pending_broadcast_start

                            results[fixture_key] = {
                                "home": home,
                                "away": away,
                                "date": current_date,
                                "kickoff_local": kickoff_time,
                                "kickoff_utc": _bst_to_utc(current_date, kickoff_time),
                                "coverage_start_local": coverage_start,
                                "coverage_start_utc": _bst_to_utc(current_date, coverage_start) if coverage_start else None,
                                "channel": channel_name,
                                "competition": comp_line.strip(),
                            }
                            pending_broadcast_start = None
                            i += 4
                            continue

            pending_broadcast_start = None

        i += 1

    logger.info(f"Scraped {len(results)} fixtures from tvguide.co.uk")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    print(f"\nTotal: {len(results)} fixtures")
    for key, data in list(results.items())[:8]:
        print(f"\n{key}:")
        for k, v in data.items():
            print(f"  {k}: {v}")
