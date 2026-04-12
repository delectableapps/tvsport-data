"""
fixtures_spfl.py — Scottish Football Fixture Scraper
Competitions: Scottish Premiership, Championship, Cup (League One/Two future)
Source: thesportsdb.com API + spfl.co.uk fallback

Returns list of fixture dicts compatible with merger.py
"""
import logging
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

SPFL_LEAGUE_IDS = {
    "SPL":  "4330",   # Scottish Premiership  (confirmed: thesportsdb.com/league/4330)
    "SCH":  "4409",   # Scottish Championship (confirmed: thesportsdb.com/league/4409)
    "SL1":  "4668",   # Scottish League One   (confirmed: thesportsdb.com/league/4668)
    "SL2":  "4670",   # Scottish League Two   (confirmed: thesportsdb.com/league/4670)
}

# Scottish Cup uses a different endpoint (cup competition)
SCUP_ID = "4571"  # Scottish Cup (thesportsdb.com/league/4571)

SEASON = "2025-2026"
SPORTSDB_API = "https://www.thesportsdb.com/api/v1/json/3"
HEADERS = {"User-Agent": "TVsport.live fixture scraper (contact: admin@tvsport.live)"}


def _fetch_sportsdb_league(league_id: str, comp_code: str) -> list:
    """Fetch league fixtures from thesportsdb."""
    fixtures = []
    try:
        url = f"{SPORTSDB_API}/eventsseason.php?id={league_id}&s={SEASON}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events") or []
        now = datetime.now(timezone.utc)

        for ev in events:
            try:
                date_str = ev.get("dateEvent", "")
                time_str = ev.get("strTime", "00:00:00") or "00:00:00"
                if not date_str:
                    continue

                dt_str = f"{date_str}T{time_str}Z"
                kickoff = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                delta = (kickoff - start_of_today).total_seconds() / 86400
                if delta < 0 or delta > 30:
                    continue

                fixtures.append({
                    "id": f"spfl-{ev.get('idEvent', '')}",
                    "competition": comp_code,
                    "home_team": ev.get("strHomeTeam", ""),
                    "away_team": ev.get("strAwayTeam", ""),
                    "kickoff": kickoff.isoformat(),
                    "matchday": ev.get("intRound", ""),
                    "blackout": False,   # No blackout rule in Scottish football
                    "source": "thesportsdb",
                })
            except Exception as e:
                log.debug(f"SPFL event parse: {e}")

    except Exception as e:
        log.warning(f"SPFL sportsdb failed for {comp_code}: {e}")

    return fixtures


def _fetch_sportsdb_cup(cup_id: str, comp_code: str) -> list:
    """Fetch cup fixtures from thesportsdb — uses next events endpoint."""
    fixtures = []
    try:
        url = f"{SPORTSDB_API}/eventsseason.php?id={cup_id}&s={SEASON}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events") or []
        now = datetime.now(timezone.utc)

        for ev in events:
            try:
                date_str = ev.get("dateEvent", "")
                time_str = ev.get("strTime", "00:00:00") or "00:00:00"
                if not date_str:
                    continue

                dt_str = f"{date_str}T{time_str}Z"
                kickoff = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                delta = (kickoff - start_of_today).total_seconds() / 86400
                if delta < 0 or delta > 30:
                    continue

                # Determine cup round label
                round_label = ev.get("strRound") or ev.get("intRound") or "Cup"

                fixtures.append({
                    "id": f"scup-{ev.get('idEvent', '')}",
                    "competition": comp_code,
                    "home_team": ev.get("strHomeTeam", ""),
                    "away_team": ev.get("strAwayTeam", ""),
                    "kickoff": kickoff.isoformat(),
                    "matchday": round_label,
                    "blackout": False,
                    "source": "thesportsdb",
                })
            except Exception as e:
                log.debug(f"Scottish Cup event parse: {e}")

    except Exception as e:
        log.warning(f"Scottish Cup sportsdb failed: {e}")

    return fixtures


def _fetch_spfl_website(comp_code: str) -> list:
    """Fallback: scrape spfl.co.uk."""
    comp_paths = {
        "SPL":  "premiership",
        "SCH":  "championship",
        "SL1":  "league-one",
        "SL2":  "league-two",
        "SCUP": "scottish-cup",
    }
    path = comp_paths.get(comp_code)
    if not path:
        return []

    fixtures = []
    try:
        if comp_code == "SCUP":
            url = f"https://spfl.co.uk/cup/scottish-cup/fixtures"
        else:
            url = f"https://spfl.co.uk/league/{path}/fixtures"

        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select(".fixture, .match-row, .fixture-row"):
            try:
                home = card.select_one(".home, .team-home, [class*=home-team]")
                away = card.select_one(".away, .team-away, [class*=away-team]")
                ko_el = card.select_one("time, .ko-time, .kick-off")

                if not home or not away:
                    continue

                kickoff_str = ""
                if ko_el:
                    kickoff_str = ko_el.get("datetime") or ko_el.text.strip()

                if not kickoff_str:
                    continue

                kickoff = datetime.fromisoformat(kickoff_str)

                fixtures.append({
                    "id": f"spfl-web-{comp_code}-{home.text.strip()[:4]}",
                    "competition": comp_code,
                    "home_team": home.text.strip(),
                    "away_team": away.text.strip(),
                    "kickoff": kickoff.isoformat(),
                    "matchday": "",
                    "blackout": False,
                    "source": "spfl.co.uk",
                })
            except Exception as e:
                log.debug(f"SPFL website card: {e}")

    except Exception as e:
        log.warning(f"SPFL website scrape failed for {comp_code}: {e}")

    return fixtures


def scrape_spfl_fixtures() -> list:
    """Main entry — scrapes all Scottish competitions."""
    all_fixtures = []

    # League competitions
    for comp_code, league_id in SPFL_LEAGUE_IDS.items():
        log.info(f"Scraping {comp_code} from thesportsdb...")
        fixtures = _fetch_sportsdb_league(league_id, comp_code)
        if not fixtures:
            log.info(f"  Fallback to spfl.co.uk for {comp_code}")
            fixtures = _fetch_spfl_website(comp_code)
        log.info(f"  {comp_code}: {len(fixtures)} fixtures")
        all_fixtures.extend(fixtures)

    # Scottish Cup
    log.info("Scraping Scottish Cup...")
    cup_fixtures = _fetch_sportsdb_cup(SCUP_ID, "SCUP")
    if not cup_fixtures:
        log.info("  Fallback to spfl.co.uk for Scottish Cup")
        cup_fixtures = _fetch_spfl_website("SCUP")
    log.info(f"  SCUP: {len(cup_fixtures)} fixtures")
    all_fixtures.extend(cup_fixtures)

    return all_fixtures


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_spfl_fixtures()
    print(f"Total Scottish fixtures: {len(results)}")
    for f in results[:5]:
        print(f"  {f['competition']} | {f['home_team']} vs {f['away_team']} | {f['kickoff']}")
