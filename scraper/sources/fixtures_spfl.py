"""
fixtures_spfl.py
Scrapes spfl.co.uk for Scottish Premiership, Championship, League One, League Two.
Primary source for Scottish football (not covered by football-data.org free tier).
"""

import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SPFL_COMPETITIONS = {
    "premiership": {
        "name": "Scottish Premiership",
        "code": "SP1",
        "url": "https://spfl.co.uk/league/premier-league/fixtures",
    },
    "championship": {
        "name": "Scottish Championship",
        "code": "SC1",
        "url": "https://spfl.co.uk/league/championship/fixtures",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TVsport/1.0; +https://tvsport.live)"
}


def _parse_spfl_page(html: str, comp_info: dict) -> list:
    """Parse SPFL fixtures HTML."""
    fixtures = []
    soup = BeautifulSoup(html, "html.parser")

    # SPFL site structure — common patterns
    blocks = soup.select(".fixture, .match-row, .fixture-row, li.fixture")

    if not blocks:
        blocks = soup.select("tr.fixture, div.fixture-card, .game-card")

    for block in blocks:
        try:
            home_el = block.select_one(".home, .home-team, [data-home]")
            away_el = block.select_one(".away, .away-team, [data-away]")
            date_el = block.select_one("time, .date, .kickoff-time, [datetime]")

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime") or date_el.get_text(strip=True)

            if not home or not away:
                continue

            date_slug = date_str[:10] if len(date_str) >= 10 else "unknown"
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
                "source":      "spfl.co.uk",
            })
        except Exception as e:
            logger.debug(f"[spfl] Could not parse fixture: {e}")
            continue

    return fixtures


def scrape_fixtures() -> list:
    """Scrape SPFL fixture pages. Returns list of fixture dicts."""
    all_fixtures = []

    for key, comp_info in SPFL_COMPETITIONS.items():
        try:
            logger.info(f"[spfl] Fetching {comp_info['name']}...")
            resp = requests.get(comp_info["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            fixtures = _parse_spfl_page(resp.text, comp_info)
            logger.info(f"[spfl] {comp_info['name']}: {len(fixtures)} fixtures parsed")
            all_fixtures.extend(fixtures)
        except Exception as e:
            logger.error(f"[spfl] Failed to fetch {comp_info['name']}: {e}")

    return all_fixtures
