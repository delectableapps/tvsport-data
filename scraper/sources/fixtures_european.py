"""
fixtures_european.py — European Leagues Fixture Scraper
Competitions: La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga
Source: thesportsdb.com API (primary) + official league sites (fallback)

Returns list of fixture dicts compatible with merger.py
"""
import logging
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# thesportsdb league IDs — all confirmed from thesportsdb.com URLs
EUROPEAN_LEAGUES = {
    "LALIGA":     {"id": "4335", "name": "La Liga",       "country": "Spain"},
    "BUNDESLIGA": {"id": "4331", "name": "Bundesliga",    "country": "Germany"},
    "SERIEA":     {"id": "4332", "name": "Serie A",       "country": "Italy"},
    "SERIEB":     {"id": "4399", "name": "Serie B",       "country": "Italy"},
    "LIGUE1":     {"id": "4334", "name": "Ligue 1",       "country": "France"},
    "EREDIVISIE": {"id": "4337", "name": "Eredivisie",    "country": "Netherlands"},
    "PRIMEIRA":   {"id": "4344", "name": "Primeira Liga", "country": "Portugal"},
}

# Fallback official site URLs — using more stable endpoints
OFFICIAL_URLS = {
    "LALIGA":     "https://www.laliga.com/en-GB/laliga-easports/calendar",
    "BUNDESLIGA": "https://www.bundesliga.com/en/bundesliga/schedule",
    "SERIEA":     "https://www.legaseriea.it/en/serie-a/calendar-and-results",
    "LIGUE1":     "https://www.ligue1.com/calendar-results",
    "EREDIVISIE": "https://eredivisie.nl/en/schedule",
    "PRIMEIRA":   "https://www.ligaportugal.pt/en/liga/calendar",
}

SEASON = "2025-2026"
SPORTSDB_API = "https://www.thesportsdb.com/api/v1/json/3"
HEADERS = {"User-Agent": "TVsport.live fixture scraper (contact: admin@tvsport.live)"}


def _fetch_sportsdb(league_id: str, comp_code: str) -> list:
    """Fetch fixtures from thesportsdb for a European league."""
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
                    "id": f"{comp_code.lower()}-{ev.get('idEvent', '')}",
                    "competition": comp_code,
                    "home_team": ev.get("strHomeTeam", ""),
                    "away_team": ev.get("strAwayTeam", ""),
                    "kickoff": kickoff.isoformat(),
                    "matchday": str(ev.get("intRound", "")),
                    "blackout": False,
                    "source": "thesportsdb",
                })
            except Exception as e:
                log.debug(f"{comp_code} event parse: {e}")

    except Exception as e:
        log.warning(f"thesportsdb failed for {comp_code}: {e}")

    return fixtures


def _fetch_laliga_fallback() -> list:
    """Fallback scraper for La Liga official site."""
    fixtures = []
    try:
        resp = requests.get(OFFICIAL_URLS["LALIGA"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select(".match-card, .fixture-item, [class*=match]"):
            try:
                home = card.select_one("[class*=local], [class*=home]")
                away = card.select_one("[class*=visitor], [class*=away]")
                ko = card.select_one("time, [class*=time], [class*=date]")
                if not home or not away or not ko:
                    continue
                kickoff_str = ko.get("datetime") or ko.text.strip()
                kickoff = datetime.fromisoformat(kickoff_str)
                fixtures.append({
                    "id": f"laliga-web-{home.text.strip()[:4]}",
                    "competition": "LALIGA",
                    "home_team": home.text.strip(),
                    "away_team": away.text.strip(),
                    "kickoff": kickoff.isoformat(),
                    "matchday": "",
                    "blackout": False,
                    "source": "laliga.com",
                })
            except Exception:
                continue
    except Exception as e:
        log.warning(f"La Liga fallback failed: {e}")
    return fixtures


def _fetch_bundesliga_fallback() -> list:
    """Fallback scraper for Bundesliga official site."""
    fixtures = []
    try:
        resp = requests.get(OFFICIAL_URLS["BUNDESLIGA"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("[class*=match], [class*=fixture]"):
            try:
                home = card.select_one("[class*=home]")
                away = card.select_one("[class*=guest], [class*=away]")
                ko = card.select_one("time")
                if not home or not away or not ko:
                    continue
                kickoff = datetime.fromisoformat(ko.get("datetime", ""))
                fixtures.append({
                    "id": f"bundesliga-web-{home.text.strip()[:4]}",
                    "competition": "BUNDESLIGA",
                    "home_team": home.text.strip(),
                    "away_team": away.text.strip(),
                    "kickoff": kickoff.isoformat(),
                    "matchday": "",
                    "blackout": False,
                    "source": "bundesliga.com",
                })
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Bundesliga fallback failed: {e}")
    return fixtures


def scrape_european_fixtures() -> list:
    """
    Main entry point. Scrapes all European league competitions.
    Uses thesportsdb primary, official site as fallback.
    Returns combined list.
    """
    all_fixtures = []

    for comp_code, meta in EUROPEAN_LEAGUES.items():
        log.info(f"Scraping {meta['name']} ({comp_code})...")
        fixtures = _fetch_sportsdb(meta["id"], comp_code)

        if not fixtures:
            log.info(f"  thesportsdb empty, trying fallback for {comp_code}...")
            if comp_code == "LALIGA":
                fixtures = _fetch_laliga_fallback()
            elif comp_code == "BUNDESLIGA":
                fixtures = _fetch_bundesliga_fallback()
            # Other leagues: add fallbacks similarly as needed

        log.info(f"  {comp_code}: {len(fixtures)} fixtures")
        all_fixtures.extend(fixtures)

    return all_fixtures


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_european_fixtures()
    print(f"\nTotal European fixtures: {len(results)}")
    by_comp = {}
    for f in results:
        by_comp.setdefault(f["competition"], []).append(f)
    for comp, fxs in sorted(by_comp.items()):
        print(f"  {comp}: {len(fxs)} fixtures")
    print("\nSample:")
    for f in results[:3]:
        print(f"  {f['competition']} | {f['home_team']} vs {f['away_team']} | {f['kickoff']}")
