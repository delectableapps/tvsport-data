"""
uk_skysports.py
Scrapes skysports.com/watch/sport-on-sky for exact UK channel per fixture.
This is more reliable than EPG for UK assignments — Sky's own listings page
with structured HTML showing team, channel, and time per fixture.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

URL = "https://www.skysports.com/watch/sport-on-sky"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

# Normalise Sky channel names to our standard names
CHANNEL_MAP = {
    "sky sports main event":    "Sky Sports Main Event",
    "sky sports premier league":"Sky Sports Premier League",
    "sky sports football":      "Sky Sports Football",
    "sky sports action":        "Sky Sports Action",
    "sky sports arena":         "Sky Sports Arena",
    "sky sports mix":           "Sky Sports Mix",
    "sky sports+":              "Sky Sports+",
    "sky sports plus":          "Sky Sports+",
    "tnt sports 1":             "TNT Sports 1",
    "tnt sports 2":             "TNT Sports 2",
    "tnt sports 3":             "TNT Sports 3",
    "tnt sports 4":             "TNT Sports 4",
}

TEAM_ALIASES = {
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham",
    "wolves": "wolverhampton wanderers",
    "n. forest": "nottingham forest",
    "nott'm forest": "nottingham forest",
    "notts forest": "nottingham forest",
    "so'ton": "southampton",
    "sheff utd": "sheffield united",
    "sheff weds": "sheffield wednesday",
    "qpr": "queens park rangers",
    "west brom": "west bromwich albion",
    "luton": "luton town",
    "boro": "middlesbrough",
}


def _normalise_team(name: str) -> str:
    n = name.lower().strip()
    return TEAM_ALIASES.get(n, n)


def _normalise_channel(raw: str) -> str:
    return CHANNEL_MAP.get(raw.lower().strip(), raw.strip())


def _parse_page(html: str) -> list:
    """
    Parse the sport-on-sky page.
    Returns list of dicts: { home, away, channel, kickoff_display }
    """
    fixtures = []
    soup = BeautifulSoup(html, "html.parser")

    # The page lists fixtures in sections by day
    # Each fixture has: team names, competition, channel, time
    # Pattern from page: "Competition, Channel (HH:MM)"
    # Teams are in separate elements

    # Find all fixture blocks — they're in li or div elements
    # Look for elements containing " v " or " vs " with channel info nearby
    items = soup.select("li, .match-listing, [class*='fixture'], [class*='match']")

    for item in items:
        text = item.get_text(" ", strip=True)

        # Look for "Team A v/vs Team B" pattern
        team_match = re.search(
            r'([A-Z][a-zA-Z\s&\'.]{2,30}?)\s+(?:v\.?|vs\.?)\s+([A-Z][a-zA-Z\s&\'.]{2,30})',
            text
        )
        if not team_match:
            continue

        home = team_match.group(1).strip()
        away = team_match.group(2).strip()

        # Extract channel name — look for "Sky Sports X" or "TNT Sports X"
        channel_match = re.search(
            r'(Sky Sports[\w\s+]+|TNT Sports\s*\d*)',
            text, re.IGNORECASE
        )
        channel = _normalise_channel(channel_match.group(1)) if channel_match else ""

        # Extract time
        time_match = re.search(r'(\d{2}:\d{2})', text)
        kickoff_display = time_match.group(1) if time_match else ""

        if home and away and channel:
            fixtures.append({
                "home": home,
                "away": away,
                "channel": channel,
                "kickoff_display": kickoff_display,
            })

    return fixtures


def _fuzzy_match(sky_home: str, sky_away: str, fixtures: list) -> str | None:
    """Match Sky listing to a fixture ID."""
    sh = _normalise_team(sky_home)
    sa = _normalise_team(sky_away)

    for f in fixtures:
        fh = _normalise_team(f.get("home_team", ""))
        fa = _normalise_team(f.get("away_team", ""))

        h_match = sh in fh or fh in sh or sh[:5] == fh[:5]
        a_match = sa in fa or fa in sa or sa[:5] == fa[:5]

        if h_match and a_match:
            return f["id"]
    return None


def get_uk_channels(fixtures: list) -> dict:
    """
    Scrape skysports.com and return:
        { fixture_id: { "channel": "Sky Sports Football", "kickoff_display": "20:00" } }
    """
    try:
        logger.info("[skysports] Fetching sport-on-sky page...")
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        sky_fixtures = _parse_page(resp.text)
        logger.info(f"[skysports] Found {len(sky_fixtures)} fixtures on page")
    except Exception as e:
        logger.error(f"[skysports] Fetch failed: {e}")
        return {}

    result = {}
    for sky_fix in sky_fixtures:
        fixture_id = _fuzzy_match(sky_fix["home"], sky_fix["away"], fixtures)
        if fixture_id:
            result[fixture_id] = {
                "channel": sky_fix["channel"],
                "kickoff_display": sky_fix["kickoff_display"],
            }

    logger.info(f"[skysports] Matched {len(result)} fixtures with specific Sky channel")
    return result
