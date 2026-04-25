"""
openfootball_fetcher.py
-----------------------
Fetches league fixtures from the openfootball public-domain JSON feeds.

openfootball publishes two tiers of JSON data:

  1. The umbrella repo `openfootball/football.json` holds top-level league
     files named like `en.1.json` (EPL), `en.2.json` (Championship), etc.
     served from raw.githubusercontent.com. This is the most reliable source
     for the core leagues across Europe.

  2. Per-country repos like `openfootball/england` publish richer trees
     (including lower leagues) via GitHub Pages at
     https://openfootball.github.io/<repo>/<season>/<file>.json

Both feeds use the same match schema:
    { "round": "Matchday 7", "date": "2025-10-04", "time": "15:00",
      "team1": "Arsenal FC", "team2": "West Ham United",
      "score": { ... } }

We fetch whatever we can, normalise each match to a common dict shape,
and let merger.py deduplicate against other sources.

Public domain — CC0-1.0. No API key required. Rate-limit friendly: one
HTTP GET per league per nightly run (~30 requests total).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Season helpers
# ---------------------------------------------------------------------------

def current_season_slug(today: datetime | None = None) -> str:
    """
    Return season as 'YYYY-YY'. European leagues roll over in early July.
    In June or earlier → previous season; from July onwards → this season.
    """
    today = today or datetime.now(timezone.utc)
    year = today.year
    if today.month < 7:
        return f"{year - 1}-{str(year)[-2:]}"
    return f"{year}-{str(year + 1)[-2:]}"


# ---------------------------------------------------------------------------
# Source configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeedSpec:
    """One openfootball JSON feed."""
    competition_code: str   # stable internal code used by merger/rights_db
    display_name: str       # human-readable name
    country: str            # ISO-ish, two-letter lowercase
    url_template: str       # must contain {season}
    # If openfootball doesn't publish this for the current season, the fetch
    # will 404 — that's fine, we just log and skip.

    def url_for(self, season: str) -> str:
        return self.url_template.format(season=season)


# Raw GitHub base. Using raw.githubusercontent avoids GitHub Pages build lag
# when a season's data has just been added.
RAW = "https://raw.githubusercontent.com/openfootball/football.json/master"

# Per-country Pages base (used only for lower leagues not in the umbrella repo).
PAGES = "https://openfootball.github.io"

FEEDS: tuple[FeedSpec, ...] = (
    # ---------- England ----------
    FeedSpec("EPL",     "English Premier League",  "en",
             f"{RAW}/{{season}}/en.1.json"),
    FeedSpec("CHAMP",   "EFL Championship",        "en",
             f"{RAW}/{{season}}/en.2.json"),
    # League One / League Two / National League aren't in the umbrella repo.
    # They live in the /england country repo, published via Pages.
    FeedSpec("L1",      "EFL League One",          "en",
             f"{PAGES}/england/{{season}}/3-league1.json"),
    FeedSpec("L2",      "EFL League Two",          "en",
             f"{PAGES}/england/{{season}}/4-league2.json"),
    FeedSpec("NAT",     "National League",         "en",
             f"{PAGES}/england/{{season}}/5-nationalleague.json"),

    # ---------- Scotland ----------
    # The umbrella repo keys Scotland as sc.1. Lower tiers live in /europe.
    FeedSpec("SPFL",    "Scottish Premiership",    "sc",
             f"{RAW}/{{season}}/sc.1.json"),

    # ---------- Germany ----------
    FeedSpec("BUND",    "Bundesliga",              "de",
             f"{RAW}/{{season}}/de.1.json"),
    FeedSpec("BUND2",   "2. Bundesliga",           "de",
             f"{RAW}/{{season}}/de.2.json"),
    FeedSpec("DE3",     "3. Liga",                 "de",
             f"{RAW}/{{season}}/de.3.json"),

    # ---------- Spain ----------
    FeedSpec("LL",      "La Liga",                 "es",
             f"{RAW}/{{season}}/es.1.json"),
    FeedSpec("LL2",     "La Liga 2",               "es",
             f"{RAW}/{{season}}/es.2.json"),

    # ---------- Italy ----------
    FeedSpec("SA",      "Serie A",                 "it",
             f"{RAW}/{{season}}/it.1.json"),
    FeedSpec("SB",      "Serie B",                 "it",
             f"{RAW}/{{season}}/it.2.json"),

    # ---------- France ----------
    FeedSpec("L1F",     "Ligue 1",                 "fr",
             f"{RAW}/{{season}}/fr.1.json"),
    FeedSpec("L2F",     "Ligue 2",                 "fr",
             f"{RAW}/{{season}}/fr.2.json"),

    # ---------- Netherlands / Portugal / Brazil ----------
    FeedSpec("ERE",     "Eredivisie",              "nl",
             f"{RAW}/{{season}}/nl.1.json"),
    FeedSpec("PPL",     "Primeira Liga",           "pt",
             f"{RAW}/{{season}}/pt.1.json"),
    FeedSpec("BRA",     "Brasileirão Série A",     "br",
             f"{RAW}/{{season}}/br.1.json"),
)


# ---------------------------------------------------------------------------
# Fetch + normalise
# ---------------------------------------------------------------------------

@dataclass
class Match:
    """Common match shape that merger.py already consumes."""
    competition_code: str
    competition_name: str
    country: str
    round_label: str | None
    kickoff_utc: str | None     # ISO-8601 if both date+time, else None
    date: str                   # always present: YYYY-MM-DD
    time_local: str | None      # HH:MM as published by openfootball, may be None
    home: str
    away: str
    status: str                 # "scheduled" | "finished"
    score_ft: list[int] | None
    source: str = "openfootball"
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d.pop("raw", None)
        return d


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "tvsport.live scraper (+https://tvsport.live)",
        "Accept": "application/json",
    })
    return s


def _fetch_json(session: requests.Session, url: str, timeout: float = 20.0) -> dict | None:
    try:
        r = session.get(url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("openfootball: network error for %s -> %s", url, e)
        return None
    if r.status_code == 404:
        log.info("openfootball: no data at %s (404)", url)
        return None
    if r.status_code != 200:
        log.warning("openfootball: unexpected %s for %s", r.status_code, url)
        return None
    try:
        return r.json()
    except json.JSONDecodeError as e:
        log.warning("openfootball: bad JSON from %s -> %s", url, e)
        return None


def _normalise_match(raw: dict, feed: FeedSpec) -> Match | None:
    date = raw.get("date")
    if not date:
        return None
    time_local = raw.get("time")  # may be absent
    kickoff_utc = None
    if time_local:
        # openfootball times are the local kickoff time as published by the
        # league — not necessarily UTC. We pass them through as-is and let
        # a downstream enricher (football-data.org, EPG) provide a UTC value
        # when available. If nothing else provides it, the front-end already
        # handles date-only fixtures (time is shown as TBC).
        try:
            # Still emit a naive ISO string so merger.py can match on it.
            kickoff_utc = f"{date}T{time_local}:00"
        except Exception:
            kickoff_utc = None

    score = raw.get("score") or {}
    ft = score.get("ft")
    status = "finished" if ft else "scheduled"

    home = raw.get("team1")
    away = raw.get("team2")
    if not home or not away:
        return None

    # Some feeds wrap team names in objects with {name, code}; flatten those.
    if isinstance(home, dict):
        home = home.get("name")
    if isinstance(away, dict):
        away = away.get("name")

    return Match(
        competition_code=feed.competition_code,
        competition_name=feed.display_name,
        country=feed.country,
        round_label=raw.get("round"),
        kickoff_utc=kickoff_utc,
        date=date,
        time_local=time_local,
        home=home,
        away=away,
        status=status,
        score_ft=ft if isinstance(ft, list) else None,
        raw=raw,
    )


def fetch_feed(
    feed: FeedSpec,
    season: str,
    session: requests.Session | None = None,
) -> list[Match]:
    """Fetch and normalise one feed. Empty list on any error."""
    s = session or _session()
    url = feed.url_for(season)
    log.info("openfootball: fetching %s (%s)", feed.competition_code, url)
    payload = _fetch_json(s, url)
    if not payload:
        return []

    raw_matches = payload.get("matches") or []
    # Some cup-style feeds use 'rounds' instead of flat 'matches'; flatten those.
    if not raw_matches and "rounds" in payload:
        for rnd in payload["rounds"]:
            for m in rnd.get("matches", []):
                # Carry the round name inward so _normalise_match sees it.
                m.setdefault("round", rnd.get("name"))
                raw_matches.append(m)

    out: list[Match] = []
    for raw in raw_matches:
        m = _normalise_match(raw, feed)
        if m:
            out.append(m)
    log.info("openfootball: %s -> %d matches", feed.competition_code, len(out))
    return out


def fetch_all(
    season: str | None = None,
    feeds: Iterable[FeedSpec] | None = None,
    pause_seconds: float = 0.1,
) -> list[Match]:
    """Fetch every configured feed. Returns a flat list of Match objects."""
    season = season or current_season_slug()
    feeds = tuple(feeds) if feeds is not None else FEEDS
    s = _session()
    all_matches: list[Match] = []
    for feed in feeds:
        all_matches.extend(fetch_feed(feed, season, session=s))
        # Polite pause — raw.githubusercontent.com is generous but there's
        # no reason to hammer it.
        time.sleep(pause_seconds)
    log.info("openfootball: total %d matches across %d feeds",
             len(all_matches), len(feeds))
    return all_matches


# ---------------------------------------------------------------------------
# CLI entry point — handy for local testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    ap = argparse.ArgumentParser(description="Fetch openfootball feeds")
    ap.add_argument("--season", help="Season slug e.g. 2025-26 (default: auto)")
    ap.add_argument("--competition", help="Only fetch one competition code")
    ap.add_argument("--out", help="Write matches as JSON to this path")
    args = ap.parse_args()

    chosen = FEEDS
    if args.competition:
        chosen = tuple(f for f in FEEDS if f.competition_code == args.competition)
        if not chosen:
            raise SystemExit(
                f"No feed with competition_code={args.competition!r}. "
                f"Known codes: {[f.competition_code for f in FEEDS]}"
            )

    matches = fetch_all(season=args.season, feeds=chosen)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump([m.to_dict() for m in matches], fh, indent=2, ensure_ascii=False)
        print(f"Wrote {len(matches)} matches to {args.out}")
    else:
        for m in matches[:20]:
            print(f"{m.date} {m.time_local or 'TBC':5s}  "
                  f"{m.competition_code:5s}  {m.home} vs {m.away}")
        if len(matches) > 20:
            print(f"... and {len(matches) - 20} more")
