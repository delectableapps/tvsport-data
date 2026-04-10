"""
sources/uk_live_footballontv.py
================================
Scrapes live-footballontv.com for UK channel assignments for EPL and UCL.
Returns: dict keyed by normalised fixture name → channel data

Source: https://www.live-footballontv.com
- Static HTML, no JS rendering needed
- Updated same-day, covers ~6 weeks ahead
- Provides: kick-off time, broadcaster(s), channel(s) per fixture
"""

import re
import logging
from datetime import datetime, timezone
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
}

URLS = {
    "EPL": "https://www.live-footballontv.com/live-premier-league-football-on-tv.html",
    "UCL": "https://www.live-footballontv.com/live-champions-league-football-on-tv.html",
}

# Map broadcaster display names → our canonical names
BROADCASTER_MAP = {
    "sky sports main event":        "Sky Sports",
    "sky sports premier league":    "Sky Sports",
    "sky sports premier leaguesky": "Sky Sports",
    "sky sports football":          "Sky Sports",
    "sky sports action":            "Sky Sports",
    "sky sports ultra hdr":         "Sky Sports",
    "sky sports+":                  "Sky Sports",
    "tnt sports 1":                 "TNT Sports",
    "tnt sports 2":                 "TNT Sports",
    "tnt sports 3":                 "TNT Sports",
    "tnt sports 4":                 "TNT Sports",
    "tnt sports ultimate":          "TNT Sports",
    "hbo max":                      "HBO Max",
    "bbc one":                      "BBC Sport",
    "bbc two":                      "BBC Sport",
    "bbc iplayer":                  "BBC Sport",
    "bbc sport":                    "BBC Sport",
    "itv":                          "ITV",
    "itv1":                         "ITV",
    "amazon prime video":           "Amazon Prime Video",
    "prime video":                  "Amazon Prime Video",
}

# Channels that indicate Sky Sports (even when just one is listed)
SKY_CHANNELS = {
    "Sky Sports Main Event",
    "Sky Sports Premier League",
    "Sky Sports Football",
    "Sky Sports Action",
    "Sky Sports Ultra HDR",
    "Sky Sports+",
}

TNT_CHANNELS = {
    "TNT Sports 1", "TNT Sports 2", "TNT Sports 3",
    "TNT Sports 4", "TNT Sports Ultimate", "HBO Max",
}


def _fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return ""


def _parse_date_block(date_text: str) -> str:
    """
    Convert date strings like 'Friday 10th April 2026' to ISO date 'YYYY-MM-DD'.
    """
    # Remove ordinal suffixes
    clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_text.strip())
    # Try multiple formats
    for fmt in ["%A %d %B %Y", "%A, %d %B %Y"]:
        try:
            return datetime.strptime(clean, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_time_to_utc(date_str: str, time_str: str) -> str:
    """
    Convert 'YYYY-MM-DD' + 'HH:MM' (BST/UK local) to UTC ISO string.
    April–October UK = BST (UTC+1), otherwise GMT (UTC+0).
    """
    try:
        dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        # Determine offset: BST = last Sunday March → last Sunday October
        month = dt_local.month
        offset_hours = 1 if 3 < month < 11 or (month == 3 and dt_local.day >= 25) \
                       else 0
        dt_utc = dt_local.replace(tzinfo=timezone.utc)
        # Subtract BST offset to get UTC
        from datetime import timedelta
        dt_utc = dt_utc - timedelta(hours=offset_hours)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _normalise_team(name: str) -> str:
    """Normalise team name for matching."""
    return (name.strip()
               .lower()
               .replace("&", "and")
               .replace(".", "")
               .replace("'", "")
               .replace("-", " "))


def _make_fixture_key(home: str, away: str) -> str:
    return f"{_normalise_team(home)} v {_normalise_team(away)}"


def _parse_channels(channel_text: str) -> tuple[str, list[str]]:
    """
    Parse raw channel text like 'Sky Sports Main EventSky Sports Premier LeagueSky Sports Ultra HDR'
    Returns (broadcaster_name, [channel_list])
    """
    # The site concatenates channel names without separators
    # We split on known channel name prefixes
    known_channels = [
        "TNT Sports Ultimate", "TNT Sports 1", "TNT Sports 2",
        "TNT Sports 3", "TNT Sports 4", "TNT Sports 5", "TNT Sports 6",
        "HBO Max",
        "Sky Sports Main Event", "Sky Sports Premier League",
        "Sky Sports Football", "Sky Sports Action",
        "Sky Sports Ultra HDR", "Sky Sports+",
        "BBC One", "BBC Two", "BBC iPlayer",
        "ITV", "ITV1", "ITV4", "Channel 4",
        "Amazon Prime Video", "Prime Video",
        "LaLiga TV UK", "Viaplay Sports 1 UK", "Viaplay Sports 2 UK",
        "Premier Sports 1", "Premier Sports 2",
        "DAZN National League",
    ]

    # Sort by length desc to match longer names first
    known_channels.sort(key=len, reverse=True)

    found = []
    remaining = channel_text.strip()

    # Try to extract known channel names
    for ch in known_channels:
        if ch in remaining:
            found.append(ch)
            remaining = remaining.replace(ch, "", 1).strip()

    if not found:
        # Fallback: use raw text
        found = [channel_text.strip()]

    # Determine primary broadcaster
    tnt_found = [c for c in found if c in TNT_CHANNELS]
    sky_found = [c for c in found if c in SKY_CHANNELS]
    bbc_found = [c for c in found if "BBC" in c]
    prime_found = [c for c in found if "Prime" in c or "Amazon" in c]

    if tnt_found:
        broadcaster = "TNT Sports"
    elif sky_found:
        broadcaster = "Sky Sports"
    elif bbc_found:
        broadcaster = "BBC Sport"
    elif prime_found:
        broadcaster = "Amazon Prime Video"
    else:
        broadcaster = found[0] if found else "Unknown"

    return broadcaster, found


def scrape(competition: str = "EPL") -> dict:
    """
    Scrape live-footballontv.com for a given competition.
    Returns dict: { fixture_key: { fixture data } }
    e.g. "arsenal v afc bournemouth": {
        "home": "Arsenal", "away": "AFC Bournemouth",
        "date": "2026-04-11", "kickoff_utc": "...",
        "kickoff_local": "12:30",
        "uk_broadcaster": "TNT Sports",
        "uk_channels": ["TNT Sports 1", "TNT Sports Ultimate", "HBO Max"],
        "uk_blackout": False,
    }
    """
    url = URLS.get(competition.upper())
    if not url:
        raise ValueError(f"Unknown competition: {competition}")

    logger.info(f"Scraping {competition} from {url}")
    html = _fetch_html(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    results = {}

    # Find date section headers and fixture rows
    # The site structure: h2/h3 with date text, then divs/table rows with fixtures
    current_date = None
    current_date_iso = None

    # Find all text content - look for date headers and fixture lines
    # Structure varies - find all elements containing fixture data
    body_text = soup.get_text(separator="\n")
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    # Parse the structured text
    # Pattern: Date line → Time · Teams · Competition · Channel(s)
    date_pattern = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"\d{1,2}(st|nd|rd|th)?\s+\w+\s+\d{4}$",
        re.IGNORECASE
    )
    time_pattern = re.compile(r"^\d{2}:\d{2}$")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for date line
        if date_pattern.match(line):
            current_date_iso = _parse_date_block(line)
            current_date = line
            i += 1
            continue

        # Check for time line (kick-off)
        if time_pattern.match(line) and current_date_iso:
            kickoff_time = line
            kickoff_utc = _parse_time_to_utc(current_date_iso, kickoff_time)

            # Next lines should be: teams, competition, channels
            if i + 3 < len(lines):
                teams_line = lines[i + 1]  # e.g. "Arsenal v AFC Bournemouth"
                comp_line = lines[i + 2]   # e.g. "Premier League"
                channel_line = lines[i + 3] if i + 3 < len(lines) else ""

                # Parse teams
                if " v " in teams_line:
                    parts = teams_line.split(" v ", 1)
                    home = parts[0].strip()
                    away = parts[1].strip()
                    fixture_key = _make_fixture_key(home, away)

                    # Parse channels
                    broadcaster, channels = _parse_channels(channel_line)

                    # Detect UK blackout (15:00 Saturday, no broadcaster picked)
                    is_saturday = False
                    if current_date_iso:
                        try:
                            d = datetime.strptime(current_date_iso, "%Y-%m-%d")
                            is_saturday = d.weekday() == 5  # Saturday = 5
                        except Exception:
                            pass
                    uk_blackout = (is_saturday and kickoff_time == "15:00")

                    results[fixture_key] = {
                        "home": home,
                        "away": away,
                        "date": current_date_iso,
                        "kickoff_local": kickoff_time,
                        "kickoff_utc": kickoff_utc,
                        "uk_broadcaster": broadcaster if not uk_blackout else None,
                        "uk_channels": channels if not uk_blackout else [],
                        "uk_blackout": uk_blackout,
                        "competition_label": comp_line,
                        "_raw_channels": channel_line,
                    }
                    i += 4
                    continue

        i += 1

    logger.info(f"Scraped {len(results)} {competition} fixtures from live-footballontv.com")
    return results


def scrape_all() -> dict:
    """Scrape both EPL and UCL, return merged dict with competition tag."""
    all_results = {}
    for comp in ["EPL", "UCL"]:
        fixtures = scrape(comp)
        for key, data in fixtures.items():
            data["competition"] = comp
            all_results[key] = data
    return all_results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_all()
    print(f"\nTotal fixtures found: {len(results)}")
    for key, fx in list(results.items())[:5]:
        print(f"\n{key}:")
        for k, v in fx.items():
            print(f"  {k}: {v}")
