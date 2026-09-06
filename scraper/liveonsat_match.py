"""
liveonsat_match.py
------------------
Matches liveonsat.com scrape output (from liveonsat_fetcher.py) against the
pipeline's fixture list, and exposes per-territory broadcaster confirmations.

This is the piece that resolves the Premier Sports Ireland 3pm problem:
static rights data cannot tell us WHICH single 3pm-BST Saturday EPL match
Premier Sports Ireland selected. liveonsat lists it explicitly per match.

Used by merger.py as a Tier-1 confirmation source, sitting alongside EPG:
    from liveonsat_match import LiveOnSatIndex
    los = LiveOnSatIndex.build()                       # fetches + indexes
    los_data = los.lookup_all_fixtures(fixtures)       # {fixture_id: {...}}

Returned shape mirrors epg_fetcher's lookup_all_fixtures() so merger.py can
treat it the same way:
    {
      "pl_BOU_EVE_2026-08-29": {
         "Republic of Ireland": {"broadcaster": "Premier Sports",
                                 "channels": ["Premier Sports 1"],
                                 "is_live": True},
         "United Kingdom": {...},
         ...
      }
    }

Fails soft: any network/parse error returns an empty index and logs a
warning, so the nightly pipeline never breaks because liveonsat is down.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Which liveonsat pages to pull. UK page is essential (it carries the
# Premier Sports Ireland listings); the others improve European coverage.
DEFAULT_PAGES = ["uk", "germany", "italy", "france", "spain",
                 "netherlands", "portugal"]

# Kick-off tolerance when matching liveonsat rows to our fixtures.
KICKOFF_TOLERANCE = timedelta(minutes=20)

# ─────────────────────────────────────────────────────────────────────────────
# Channel name → (territory, broadcaster) mapping.
# Ordered: the FIRST pattern that matches wins, so put specific before generic
# ("Sky Sports Football HD" must beat a bare "Sky" rule). This is what stops
# the Sky Deutschland-on-ROI class of bug: every rule is anchored to a
# distinctive token, never a bare substring like "Sky".
# ─────────────────────────────────────────────────────────────────────────────
CHANNEL_TERRITORY_RULES = [
    # --- Republic of Ireland (checked before UK: "Premier Sports 1 Ireland") ---
    (r"premier sports.*ireland",        "Republic of Ireland", "Premier Sports"),
    (r"\bvirgin media\b",               "Republic of Ireland", "Virgin Media"),
    (r"\brte\b|\brté\b",                "Republic of Ireland", "RTE"),
    (r"\bloi tv\b",                     "Republic of Ireland", "LOI TV"),
    (r"dazn ireland",                   "Republic of Ireland", "DAZN Ireland"),
    (r"\bbbc sport ni\b",               "Republic of Ireland", "BBC NI"),

    # --- United Kingdom ---
    (r"premier sports.*(uk|gb player)", "United Kingdom", "Premier Sports"),
    (r"sky sports|sky go uk|sky uk ultra|sky mix|sky one uk",
                                        "United Kingdom", "Sky Sports"),
    (r"tnt sports",                     "United Kingdom", "TNT Sports"),
    (r"sky sports\+",                   "United Kingdom", "Sky Sports"),
    (r"\bbbc\b(?!.*\bni\b)",            "United Kingdom", "BBC"),
    (r"\bitv\b|\bitvx\b|\bstv\b|\butv\b","United Kingdom", "ITV"),
    (r"dazn great britain",             "United Kingdom", "DAZN"),
    (r"hbo max \(uk only\)",            "United Kingdom", "HBO Max"),
    (r"prime video uk",                 "United Kingdom", "Prime Video"),
    (r"\bs4c\b|sgorio",                 "United Kingdom", "S4C"),
    (r"\bnifl tv\b",                    "United Kingdom", "NIFL TV"),

    # --- Germany ---
    (r"sky sport bundesliga|sky go germany|sky sport top event|"
     r"sky sport premier league de\b|sky sport .*\bde$",
                                        "Germany", "Sky Deutschland"),
    (r"wow deutsch",                    "Germany", "WOW"),
    (r"dazn deutsch",                   "Germany", "DAZN"),
    (r"magenta sport",                  "Germany", "Magenta Sport"),
    (r"rtl deutschland|rtl\+ deutschland|nitro deutschland",
                                        "Germany", "RTL"),
    (r"sat\.1 deutschland",             "Germany", "SAT.1"),
    (r"ard das erste|dfb play tv|dfb\.tv",
                                        "Germany", "ARD / DFB"),

    # --- Italy ---
    (r"dazn \d? ?italia|dazn italia",   "Italy", "DAZN IT"),
    (r"sky sport (calcio|251|mix italia|max italia)|sky go italy",
                                        "Italy", "Sky Sport Italia"),

    # --- France ---
    (r"ligue 1\+",                      "France", "Ligue 1+"),
    (r"canal\+ (foot|sport|live|france)","France", "Canal+"),
    (r"bein sports france|bein connect france",
                                        "France", "beIN Sports FR"),
    (r"dazn france",                    "France", "DAZN France"),

    # --- Spain ---
    (r"movistar plus|m\+ laliga",       "Spain", "Movistar LaLiga"),
    (r"dazn (laliga|españa|espana)",    "Spain", "DAZN"),

    # --- Netherlands / Portugal ---
    (r"espn \d nederland|espn extra|espn nederland",
                                        "Netherlands", "ESPN NL"),
    (r"ziggo sport",                    "Netherlands", "Ziggo Sport"),
    (r"viaplay nederland",              "Netherlands", "Viaplay NL"),
    (r"sport tv\d? portugal|sport tv\d",
                                        "Portugal", "Sport TV"),
    (r"dazn \d portugal|dazn portugal", "Portugal", "DAZN PT"),
    (r"benfica tv|\bbtv\b",             "Portugal", "Benfica TV"),

    # --- Selected other territories we already list ---
    (r"bein sports mena|bein connect mena",
                                        "Middle East & N. Africa", "beIN Sports"),
    (r"supersport",                     "Sub-Saharan Africa", "SuperSport"),
    (r"stan sport australia",           "Australia", "Stan Sport"),
    (r"optus sport",                    "Australia", "Optus Sport"),
    (r"paramount\+ usa",                "United States", "Paramount+"),
    (r"peacock premium usa|usa network","United States", "Peacock / NBC"),
    (r"cbs sports network usa",         "United States", "CBS Sports"),
    (r"dazn canada|fubotv canada",      "Canada", "DAZN / Fubo"),
    (r"dazn japan",                     "Japan", "DAZN JP"),
    (r"sport 24 (at sea|in flight)",    "International", "Sport 24"),
    (r"^premier league\+",              "International", "Premier League+"),
    (r"dazn worldwide",                 "International", "DAZN Worldwide"),
    (r"sky sport \d+ austria|sky sport austria", "Austria", "Sky Austria"),
    (r"viaplay (norge|suomi|sverige|danmark)|viaplay \d urheilu",
                                        "Nordics", "Viaplay"),
    (r"bein connect t.rkiye|bein sports t.rkiye", "Turkey", "beIN Turkey"),
]

_COMPILED = [(re.compile(p, re.I), t, b) for p, t, b in CHANNEL_TERRITORY_RULES]


def classify_channel(name: str):
    """Return (territory, broadcaster) or (None, None) if unrecognised."""
    for pat, territory, broadcaster in _COMPILED:
        if pat.search(name):
            return territory, broadcaster
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Team-name normalisation — must stay in step with rights_db._normalise_team_name
# ─────────────────────────────────────────────────────────────────────────────

_SUFFIXES = (" fc", " afc", " cf", " sc", " ac", " bc", " sad", " 1913",
             " 1907", " calcio", " football club")
_PREFIXES = ("fc ", "afc ", "ac ", "as ", "ss ", "ssc ", "us ", "sv ", "vfb ",
             "vfl ", "tsg ", "rc ", "rcd ", "cd ", "cf ", "club ", "sl ",
)
_CONNECTORS = (" de ", " del ", " e ", " di ", " du ")

_ALIASES = {
    "man city": "manchester city", "man utd": "manchester united",
    "man united": "manchester united", "spurs": "tottenham",
    "tottenham hotspur": "tottenham", "wolves": "wolverhampton wanderers",
    "brighton h a": "brighton hove albion", "brighton": "brighton hove albion",
    "west brom": "west bromwich albion", "nottm forest": "nottingham forest",
    "notts forest": "nottingham forest", "preston n e": "preston north end",
    "sheff utd": "sheffield united", "sheff wed": "sheffield wednesday",
    "qpr": "queens park rangers", "psg": "paris saint germain",
    "paris st germain": "paris saint germain", "bayern munich": "bayern munchen",
    "monchengladbach": "borussia monchengladbach",
    "gladbach": "borussia monchengladbach", "dortmund": "borussia dortmund",
    "inter milan": "internazionale", "inter": "internazionale",
    "milan": "ac milan", "roma": "as roma", "napoli": "ssc napoli",
    "barcelona": "barcelona", "real madrid": "real madrid",
    "atletico madrid": "atletico de madrid", "sporting cp": "sporting",
    "porto": "porto", "benfica": "benfica",
    "internazionale milano": "internazionale",
    "sporting clube de portugal": "sporting", "sporting clube portugal": "sporting",
    "sporting cp": "sporting", "sporting lisbon": "sporting",
    "sporting clube braga": "sporting braga", "sporting clube de braga": "sporting braga", "st mirren": "saint mirren", "st johnstone": "saint johnstone",
    "hearts": "heart of midlothian", "st pauli": "saint pauli",
}


def normalise_team(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = s.encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for p in _PREFIXES:          # prefixes BEFORE connectors, else
        if s.startswith(p):      # "sporting clube de portugal" loses its
            s = s[len(p):]       # prefix anchor and collapses to "portugal"
            break
    for c in _CONNECTORS:
        s = s.replace(c, " ")
    for suf in _SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = re.sub(r"\s+", " ", s).strip()
    return _ALIASES.get(s, s)


def _parse_iso(s: str):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


class LiveOnSatIndex:
    """Indexes liveonsat fixtures for lookup by (home, away, kickoff)."""

    def __init__(self, fixtures: list | None = None):
        self.rows = fixtures or []
        self._by_pair = {}
        for r in self.rows:
            key = (normalise_team(r.get("home", "")),
                   normalise_team(r.get("away", "")))
            self._by_pair.setdefault(key, []).append(r)

    # ---------------------------------------------------------------- build
    @classmethod
    def build(cls, pages: list | None = None):
        """Obtain liveonsat data. Never raises — returns empty index on error.

        Source order:
          1. LIVEONSAT_JSON_URL env var — a pre-scraped liveonsat.json (e.g. a
             Dropbox shared link written by run_liveonsat.bat on a home PC).
             Used because liveonsat.com blocks GitHub Actions' IP ranges.
          2. Direct fetch from liveonsat.com (works from residential IPs).
        """
        import os
        path = os.environ.get("LIVEONSAT_JSON_PATH", "").strip()
        if path and os.path.exists(path):
            idx = cls._from_file(path)
            if idx is not None:
                return idx
        url = os.environ.get("LIVEONSAT_JSON_URL", "").strip()
        if url:
            idx = cls._from_url(url)
            if idx is not None:
                return idx
            logger.warning("[liveonsat] pre-scraped JSON unusable — "
                           "trying direct fetch")
        return cls._direct(pages)

    MAX_AGE_DAYS = 4   # older than this and the pick may have changed

    @classmethod
    def _from_file(cls, path: str):
        try:
            import json
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            return cls._from_doc(data, f"file {path}")
        except Exception as e:
            logger.warning(f"[liveonsat] could not read {path}: {e}")
            return None

    @classmethod
    def _from_doc(cls, data: dict, origin: str):
        from datetime import datetime, timezone
        rows = data.get("fixtures", [])
        fetched = data.get("fetched_at", "")
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(
                fetched.replace("Z", "+00:00"))
            age_days = age.total_seconds() / 86400
        except Exception:
            age_days = None
        if age_days is not None and age_days > cls.MAX_AGE_DAYS:
            logger.warning(f"[liveonsat] {origin} is {age_days:.1f} days old "
                           f"(> {cls.MAX_AGE_DAYS}) - ignoring")
            return None
        if not rows:
            logger.warning(f"[liveonsat] {origin} has 0 fixtures")
            return None
        logger.info(f"[liveonsat] loaded {len(rows)} fixtures from {origin} "
                    f"(fetched {fetched}, pages: "
                    f"{list(data.get('pages', {}).keys())})")
        return cls(rows)

    @classmethod
    def _from_url(cls, url: str):
        try:
            import requests
            from datetime import datetime, timezone
            # Dropbox links: force a direct download rather than the preview page
            if "dropbox.com" in url:
                url = url.replace("?dl=0", "?dl=1").replace("&dl=0", "&dl=1")
                if "dl=1" not in url and "raw=1" not in url:
                    url += ("&" if "?" in url else "?") + "dl=1"
            r = requests.get(url, timeout=60, allow_redirects=True)
            r.raise_for_status()
            return cls._from_doc(r.json(), "LIVEONSAT_JSON_URL")
        except Exception as e:
            logger.warning(f"[liveonsat] could not load LIVEONSAT_JSON_URL: {e}")
            return None

    @classmethod
    def _direct(cls, pages: list | None = None):
        pages = pages or DEFAULT_PAGES
        try:
            import time
            import requests
            from liveonsat_fetcher import fetch_page, parse_page, PAGES

            session = requests.Session()
            rows = []
            for slug in pages:
                if slug not in PAGES:
                    continue
                try:
                    html = fetch_page(slug, session)
                    fx, meta = parse_page(html, slug)
                    rows.extend(fx)
                    logger.info(f"[liveonsat] {slug}: {len(fx)} fixtures "
                                f"(page offset {meta['page_offset']})")
                except Exception as e:
                    logger.warning(f"[liveonsat] {slug} failed: {e}")
                time.sleep(1.5)

            if not rows:
                logger.warning("[liveonsat] no fixtures parsed — "
                               "falling back to EPG/rights only")
            return cls(rows)

        except Exception as e:
            logger.warning(f"[liveonsat] unavailable ({e}) — "
                           f"falling back to EPG/rights only")
            return cls([])

    # --------------------------------------------------------------- lookup
    def find(self, home: str, away: str, kickoff_iso: str):
        """Return the matching liveonsat row, or None."""
        key = (normalise_team(home), normalise_team(away))
        candidates = self._by_pair.get(key)
        if not candidates:
            return None
        ko = _parse_iso(kickoff_iso)
        if ko is None:
            return candidates[0]
        best, best_delta = None, None
        for r in candidates:
            rk = _parse_iso(r.get("kickoff_utc", ""))
            if rk is None:
                continue
            delta = abs(rk - ko)
            if delta <= KICKOFF_TOLERANCE and (best_delta is None
                                               or delta < best_delta):
                best, best_delta = r, delta
        return best

    def territories_for(self, row: dict) -> dict:
        """Collapse a liveonsat row's channel list into territory → broadcaster."""
        out = {}
        for ch in row.get("channels", []):
            territory, broadcaster = classify_channel(ch["name"])
            if not territory:
                continue
            entry = out.setdefault(territory, {
                "broadcaster": broadcaster,
                "channels": [],
                "is_live": True,
            })
            clean = ch["name"].replace(" HD", "").strip()
            if clean not in entry["channels"]:
                entry["channels"].append(clean)
        return out

    def lookup_all_fixtures(self, fixtures: list) -> dict:
        """Mirror epg_fetcher.lookup_all_fixtures(): {fixture_id: {territory: {...}}}"""
        result = {}
        for f in fixtures:
            row = self.find(f.get("home_team", ""), f.get("away_team", ""),
                            f.get("kickoff", ""))
            if not row:
                continue
            terrs = self.territories_for(row)
            if terrs:
                result[f.get("id", "")] = terrs
        logger.info(f"[liveonsat] matched {len(result)}/{len(fixtures)} fixtures")
        return result

    # --------------------------------------------------- ROI 3pm resolution
    def ireland_pick_for_slot(self, fixtures: list, kickoff_iso: str):
        """Of the fixtures in a given kick-off slot, return those liveonsat
        shows on Premier Sports Ireland. Empty list = unconfirmed → the site
        should omit Ireland entirely rather than guess."""
        picks = []
        for f in fixtures:
            if f.get("kickoff") != kickoff_iso:
                continue
            row = self.find(f.get("home_team", ""), f.get("away_team", ""),
                            f.get("kickoff", ""))
            if not row:
                continue
            for ch in row.get("channels", []):
                if re.search(r"premier sports.*ireland", ch["name"], re.I):
                    picks.append(f)
                    break
        return picks


# ═════════════════════════════════════════════════════════════════════════════
# BACKFILL — add fixtures liveonsat has that the primary sources missed.
# Added fixtures are flagged (source="liveonsat", needs_review=True) so the
# nightly report can ask WHY the primary source missed them.
# ═════════════════════════════════════════════════════════════════════════════

# liveonsat competition name -> (our comp_code, our competition name).
# Only competitions the site already publishes. Extend deliberately.
LOS_COMPETITIONS = {
    "English Premier League":   ("PL",     "Premier League"),
    "English Championship":     ("ELC",    "Championship"),
    "English League One":       ("EL1",    "League One"),
    "English League Two":       ("EL2",    "League Two"),
    "English National League":  ("NAT",    "National League"),
    "English League Cup":       ("EFLCUP", "EFL Cup"),
    "English FA Cup":           ("FAC",    "FA Cup"),
    "Scottish Premiership":     ("SP1",    "Scottish Premiership"),
    "Scottish Championship":    ("SCH",    "Scottish Championship"),
    "Scottish Cup":             ("SCUP",   "Scottish Cup"),
    "Scottish League Cup":      ("SLCUP",  "Scottish League Cup"),
    "UEFA Champions League":    ("CL",     "UEFA Champions League"),
    "German Bundesliga":        ("BL1",    "Bundesliga"),
    "Italian Serie A":          ("SA",     "Serie A"),
    "French Ligue 1":           ("FL1",    "Ligue 1"),
    "Spanish La Liga":          ("PD",     "La Liga"),
    "Spanish LaLiga":           ("PD",     "La Liga"),
    "Dutch Eredivisie":         ("DED",    "Eredivisie"),
    "Portuguese Primeira Liga": ("PPL",    "Primeira Liga"),
    "Portuguese Liga":          ("PPL",    "Primeira Liga"),
}

# Which primary source *should* have supplied each competition — used in the
# report so the "why was this missing?" question points somewhere.
EXPECTED_SOURCE = {
    "PL": "football-data.org", "ELC": "football-data.org",
    "CL": "football-data.org", "BL1": "football-data.org",
    "SA": "football-data.org", "FL1": "football-data.org",
    "PD": "football-data.org", "DED": "football-data.org",
    "PPL": "football-data.org",
    "EL1": "TheSportsDB (25-event cap)", "EL2": "TheSportsDB (25-event cap)",
    "NAT": "TheSportsDB", "EFLCUP": "BBC cups scraper", "FAC": "BBC cups scraper",
    "SP1": "Sportmonks", "SCH": "TheSportsDB",
    "SCUP": "BBC cups scraper", "SLCUP": "BBC cups scraper",
}

# Generic club-name furniture only. Deliberately NOT "united"/"city"/"town":
# those distinguish Manchester United from Manchester City.
_STOP = {"fc", "afc", "sc", "cf", "ac", "club", "de", "1901", "1909",
         "1913", "1963", "65", "29", "calcio"}


def _tokens(name: str) -> set:
    return {t for t in normalise_team(name).split() if t not in _STOP}


def _same_side(a: str, b: str) -> bool:
    """Do two team names plausibly denote the same club?
    True if one normalised name contains the other, or their token sets
    overlap by at least half (Jaccard >= 0.5). A single shared city word
    (Sparta Rotterdam / Feyenoord Rotterdam) is NOT enough."""
    na, nb = normalise_team(a), normalise_team(b)
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def _abbr(name: str) -> str:
    n = normalise_team(name).replace(" ", "")
    return (n[:4] or "xxxx").upper()


def _round_to_stage(rnd: str):
    """'Week 4' -> (matchday 4, REGULAR_SEASON); cup rounds -> stage text."""
    m = re.search(r"week\s*(\d+)", rnd or "", re.I)
    if m:
        return int(m.group(1)), "REGULAR_SEASON"
    return None, (rnd or "").strip().upper().replace(" ", "_") or "REGULAR_SEASON"


def backfill_missing(fixtures: list, index: "LiveOnSatIndex"):
    """Return (added_fixtures, probable_mismatches).

    added_fixtures      - liveonsat rows in covered competitions, inside the
                          date window of `fixtures`, with NO plausible match.
                          Shaped like merger fixtures and flagged for review.
    probable_mismatches - liveonsat rows that DO have a same-day, same-comp
                          fixture whose team names partly overlap. These are
                          almost certainly the same match under a different
                          spelling, so they are NOT added (that would create a
                          duplicate). They are reported for the normaliser.
    """
    if not fixtures or not index.rows:
        return [], []
    dates = sorted(f["kickoff"][:10] for f in fixtures if f.get("kickoff"))
    lo, hi = dates[0], dates[-1]
    # Primary sources drop matches once they kick off; liveonsat keeps them
    # up all day. Never backfill anything that has already started.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    exact = set()
    by_day_comp = {}
    for f in fixtures:
        d = f["kickoff"][:10]
        exact.add((normalise_team(f["home_team"]), normalise_team(f["away_team"]), d))
        by_day_comp.setdefault((d, f.get("comp_code")), []).append(f)

    added, mismatches, seen_new = [], [], set()
    for r in index.rows:
        comp = LOS_COMPETITIONS.get(r.get("competition", ""))
        if not comp:
            continue
        code, comp_name = comp
        d = (r.get("kickoff_utc") or "")[:10]
        if not (lo <= d <= hi):
            continue
        if r.get("status") == "POSTPONED":
            continue
        if (r.get("kickoff_utc") or "") <= now_iso:
            continue
        nh, na = normalise_team(r["home"]), normalise_team(r["away"])
        if (nh, na, d) in exact or (nh, na, d) in seen_new:
            continue

        # Fuzzy: same day + same competition + at least one side is
        # plausibly the same club under a different spelling
        near = None
        for f in by_day_comp.get((d, code), []):
            if _same_side(r["home"], f["home_team"]) or \
               _same_side(r["away"], f["away_team"]):
                near = f
                break
        if near:
            mismatches.append({
                "liveonsat": f"{r['home']} v {r['away']}",
                "ours": f"{near['home_team']} v {near['away_team']}",
                "competition": comp_name, "date": d,
            })
            continue

        matchday, stage = _round_to_stage(r.get("round"))
        fid = f"{code.lower()}_{_abbr(r['home'])}_{_abbr(r['away'])}_{d}"
        seen_new.add((nh, na, d))
        added.append({
            "id":           fid,
            "competition":  comp_name,
            "comp_code":    code,
            "home_team":    r["home"],
            "away_team":    r["away"],
            "kickoff":      r["kickoff_utc"],
            "matchday":     matchday,
            "stage":        stage,
            "group":        None,
            "source":       "liveonsat",
            "needs_review": True,
            "expected_source": EXPECTED_SOURCE.get(code, "unknown"),
        })
    logger.info(f"[liveonsat] backfill: +{len(added)} fixtures added, "
                f"{len(mismatches)} probable name mismatches skipped")
    return added, mismatches
