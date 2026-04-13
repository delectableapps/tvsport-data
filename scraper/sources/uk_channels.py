"""
uk_channels.py
Scrapes livefootballontv.com for UK broadcaster + specific channel per fixture.
This is the most reliable public source for exact UK channel assignments
(e.g. Sky Sports Main Event vs Sky Sports Premier League vs TNT Sports 1).

Used as the UK schedule layer — cross-referenced against rights_db.py.
"""

import logging
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

URL = "https://www.livefootballontv.com/matches/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TVsport/1.0; +https://tvsport.live)"
}

# Map livefootballontv channel names → normalised TVsport channel names
CHANNEL_MAP = {
    "sky sports main event":         "Sky Sports Main Event",
    "sky sports premier league":     "Sky Sports Premier League",
    "sky sports football":           "Sky Sports Football",
    "sky sports action":             "Sky Sports Action",
    "sky sports arena":              "Sky Sports Arena",
    "sky sports mix":                "Sky Sports Mix",
    "tnt sports 1":                  "TNT Sports 1",
    "tnt sports 2":                  "TNT Sports 2",
    "tnt sports 3":                  "TNT Sports 3",
    "tnt sports 4":                  "TNT Sports 4",
    "tnt sports ultimate":           "TNT Sports Ultimate",
    "bbc one":                       "BBC One",
    "bbc two":                       "BBC Two",
    "bbc iplayer":                   "BBC iPlayer",
    "itv1":                          "ITV1",
    "itvx":                          "ITVX",
    "amazon prime video":            "Amazon Prime Video",
    "amazon prime":                  "Amazon Prime Video",
    "premier sports 1":              "Premier Sports 1",
    "premier sports 2":              "Premier Sports 2",
    "freesports":                    "FreeSports",
    "channel 4":                     "Channel 4",
    "s4c":                           "S4C",
}

# Which broadcaster each channel belongs to (for rights matching)
CHANNEL_TO_BROADCASTER = {
    "Sky Sports Main Event":         "Sky Sports",
    "Sky Sports Premier League":     "Sky Sports",
    "Sky Sports Football":           "Sky Sports",
    "Sky Sports Action":             "Sky Sports",
    "Sky Sports Arena":              "Sky Sports",
    "Sky Sports Mix":                "Sky Sports",
    "TNT Sports 1":                  "TNT Sports",
    "TNT Sports 2":                  "TNT Sports",
    "TNT Sports 3":                  "TNT Sports",
    "TNT Sports 4":                  "TNT Sports",
    "TNT Sports Ultimate":           "TNT Sports",
    "BBC One":                       "BBC",
    "BBC Two":                       "BBC",
    "BBC iPlayer":                   "BBC",
    "ITV1":                          "ITV",
    "ITVX":                          "ITV",
    "Amazon Prime Video":            "Prime Video",
    "Premier Sports 1":              "Premier Sports",
    "Premier Sports 2":              "Premier Sports",
    "FreeSports":                    "FreeSports",
    "Channel 4":                     "Channel 4",
}


def _normalise_channel(raw: str) -> str:
    """Normalise a raw channel name from the site."""
    cleaned = raw.strip().lower()
    return CHANNEL_MAP.get(cleaned, raw.strip())


def _parse_page(html: str) -> dict:
    """
    Parse livefootballontv.com and return a dict:
        { "Team A v Team B": { "channels": ["Sky Sports Main Event"], "time": "12:30" } }
    """
    results = {}
    soup = BeautifulSoup(html, "html.parser")

    # The site lists matches in article/li elements with team names and channel info
    match_items = soup.select("article.match, li.match, .match-listing, .fixture")

    if not match_items:
        # Broader fallback
        match_items = soup.select("[class*='match']")

    for item in match_items:
        try:
            # Extract teams
            teams_el = item.select_one(".teams, .match-teams, h3, h4, .fixture-teams")
            if not teams_el:
                continue
            teams_text = teams_el.get_text(strip=True)

            # Extract channel(s)
            channel_els = item.select(".channel, .broadcaster, .tv-channel, [class*='channel']")
            channels = []
            for ch_el in channel_els:
                ch_name = ch_el.get_text(strip=True)
                if ch_name:
                    channels.append(_normalise_channel(ch_name))

            # Extract time
            time_el = item.select_one("time, .time, .kickoff, .ko-time")
            time_str = ""
            if time_el:
                time_str = time_el.get("datetime") or time_el.get_text(strip=True)

            if teams_text and channels:
                results[teams_text] = {
                    "channels": channels,
                    "kickoff_display": time_str,
                }
        except Exception as e:
            logger.debug(f"[livefootballontv] parse error: {e}")
            continue

    return results


def _fuzzy_match(fixture_key: str, uk_data: dict) -> dict | None:
    """
    Try to match a fixture's team names against livefootballontv entries.
    fixture_key: "Home Team vs Away Team"
    """
    # Direct lookup first
    if fixture_key in uk_data:
        return uk_data[fixture_key]

    # Fuzzy: check if both team names appear in any key
    parts = fixture_key.lower().replace(" vs ", " v ").split(" v ")
    if len(parts) != 2:
        return None

    home_frag = parts[0].strip()[:8]
    away_frag = parts[1].strip()[:8]

    for key, val in uk_data.items():
        key_lower = key.lower()
        if home_frag in key_lower and away_frag in key_lower:
            return val

    return None


def get_uk_channels(fixtures: list) -> dict:
    """
    Fetch livefootballontv.com and return a dict mapping fixture IDs
    to their UK channel data.

    Returns:
        { fixture_id: { "channels": [...], "kickoff_display": "..." } }
    """
    try:
        logger.info("[livefootballontv] Fetching UK channel data...")
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        uk_data = _parse_page(resp.text)
        logger.info(f"[livefootballontv] Found {len(uk_data)} fixtures on page")
    except Exception as e:
        logger.error(f"[livefootballontv] Fetch failed: {e}")
        return {}

    result = {}
    for fixture in fixtures:
        key = f"{fixture.get('home_team', '')} v {fixture.get('away_team', '')}"
        match = _fuzzy_match(key, uk_data)
        if match:
            result[fixture["id"]] = match

    logger.info(f"[livefootballontv] Matched {len(result)} fixtures with UK channel data")
    return result
