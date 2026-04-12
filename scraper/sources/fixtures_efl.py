"""
fixtures_efl.py — EFL Fixture Scraper
Competitions: Championship, League One, League Two, National League
Source: thesportsdb.com API (free tier) + efl.com fallback

Returns list of fixture dicts compatible with merger.py
"""
import logging
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# thesportsdb.com league IDs — verified from thesportsdb.com URLs
EFL_LEAGUE_IDS = {
    "EFL-CH": "4329",   # English Championship  (confirmed: thesportsdb.com/league/4329)
    "EFL-L1": "4396",   # English League One    (confirmed: thesportsdb.com/league/4396)
    "EFL-L2": "4397",   # English League Two    (confirmed: thesportsdb.com/league/4397)
    "NAT":    "4398",   # National League       (thesportsdb.com/league/4398)
}

EFL_SEASON = "2025-2026"
SPORTSDB_API = "https://www.thesportsdb.com/api/v1/json/3"
HEADERS = {"User-Agent": "TVsport.live fixture scraper (contact: admin@tvsport.live)"}


def _fetch_sportsdb(league_id: str, comp_code: str) -> list:
    """Fetch fixtures from thesportsdb for a given league."""
    fixtures = []
    try:
        url = f"{SPORTSDB_API}/eventsseason.php?id={league_id}&s={EFL_SEASON}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        events = data.get("events") or []
        now = datetime.now(timezone.utc)

        for ev in events:
            try:
                # Parse kickoff — thesportsdb uses dateEvent + strTime
                date_str = ev.get("dateEvent", "")
                time_str = ev.get("strTime", "00:00:00") or "00:00:00"
                if not date_str:
                    continue

                dt_str = f"{date_str}T{time_str}Z"
                kickoff = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

                # Keep fixtures from start of today through 30 days ahead
                # so today's matches stay visible all day until midnight
                now = datetime.now(timezone.utc)
                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                delta = (kickoff - start_of_today).total_seconds() / 86400
                if delta < 0 or delta > 30:
                    continue

                # 3pm Saturday blackout — same rule as EPL
                blackout = False
                if kickoff.weekday() == 5:  # Saturday
                    if kickoff.hour == 14 and kickoff.minute == 45:
                        # BST: 15:00 BST = 14:00 UTC
                        blackout = True
                    elif kickoff.hour == 15 and kickoff.minute == 0:
                        blackout = True

                fixtures.append({
                    "id": f"efl-{ev.get('idEvent', '')}",
                    "competition": comp_code,
                    "home_team": ev.get("strHomeTeam", ""),
                    "away_team": ev.get("strAwayTeam", ""),
                    "kickoff": kickoff.isoformat(),
                    "matchday": ev.get("intRound", ""),
                    "blackout": blackout,
                    "source": "thesportsdb",
                })
            except Exception as e:
                log.debug(f"EFL event parse error: {e}")
                continue

    except Exception as e:
        log.warning(f"EFL sportsdb fetch failed for {comp_code}: {e}")

    return fixtures


def _fetch_efl_website(comp_code: str) -> list:
    """
    Fallback: scrape efl.com fixtures page.
    Only used if thesportsdb returns empty.
    """
    comp_slugs = {
        "EFL-CH": "championship",
        "EFL-L1": "league-one",
        "EFL-L2": "league-two",
        "NAT":    "national-league",
    }
    slug = comp_slugs.get(comp_code)
    if not slug:
        return []

    fixtures = []
    try:
        url = f"https://www.efl.com/fixtures-results/?league={slug}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # EFL.com fixture cards
        for card in soup.select(".fixture-card, .match-fixture"):
            try:
                home = card.select_one(".home-team, .team-home")
                away = card.select_one(".away-team, .team-away")
                ko_el = card.select_one("time, .kickoff-time")

                if not home or not away or not ko_el:
                    continue

                kickoff_str = ko_el.get("datetime") or ko_el.text.strip()
                kickoff = datetime.fromisoformat(kickoff_str)

                fixtures.append({
                    "id": f"efl-web-{comp_code}-{home.text.strip()[:4]}{away.text.strip()[:4]}",
                    "competition": comp_code,
                    "home_team": home.text.strip(),
                    "away_team": away.text.strip(),
                    "kickoff": kickoff.isoformat(),
                    "matchday": "",
                    "blackout": False,
                    "source": "efl.com",
                })
            except Exception as e:
                log.debug(f"EFL.com card parse: {e}")
                continue

    except Exception as e:
        log.warning(f"EFL.com scrape failed for {comp_code}: {e}")

    return fixtures


def scrape_efl_fixtures() -> list:
    """
    Main entry point. Scrapes all four EFL competitions.
    Returns combined list of fixture dicts.
    """
    all_fixtures = []

    for comp_code, league_id in EFL_LEAGUE_IDS.items():
        log.info(f"Scraping {comp_code} fixtures from thesportsdb...")
        fixtures = _fetch_sportsdb(league_id, comp_code)

        if not fixtures:
            log.info(f"  thesportsdb empty, trying efl.com fallback for {comp_code}...")
            fixtures = _fetch_efl_website(comp_code)

        log.info(f"  {comp_code}: {len(fixtures)} fixtures found")
        all_fixtures.extend(fixtures)

    return all_fixtures


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_efl_fixtures()
    print(f"Total EFL fixtures: {len(results)}")
    for f in results[:5]:
        print(f"  {f['competition']} | {f['home_team']} vs {f['away_team']} | {f['kickoff']}")
