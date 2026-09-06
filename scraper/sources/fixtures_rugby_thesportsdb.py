"""
fixtures_rugby_thesportsdb.py
-----------------------------
Rugby Union fixture source: TheSportsDB v1 API (free key "123").

League IDs verified 6 Sep 2026 against thesportsdb.com:
    4714  Six Nations Championship          (season "2027")
    4414  English Prem Rugby                (season "2026-2027")
    4446  United Rugby Championship         (season "2026-2027")
    4430  French Top 14                     (season "2026-2027")
    4550  European Rugby Champions Cup      (season "2026-2027")
    5418  European Rugby Challenge Cup      (season "2026-2027")
    5852  Nations Championship              (season "2026")
    4551  Super Rugby                       (season "2027")

IMPORTANT (differs from the football scraper's assumption): on the free key
`eventsnextleague.php` returns only ONE event for these leagues, whereas
`eventsseason.php?id=..&s=<season>` returns the whole season. So this
module uses eventsseason first (trying the league's strCurrentSeason and
the following season string) and only falls back to eventsnextleague.

Times: TheSportsDB gives UTC in dateEvent/strTime and local in
dateEventLocal/strTimeLocal. We use the UTC pair.

Offline testing: set RUGBY_TSDB_CACHE_DIR to a folder of files named
<league_id>_<season>.json (raw API responses) and no HTTP call is made.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://www.thesportsdb.com/api/v1/json"
API_KEY = os.environ.get("THESPORTSDB_API_KEY", "123")
CACHE_DIR = os.environ.get("RUGBY_TSDB_CACHE_DIR", "").strip()

# How far ahead to publish, per competition (days). Today's matches are
# always kept until midnight UK (same rule as football).
RUGBY_TSDB_COMPETITIONS = {
    "4714": {"code": "SIXN",  "display": "Six Nations",               "days": 120},
    "4414": {"code": "PREM",  "display": "Gallagher PREM",            "days": 45},
    "4446": {"code": "URC",   "display": "United Rugby Championship", "days": 45},
    "4430": {"code": "TOP14", "display": "Top 14",                    "days": 45},
    "4550": {"code": "ECC",   "display": "Investec Champions Cup",    "days": 60},
    "5418": {"code": "ECHC",  "display": "EPCR Challenge Cup",        "days": 60},
    "5852": {"code": "NATC",  "display": "Nations Championship",      "days": 120},
    "4551": {"code": "SUPER", "display": "Super Rugby Pacific",       "days": 45},
}

# Team-name tidy-ups so rugby names match liveonsat / common usage.
_NAME_FIXES = [
    (re.compile(r"\s+Rugby$", re.I), ""),          # "England Rugby" -> "England"
    (re.compile(r"^Stade Toulousain$", re.I), "Toulouse"),
    (re.compile(r"^Stade Rochelais$", re.I), "La Rochelle"),
    (re.compile(r"^Stade Français Paris$", re.I), "Stade Français"),
    (re.compile(r"^Union Bordeaux Bègles$", re.I), "Bordeaux-Bègles"),
    (re.compile(r"^ASM Clermont Auvergne$", re.I), "Clermont"),
    (re.compile(r"^Montpellier Hérault Rugby$", re.I), "Montpellier"),
    (re.compile(r"^RC Toulonnais$", re.I), "Toulon"),
    (re.compile(r"^Aviron Bayonnais$", re.I), "Bayonne"),
    (re.compile(r"^Section Paloise$", re.I), "Pau"),
    (re.compile(r"^Castres Olympique$", re.I), "Castres"),
    (re.compile(r"^USA Perpignan$", re.I), "Perpignan"),
    (re.compile(r"^Lyon OU$", re.I), "Lyon"),
    (re.compile(r"^Racing 92$", re.I), "Racing 92"),
    (re.compile(r"^Bath Rugby$", re.I), "Bath"),
    (re.compile(r"^Glasgow$", re.I), "Glasgow Warriors"),
    (re.compile(r"^Racing (Métro|Metro) 92$", re.I), "Racing 92"),
    (re.compile(r"^The Sharks$", re.I), "Sharks"),
    (re.compile(r"^Cardiff Rugby$", re.I), "Cardiff"),
    (re.compile(r"^Newcastle Red Bulls$", re.I), "Newcastle Red Bulls"),
]


def _abbr(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())[:3] or "XXX"


def clean_team(name: str) -> str:
    s = (name or "").strip()
    for pat, rep in _NAME_FIXES:
        s = pat.sub(rep, s)
    return s.strip()


def _http_json(url: str, params: dict) -> dict | None:
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=20,
                             headers={"Accept": "application/json"})
            if r.status_code == 429:
                logger.warning("[rugby_tsdb] rate limited — sleeping 10s")
                time.sleep(10)
                continue
            if r.status_code != 200:
                logger.warning(f"[rugby_tsdb] HTTP {r.status_code} for {params}")
                return None
            return r.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[rugby_tsdb] request failed ({params}): {e}")
            time.sleep(2)
    return None


def _cached(name: str) -> dict | None:
    if not CACHE_DIR:
        return None
    p = os.path.join(CACHE_DIR, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _current_season(league_id: str) -> str | None:
    c = _cached(f"{league_id}_league.json")
    data = c or _http_json(f"{API_BASE}/{API_KEY}/lookupleague.php", {"id": league_id})
    try:
        return (data["leagues"][0].get("strCurrentSeason") or "").strip() or None
    except Exception:
        return None


def _next_season_string(season: str) -> str | None:
    """'2026-2027' -> '2027-2028'; '2026' -> '2027'."""
    m = re.fullmatch(r"(\d{4})-(\d{4})", season or "")
    if m:
        return f"{int(m.group(1)) + 1}-{int(m.group(2)) + 1}"
    m = re.fullmatch(r"\d{4}", season or "")
    if m:
        return str(int(season) + 1)
    return None


def _season_events(league_id: str, season: str) -> list:
    c = _cached(f"{league_id}_{season}.json")
    data = c or _http_json(f"{API_BASE}/{API_KEY}/eventsseason.php",
                           {"id": league_id, "s": season})
    return (data or {}).get("events") or []


def _next_events(league_id: str) -> list:
    c = _cached(f"{league_id}_next.json")
    data = c or _http_json(f"{API_BASE}/{API_KEY}/eventsnextleague.php", {"id": league_id})
    return (data or {}).get("events") or []


def _parse_kickoff(date_str: str, time_str: str | None) -> str | None:
    if not date_str:
        return None
    t = (time_str or "00:00:00").strip()
    if "+" in t:
        t = t.split("+")[0]
    if len(t) == 5:
        t += ":00"
    try:
        dt = datetime.fromisoformat(f"{date_str}T{t}").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _stage_from_round(rnd: str | None, event_name: str) -> str:
    n = (event_name or "").lower()
    for word, stage in (("final", "FINAL"), ("semi", "SEMI_FINAL"),
                        ("quarter", "QUARTER_FINAL"), ("play-off", "PLAYOFF"),
                        ("playoff", "PLAYOFF")):
        if word in n:
            return stage
    return "REGULAR_SEASON"


def _normalise(event: dict, comp: dict, now: datetime) -> dict | None:
    home = clean_team(event.get("strHomeTeam"))
    away = clean_team(event.get("strAwayTeam"))
    kickoff = _parse_kickoff(event.get("dateEvent", ""), event.get("strTime"))
    if not home or not away or not kickoff:
        return None
    ko = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    # keep from start of today (UTC) to N days ahead
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if ko < start or ko > now + timedelta(days=comp["days"]):
        return None
    if (event.get("strPostponed") or "").lower() == "yes":
        status = "POSTPONED"
    else:
        status = event.get("strStatus") or ""
    rnd = event.get("intRound")
    try:
        matchday = int(rnd) if rnd not in (None, "", "0") else None
    except ValueError:
        matchday = None
    date_str = kickoff[:10]
    return {
        "id":          f"{comp['code'].lower()}_{_abbr(home)}_{_abbr(away)}_{date_str}",
        "sport":       "rugby_union",
        "competition": comp["display"],
        "comp_code":   comp["code"],
        "home_team":   home,
        "away_team":   away,
        "kickoff":     kickoff,
        "matchday":    matchday,
        "stage":       _stage_from_round(rnd, event.get("strEvent", "")),
        "group":       event.get("strGroup") or None,
        "venue":       event.get("strVenue") or None,
        "status":      status,
        "source":      "thesportsdb",
        "tsdb_id":     event.get("idEvent"),
    }


def scrape_fixtures(competitions: dict | None = None) -> list:
    """Return normalised rugby fixtures for all configured competitions."""
    comps = competitions or RUGBY_TSDB_COMPETITIONS
    now = datetime.now(timezone.utc)
    out, seen = [], set()

    for league_id, comp in comps.items():
        events = []
        season = _current_season(league_id)
        candidates = [s for s in (season, _next_season_string(season)) if s]
        for s in candidates:
            evs = _season_events(league_id, s)
            if evs:
                events.extend(evs)
            time.sleep(0.6)   # free tier: 30 req/min
        if not events:
            events = _next_events(league_id)

        added = 0
        for ev in events:
            fx = _normalise(ev, comp, now)
            if fx and fx["id"] not in seen:
                seen.add(fx["id"])
                out.append(fx)
                added += 1
        logger.info(f"[rugby_tsdb] {comp['display']} (id={league_id}, "
                    f"seasons={candidates}): {added} fixtures in window "
                    f"(of {len(events)} returned)")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    fx = scrape_fixtures()
    print(json.dumps(fx[:5], indent=1, ensure_ascii=False))
    print(f"{len(fx)} rugby fixtures")
