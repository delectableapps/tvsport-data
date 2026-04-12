"""
amazon_prime.py — Amazon Prime Video Football Scraper
Scrapes live-footballontv.com/live-football-on-amazon.html

What Amazon Prime Video holds (UK/Ireland, as of 2025/26):
  - UCL: top-pick Tuesday match exclusively (renewed to 2030/31)
  - EFL: selected Championship, League One, League Two matches
  - EPL: NO RIGHTS from 2025/26 onwards (lost bid, deal ended 2024/25)

Returns a dict keyed by (home_team, away_team) with channel data,
used by merger.py to override rights_db static entries when Amazon
is specifically shown for that fixture.
"""
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

log = logging.getLogger(__name__)

AMAZON_URL = "https://www.live-footballontv.com/live-football-on-amazon.html"
HEADERS = {"User-Agent": "TVsport.live fixture scraper (contact: admin@tvsport.live)"}

AMAZON_BROADCASTER = {
    "name": "Amazon Prime Video",
    "country": "United Kingdom",
    "channels": ["Prime Video (free with Prime membership)"],
    "badges": ["live", "stream", "free"],
    "icon": "📱",
}


def scrape_amazon_fixtures() -> dict:
    """
    Scrapes live-footballontv.com Amazon page.
    Returns dict: { (home, away): broadcaster_info }
    """
    results = {}
    try:
        resp = requests.get(AMAZON_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        now = datetime.now(timezone.utc)

        # live-footballontv uses a consistent table/list structure
        # Each fixture row typically contains: date, time, competition, teams
        for row in soup.select("tr.match, .fixture-row, li.match-item, .tv-match"):
            try:
                # Extract team names
                teams_el = row.select_one(".match-teams, .teams, .fixture-teams")
                if not teams_el:
                    # Fallback: look for vs separator
                    text = row.get_text(" ", strip=True)
                    if " v " in text.lower():
                        parts = text.lower().split(" v ")
                        home = parts[0].strip().title()
                        away = parts[1].split()[0].strip().title()
                    else:
                        continue
                else:
                    teams_text = teams_el.get_text(" ", strip=True)
                    if " v " in teams_text.lower():
                        parts = teams_text.split(" v ")
                        home = parts[0].strip()
                        away = parts[1].strip()
                    else:
                        continue

                # Only include upcoming fixtures (within 30 days)
                date_el = row.select_one("time, .date, .fixture-date")
                if date_el:
                    dt_str = date_el.get("datetime", "")
                    if dt_str:
                        try:
                            ko = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            delta = (ko - now).total_seconds() / 86400
                            if delta < -1 or delta > 30:
                                continue
                        except Exception:
                            pass

                key = (home, away)
                results[key] = AMAZON_BROADCASTER
                log.debug(f"  Amazon Prime: {home} vs {away}")

            except Exception as e:
                log.debug(f"Amazon row parse: {e}")
                continue

        log.info(f"Amazon Prime: {len(results)} fixtures found")

    except Exception as e:
        log.warning(f"Amazon Prime scrape failed: {e}")

    return results


def get_amazon_channel_for_fixture(home: str, away: str,
                                    amazon_data: dict) -> dict | None:
    """
    Check if a specific fixture is on Amazon Prime.
    Tries exact match first, then fuzzy (first word of team name).
    Returns broadcaster dict or None.
    """
    # Exact match
    if (home, away) in amazon_data:
        return amazon_data[(home, away)]

    # Fuzzy match — first significant word of each team
    home_key = home.split()[0].lower()
    away_key = away.split()[0].lower()
    for (h, a), data in amazon_data.items():
        if h.split()[0].lower() == home_key and a.split()[0].lower() == away_key:
            return data

    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = scrape_amazon_fixtures()
    print(f"Amazon Prime fixtures: {len(data)}")
    for (h, a) in list(data.keys())[:5]:
        print(f"  {h} vs {a}")
