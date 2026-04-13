"""
fixtures_efl.py
Fallback / validator: scrapes efl.com for Championship, League One, League Two fixtures.
Used when football-data.org does not return data for EFL competitions.
"""

import logging
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EFL_COMPETITIONS = {
    "championship": {"name": "Championship",  "code": "ELC", "url": "https://www.efl.com/fixtures-results/?division=championship"},
    "league-one":   {"name": "League One",    "code": "EL1", "url": "https://www.efl.com/fixtures-results/?division=league-one"},
    "league-two":   {"name": "League Two",    "code": "EL2", "url": "https://www.efl.com/fixtures-results/?division=league-two"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TVsport/1.0; +https://tvsport.live)"
}


def _parse_efl_page(html: str, comp_info: dict) -> list:
    """Parse EFL fixtures page HTML into fixture dicts."""
    fixtures = []
    soup = BeautifulSoup(html, "html.parser")

    # EFL site uses match cards — find fixture blocks
    # Structure varies but common selector: .fixture, .match-fixture, data-fixture
    fixture_blocks = soup.select(".match, .fixture-item, [data-home], .matchlist-item")

    if not fixture_blocks:
        # Try broader selector
        fixture_blocks = soup.select("li.match, div.match, tr.match")

    for block in fixture_blocks:
        try:
            home_el = block.select_one("[data-home], .home-team, .team-home, .match-home")
            away_el = block.select_one("[data-away], .away-team, .team-away, .match-away")
            date_el = block.select_one("[data-date], .match-date, time, .date")

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)

            # Try to get date from data attribute or text
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime") or date_el.get("data-date") or date_el.get_text(strip=True)

            if not home or not away:
                continue

            # Build a simple ID
            date_slug = date_str[:10] if date_str else "unknown"
            fixture_id = f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{date_slug}"

            fixtures.append({
                "id":          fixture_id,
                "competition": comp_info["name"],
                "comp_code":   comp_info["code"],
                "home_team":   home,
                "away_team":   away,
                "kickoff":     date_str,
                "matchday":    None,
                "stage":       "REGULAR_SEASON",
                "group":       None,
                "source":      "efl.com",
            })
        except Exception as e:
            logger.debug(f"[efl] Could not parse fixture block: {e}")
            continue

    return fixtures


def scrape_fixtures() -> list:
    """Scrape EFL fixture pages. Returns list of fixture dicts."""
    all_fixtures = []

    for key, comp_info in EFL_COMPETITIONS.items():
        try:
            logger.info(f"[efl] Fetching {comp_info['name']}...")
            resp = requests.get(comp_info["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            fixtures = _parse_efl_page(resp.text, comp_info)
            logger.info(f"[efl] {comp_info['name']}: {len(fixtures)} fixtures parsed")
            all_fixtures.extend(fixtures)
        except Exception as e:
            logger.error(f"[efl] Failed to fetch {comp_info['name']}: {e}")

    return all_fixtures
