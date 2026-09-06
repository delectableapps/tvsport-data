"""
rugby_merger.py — TVsport Rugby Union pipeline
==============================================
Builds output/rugby_fixtures.json in exactly the same shape as the
football fixtures.json, so the front-end renders both with one code path
(the Rugby / Football toggle just switches the JSON URL).

Pipeline:
    1. Fixtures  — TheSportsDB (eventsseason) for the 7 priority
                   competitions  [sources/fixtures_rugby_thesportsdb.py]
    2. Backfill  — liveonsat.com rugby page adds any in-scope fixture
                   TheSportsDB is missing (flagged needs_review)
    3. Rights    — rugby_rights_db.py gives territory → broadcaster
                   (confidence "medium")
    4. Confirm   — liveonsat per-match channel lists override the rights
                   row for that territory (confidence "high", source
                   "liveonsat")
    5. Always    — league OTT / FTA alternatives (TOP 14 Rugby TV,
                   TV5MONDE, EPCR TV, URC TV, RugbyPass TV)

Run:  cd scraper && python rugby_merger.py
Env:  LIVEONSAT_JSON_PATH / LIVEONSAT_JSON_URL  (same as merger.py — the
      liveonsat.json must have been scraped with "rugby" in --pages)
      RUGBY_TSDB_CACHE_DIR  (offline testing, see the fixture source)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from rugby_rights_db import (RUGBY_COMPETITIONS, ALWAYS_INCLUDE, UK_FTA,
                             get_rights_map, broadcaster_meta)
from channel_normaliser import normalise_channel_list

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("rugby")

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "rugby_fixtures.json")

# ─────────────────────────────────────────────────────────────────────────────
# liveonsat competition heading → comp_code  (first match wins)
# Headings look like "French TOP 14 - Round 1", "Nations Championship - Round 3"
# ─────────────────────────────────────────────────────────────────────────────
LOS_COMP_RULES = [
    (r"\b(u20|under[- ]?20|women|womens|wxv|female)\b",              None),     # skip age-grade/women's
    (r"top ?14",                                                     "TOP14"),
    (r"united rugby championship|\burc\b",                           "URC"),
    (r"nations championship",                                        "NATC"),
    (r"gallagher|english prem|premiership rugby|prem rugby|english premiership", "PREM"),
    (r"champions cup",                                               "ECC"),
    (r"challenge cup",                                               "ECHC"),
    (r"six nations",                                                 "SIXN"),
    (r"super rugby pacific",                                         "SUPER"),
    (r"autumn nations|nations series|rugby championship|international|test match|"
     r"british and irish lions|lions tour|quilter|summer tour",       "INTL"),
    (r"friendl",                                                     "FRIENDLY"),  # resolved per teams
]
NATIONS = {"england", "scotland", "wales", "ireland", "france", "italy", "new zealand",
           "australia", "south africa", "argentina", "japan", "fiji", "samoa", "tonga",
           "georgia", "usa", "united states", "canada", "uruguay", "chile", "spain",
           "portugal", "romania", "namibia", "hong kong", "china", "zimbabwe", "brazil",
           "netherlands", "germany", "belgium", "kenya", "korea", "south korea",
           "british and irish lions", "barbarians", "maori all blacks", "all blacks xv",
           "england a", "scotland a", "wales a", "ireland a", "emerging ireland", "france a"}
_LOS_COMP = [(re.compile(p, re.I), c) for p, c in LOS_COMP_RULES]


def los_comp_code(heading: str, home: str = "", away: str = "") -> str | None:
    for pat, code in _LOS_COMP:
        if pat.search(heading or ""):
            if code == "FRIENDLY":
                # club pre-season friendlies are out of scope; nation v nation is a Test
                return "INTL" if rugby_norm(home) in NATIONS and rugby_norm(away) in NATIONS else None
            return code
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Rugby-specific channel → (territory, broadcaster). Checked BEFORE the
# football rules in liveonsat_match.classify_channel, which remain the
# fall-back (Sky Sports, TNT, BBC, ITV, Canal+, SuperSport, ...).
# ─────────────────────────────────────────────────────────────────────────────
RUGBY_CHANNEL_RULES = [
    (r"premier sports.*ireland",              "Republic of Ireland", "Premier Sports Ireland"),
    (r"premier sports (rugby|\d|gb player|player)", "United Kingdom", "Premier Sports"),
    (r"\bs4c\b",                              "United Kingdom", "S4C"),
    (r"bbc (one|two) wales|bbc wales",        "United Kingdom", "BBC Wales"),
    (r"\bitv|\bstv\b|\butv\b",                "United Kingdom", "ITV"),
    (r"discovery\+|hbo max uk",               "United Kingdom", "Discovery+"),
    (r"\btg4\b",                              "Republic of Ireland", "TG4"),
    (r"virgin media",                         "Republic of Ireland", "Virgin Media"),
    (r"\brte\b|\brté\b",                      "Republic of Ireland", "RTÉ"),
    (r"canal\+.*czech",                       "Czechia", "Canal+"),
    (r"canal\+.*(poland|polska)",             "Poland", "Canal+"),
    (r"canal\+.*(afrique|africa)",            "Sub-Saharan Africa", "Canal+"),
    (r"canal\+.*(switzerland|suisse)",        "Switzerland", "Canal+"),
    (r"canal\+ ?(rugby|sport|foot|france|live|\d)|mycanal", "France", "Canal+"),
    (r"france (2|3|4)|france tv|france\.tv",  "France", "France Télévisions"),
    (r"\btf1\b",                              "France", "TF1"),
    (r"bein sports? ?\d? france|bein connect france", "France", "beIN Sports"),
    (r"bein sports? ?\d? mena|bein connect mena", "Middle East & N. Africa", "beIN Sports"),
    (r"bein sports (connect )?australia",     "Australia", "beIN Sports"),
    (r"sky sport (arena|uno|\d+) ?(italia|italy)|sky sport italia|sky go italy|now tv italy|now italia", "Italy", "Sky Italia"),
    (r"\btv8\b|rai ?(sport|play|2)",          "Italy", "RAI/TV8"),
    (r"dazn ?\d? italia",                     "Italy", "DAZN Italy"),
    (r"m\+ deportes|movistar",                "Spain", "Movistar"),
    (r"morethansports",                       "Germany", "MoreThanSportsTV"),
    (r"dazn deutsch|dazn germany",            "Germany", "DAZN"),
    (r"viaplay",                              "Nordics", "Viaplay"),
    (r"sport tv\d? portugal",                 "Portugal", "Sport TV"),
    (r"\bpeacock\b|nbc|cnbc",                 "United States", "NBC Sports / Peacock"),
    (r"flo ?rugby|flosports",                 "United States", "FloRugby"),
    (r"rugbypass",                            "Worldwide", "RugbyPass TV"),
    (r"sportsnet world",                      "Canada", "Sportsnet World"),
    (r"\btsn\b",                              "Canada", "TSN"),
    (r"espn.*(argentina|sur|latin|chile|colombia|brasil|brazil|mexico)|star\+", "Latin America", "ESPN Sur"),
    (r"stan sport",                           "Australia", "Stan Sport"),
    (r"channel 9|9now|nine network|9gem",     "Australia", "Channel 9"),
    (r"sky sport (\d|select|now|pop).*nz|sky sport nz", "New Zealand", "Sky Sport NZ"),
    (r"nzr\+",                                "New Zealand", "NZR+"),
    (r"supersport",                           "South Africa", "SuperSport"),
    (r"\bfbc\b",                              "Fiji", "FBC"),
    (r"sky pacific",                          "Fiji", "Sky Pacific"),
    (r"digicel",                              "Pacific Islands", "Digicel"),
    (r"wowow",                                "Japan", "WOWOW"),
    (r"dazn japan",                           "Japan", "DAZN Japan"),
    (r"setanta",                              "Asia / Oceania (Setanta)", "Setanta Sports"),
    (r"\btod\b|starzplay",                    "Middle East & N. Africa", "TOD TV (Starzplay)"),
    (r"sport ?5 israel|sport 5",              "Israel", "Sport 5"),
    (r"imedi",                                "Georgia", "Imedi TV"),
    (r"tv5 ?monde",                           "Worldwide", "TV5MONDE"),
    (r"top ?14 rugby tv|top14rugbytv",        "Worldwide (170+ territories)", "TOP 14 Rugby TV"),
    (r"epcr ?tv|epcrugby\.tv",                "Worldwide (outside rights-holder territories)", "EPCR TV"),
    (r"urc ?tv|urc\.tv",                      "Worldwide (outside rights-holder territories)", "URC TV"),
    (r"prtv",                                 "Rest of World", "PRTV Live"),
    (r"sport 24 (at sea|in flight)",          "International", "Sport 24"),
]
_RUGBY_CH = [(re.compile(p, re.I), t, b) for p, t, b in RUGBY_CHANNEL_RULES]


# ─────────────────────────────────────────────────────────────────────────────
# Rugby team-name normalisation. liveonsat and TheSportsDB spell clubs
# differently ("Benetton Rugby" / "Benetton", "Clermont Auvergne" /
# "ASM Clermont Auvergne", "Cardiff Rugby" / "Cardiff"). Both sides are
# passed through rugby_norm() before matching or de-duplicating.
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

RUGBY_TEAM_ALIASES = {
    # French
    "stade toulousain": "toulouse", "stade rochelais": "la rochelle",
    "stade francais paris": "stade francais", "union bordeaux begles": "bordeaux begles",
    "bordeaux": "bordeaux begles", "ubb": "bordeaux begles",
    "asm clermont auvergne": "clermont", "clermont auvergne": "clermont", "asm clermont": "clermont",
    "montpellier herault": "montpellier", "rc toulonnais": "toulon", "rc toulon": "toulon",
    "aviron bayonnais": "bayonne", "section paloise": "pau", "castres olympique": "castres",
    "usa perpignan": "perpignan", "lyon ou": "lyon", "racing metro 92": "racing 92",
    "rc vannes": "vannes",
    # English
    "bath rugby": "bath", "leicester": "leicester tigers", "northampton": "northampton saints",
    "newcastle": "newcastle red bulls", "newcastle falcons": "newcastle red bulls",
    "sale": "sale sharks", "bristol": "bristol bears", "exeter": "exeter chiefs",
    "gloucester rugby": "gloucester", "quins": "harlequins", "saints": "northampton saints",
    # URC
    "benetton treviso": "benetton", "zebre parma": "zebre", "dhl stormers": "stormers",
    "vodacom bulls": "bulls", "emirates lions": "lions", "hollywoodbets sharks": "sharks",
    "the sharks": "sharks", "glasgow": "glasgow warriors", "cardiff blues": "cardiff",
    "scarlets rugby": "scarlets", "ospreys rugby": "ospreys", "dragons rfc": "dragons",
    # Internationals
    "all blacks": "new zealand", "springboks": "south africa", "wallabies": "australia",
    "pumas": "argentina", "les bleus": "france",
}


def rugby_norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\brugby\b", " ", s)           # "Cardiff Rugby", "Ulster Rugby", "England Rugby"
    s = re.sub(r"^(the|as|rc|us|sc|cs|asm)\s+", "", s)
    s = re.sub(r"\s+(rfc|fc|rc)$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return RUGBY_TEAM_ALIASES.get(s, s)


# liveonsat spellings (normalised) → the display name we publish
LOS_DISPLAY_FIXES = {
    "clermont": "Clermont", "bordeaux begles": "Bordeaux-Bègles", "stade francais": "Stade Français",
    "benetton": "Benetton", "cardiff": "Cardiff", "sharks": "Sharks", "racing 92": "Racing 92",
    "glasgow warriors": "Glasgow Warriors", "la rochelle": "La Rochelle", "toulouse": "Toulouse",
}


class RugbyLosIndex:
    """liveonsat rugby rows keyed by normalised (home, away)."""
    TOL = 25 * 60   # seconds

    def __init__(self, rows: list):
        self.rows = rows
        self._by = {}
        for r in rows:
            self._by.setdefault((rugby_norm(r.get("home")), rugby_norm(r.get("away"))), []).append(r)

    def find(self, home, away, kickoff_iso):
        cands = self._by.get((rugby_norm(home), rugby_norm(away)))
        if not cands:
            return None
        try:
            ko = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
        except Exception:
            return cands[0]
        best, bd = None, None
        for r in cands:
            try:
                rk = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
            except Exception:
                continue
            d = abs((rk - ko).total_seconds())
            if d <= self.TOL and (bd is None or d < bd):
                best, bd = r, d
        return best


def tidy_channel(name: str) -> str:
    """Display form of a liveonsat channel name."""
    n = re.sub(r"\[(s/cast|app|online|via app)\]", "", name, flags=re.I)
    n = n.replace(" HD", "").replace("(#)", "")
    return re.sub(r"\s{2,}", " ", n).strip()


def classify_rugby_channel(name: str):
    for pat, terr, bcast in _RUGBY_CH:
        if pat.search(name):
            return terr, bcast
    try:
        from liveonsat_match import classify_channel
        return classify_channel(name)
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — fixtures
# ─────────────────────────────────────────────────────────────────────────────
def fetch_fixtures() -> list:
    try:
        from sources.fixtures_rugby_thesportsdb import scrape_fixtures
        fx = scrape_fixtures()
        logger.info(f"[rugby] thesportsdb: {len(fx)} fixtures")
        return fx
    except Exception as e:
        logger.error(f"[rugby] thesportsdb failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — liveonsat rugby rows (index + backfill)
# ─────────────────────────────────────────────────────────────────────────────
def load_liveonsat_rugby():
    """Return a LiveOnSatIndex over rugby rows only, or None."""
    try:
        from liveonsat_match import LiveOnSatIndex
    except Exception as e:
        logger.warning(f"[rugby] liveonsat_match unavailable: {e}")
        return None

    def _fix_legacy_offset(data: dict, rows: list) -> list:
        """liveonsat.json written by a fetcher older than 6 Sep 2026: the rugby
        page header is unparsable, so those rows were converted with the
        GMT-4 fallback while the football pages used the real (UK) offset.
        Re-derive the wall-clock time and reinterpret it in the UK page's zone."""
        pages = data.get("pages", {})
        rp, up = pages.get("rugby", {}), pages.get("uk", {})
        if not rows or rp.get("offset_found") is not None:      # new fetcher → already right
            return rows
        uk_off = up.get("page_offset")
        if rp.get("page_offset") != "-04:00" or not uk_off or uk_off == "-04:00":
            return rows
        from zoneinfo import ZoneInfo
        from datetime import timedelta
        zone = ZoneInfo("Europe/London") if uk_off in ("+00:00", "+01:00") else None
        h, m = int(uk_off[1:3]), int(uk_off[4:6])
        fixed = timezone(timedelta(hours=h, minutes=m) * (-1 if uk_off[0] == "-" else 1))
        for r in rows:
            try:
                utc = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
                wall = (utc - timedelta(hours=4)).replace(tzinfo=None)      # what the page showed
                real = wall.replace(tzinfo=zone or fixed).astimezone(timezone.utc)
                r["kickoff_utc"] = real.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        logger.warning(f"[rugby] liveonsat rugby rows re-timed from GMT-4 fallback to "
                       f"UK page offset {uk_off} ({len(rows)} rows) — re-run run_liveonsat.bat "
                       f"with the updated liveonsat_fetcher.py to remove this step")
        return rows

    def _rows_from_doc(data: dict, origin: str):
        rows = [r for r in data.get("fixtures", []) if r.get("source_page") == "rugby"]
        rows = _fix_legacy_offset(data, rows)
        fetched = data.get("fetched_at", "")
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(fetched.replace("Z", "+00:00"))).total_seconds() / 86400
        except Exception:
            age = None
        if age is not None and age > LiveOnSatIndex.MAX_AGE_DAYS:
            logger.warning(f"[rugby] {origin} is {age:.1f} days old — ignoring")
            return None
        if not rows:
            logger.warning(f"[rugby] {origin} has no rugby rows — was the "
                           f"rugby page included in run_liveonsat.bat --pages?")
            return None
        logger.info(f"[rugby] liveonsat: {len(rows)} rugby rows from {origin}")
        return rows

    rows = None
    path = os.environ.get("LIVEONSAT_JSON_PATH", "").strip()
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                rows = _rows_from_doc(json.load(fh), f"file {path}")
        except Exception as e:
            logger.warning(f"[rugby] could not read {path}: {e}")
    if rows is None:
        url = os.environ.get("LIVEONSAT_JSON_URL", "").strip()
        if url:
            try:
                import requests
                if "dropbox.com" in url:
                    url = url.replace("?dl=0", "?dl=1").replace("&dl=0", "&dl=1")
                    if "dl=1" not in url and "raw=1" not in url:
                        url += ("&" if "?" in url else "?") + "dl=1"
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                rows = _rows_from_doc(r.json(), "LIVEONSAT_JSON_URL")
            except Exception as e:
                logger.warning(f"[rugby] could not load LIVEONSAT_JSON_URL: {e}")
    if rows is None:
        # Direct fetch (works from residential IPs, not GitHub Actions)
        try:
            import requests
            from liveonsat_fetcher import fetch_page, parse_page
            html = fetch_page("rugby", requests.Session())
            rows, meta = parse_page(html, "rugby")
            logger.info(f"[rugby] liveonsat direct: {len(rows)} rows "
                        f"(page offset {meta.get('page_offset')})")
        except Exception as e:
            logger.warning(f"[rugby] liveonsat direct fetch failed: {e}")
            return None
    if not rows:
        return None
    return RugbyLosIndex(rows)


def backfill_from_liveonsat(fixtures: list, index) -> list:
    """Add in-scope liveonsat rugby matches TheSportsDB doesn't have."""
    if index is None:
        return fixtures
    have = {(rugby_norm(f["home_team"]), rugby_norm(f["away_team"]), f["kickoff"][:10])
            for f in fixtures}
    # One display name per club across both sources, so favourites / search
    # match: prefer the spelling TheSportsDB rows already use, else tidy the
    # liveonsat spelling ("Benetton Rugby" -> "Benetton").
    from sources.fixtures_rugby_thesportsdb import clean_team
    display = {}
    for f in fixtures:
        display.setdefault(rugby_norm(f["home_team"]), f["home_team"])
        display.setdefault(rugby_norm(f["away_team"]), f["away_team"])
    def disp(raw):
        n = rugby_norm(raw)
        if n in display:
            return display[n]
        name = LOS_DISPLAY_FIXES.get(n) or clean_team(raw)
        display[n] = name
        return name
    added = []
    for r in index.rows:
        code = los_comp_code(r.get("competition", ""), r.get("home", ""), r.get("away", ""))
        if not code:
            continue
        if r.get("status") == "POSTPONED":
            continue
        ko = r.get("kickoff_utc", "")
        key = (rugby_norm(r.get("home", "")), rugby_norm(r.get("away", "")), ko[:10])
        if key in have:
            continue
        # Same pairing within ±1 day (late-night UTC kick-offs can sit on the
        # neighbouring date) → same match, don't duplicate.
        try:
            kd = datetime.fromisoformat(ko[:10])
            if any(k[0] == key[0] and k[1] == key[1]
                   and abs((datetime.fromisoformat(k[2]) - kd).days) <= 1 for k in have):
                continue
        except Exception:
            pass
        comp = RUGBY_COMPETITIONS[code]
        m = re.search(r"round\s*(\d+)", r.get("round", "") or "", re.I)
        added.append({
            "id":          f"{code.lower()}_{_abbr(disp(r['home']))}_{_abbr(disp(r['away']))}_{ko[:10]}",
            "sport":       "rugby_union",
            "competition": comp["display"],
            "comp_code":   code,
            "home_team":   disp(r["home"]),
            "away_team":   disp(r["away"]),
            "kickoff":     ko,
            "matchday":    int(m.group(1)) if m else None,
            "stage":       "REGULAR_SEASON",
            "group":       None,
            "venue":       None,
            "status":      r.get("status") or "",
            "source":      "liveonsat",
            "needs_review": True,
        })
        have.add(key)
    if added:
        by = Counter(a["competition"] for a in added)
        logger.info("[rugby] liveonsat backfill: " + ", ".join(f"{c} +{n}" for c, n in by.items()))
    return fixtures + added


def liveonsat_territories(index, fixture: dict) -> dict:
    """{territory: {broadcaster, channels}} for one fixture from liveonsat."""
    if index is None:
        return {}
    row = index.find(fixture["home_team"], fixture["away_team"], fixture["kickoff"])
    if not row:
        return {}
    out = {}
    for ch in row.get("channels", []):
        terr, bcast = classify_rugby_channel(ch["name"])
        if not terr:
            continue
        e = out.setdefault((terr, bcast), {"broadcaster": bcast, "channels": [], "pay": ch.get("pay", False)})
        clean = tidy_channel(ch["name"])
        if clean and clean not in e["channels"]:
            e["channels"].append(clean)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3–5 — broadcaster list per fixture
# ─────────────────────────────────────────────────────────────────────────────
def _region_for(territory: str, rights_map: dict) -> str:
    if territory in rights_map:
        return rights_map[territory]["region"]
    return {"United Kingdom": "UK", "Republic of Ireland": "Europe",
            "France": "Europe", "Italy": "Europe", "Spain": "Europe",
            "Germany": "Europe", "Nordics": "Europe", "Portugal": "Europe",
            "Czechia": "Europe", "Poland": "Europe", "Georgia": "Europe",
            "United States": "Americas", "Canada": "Americas",
            "Latin America": "Americas", "Australia": "Asia-Pacific",
            "New Zealand": "Asia-Pacific", "Fiji": "Asia-Pacific",
            "Pacific Islands": "Asia-Pacific", "Japan": "Asia",
            "South Africa": "Sub-Saharan Africa",
            "Sub-Saharan Africa": "Sub-Saharan Africa",
            "Middle East & N. Africa": "Middle East & N. Africa",
            "Israel": "Middle East & N. Africa"}.get(territory, "International")


REGION_ORDER = {"UK": 0, "Europe": 1, "Americas": 2, "Asia-Pacific": 3, "Asia": 4,
                "Middle East & N. Africa": 5, "Sub-Saharan Africa": 6, "International": 7}


def _abbr(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())[:3] or "XXX"


# Six Nations UK split (2026–2029): BBC = Scotland & Wales home games,
# ITV = England, Ireland, France, Italy home games. S4C simulcasts Wales
# games in Welsh; STV carries ITV's coverage in Scotland.
SIXN_BBC_HOSTS = {"scotland", "wales"}
UK_RIGHTS_NOTES = {
    ("PREM", "ITV"): "7 selected live matches per season incl. the Final (also on TNT) — confirmed per match nearer the time",
    ("SIXN", "S4C"): "Welsh-language coverage of Wales matches",
    ("SIXN", "STV"): "ITV coverage in Scotland",
    ("URC", "S4C"):  "20 Welsh-region matches free-to-air per season",
    ("URC", "BBC Wales"): "Selected Welsh-region matches",
    ("ECC", "S4C"):  "Selected Welsh-region matches free-to-air",
    ("ECHC", "S4C"): "Selected Welsh-region matches free-to-air",
    ("TOP14", "Premier Sports"): "4 matches per round + finals — not every match is shown in the UK",
    ("INTL", "Sky Sports"): "Rugby Championship and southern-hemisphere home Tests",
    ("INTL", "TNT Sports"): "Selected home-nation Tests in non-Nations-Championship years",
    ("INTL", "ITV"): "Nations Series Tests in 2026 and 2028",
}


def _uk_rights_for_match(code: str, home: str, names: list) -> list:
    """Narrow the UK rights-holder list using per-match rules where the
    split is known (Six Nations BBC/ITV by home nation)."""
    if code == "SIXN":
        h = (home or "").lower()
        if any(n in h for n in SIXN_BBC_HOSTS):
            keep = {"BBC", "S4C"} if "wales" in h else {"BBC"}
        else:
            keep = {"ITV", "STV"}
        return [n for n in names if n in keep] or names
    return names


def build_broadcasters(fixture: dict, los_terrs: dict) -> list:
    code = fixture["comp_code"]
    rights_map = get_rights_map(code)
    out = []
    covered = set()

    # Tier 1 — liveonsat confirmed channels (per match, per broadcaster)
    for (terr, _bcast), e in los_terrs.items():
        meta = broadcaster_meta(e["broadcaster"])
        btype = "free_tv" if (terr == "United Kingdom" and e["broadcaster"] in UK_FTA) else meta["type"]
        out.append({
            "territory":   terr,
            "region":      _region_for(terr, rights_map),
            "broadcaster": e["broadcaster"],
            "channels":    normalise_channel_list(e["channels"]) or e["channels"],
            "type":        btype,
            "coverage":    "live",
            "confidence":  "high",
            "source":      "liveonsat",
        })
        covered.add(terr)

    # Tier 2 — static rights for territories liveonsat didn't confirm
    home = fixture.get("home_team", "")
    for terr, row in rights_map.items():
        if terr in covered:
            continue
        names = [b.strip() for b in row["broadcaster"].split(";") if b.strip()]
        if terr == "United Kingdom":
            names = _uk_rights_for_match(code, home, names)
        for name in names:
            meta = broadcaster_meta(name)
            note = UK_RIGHTS_NOTES.get((code, name), "") if terr == "United Kingdom" else ""
            out.append({
                "territory":   terr,
                "region":      row["region"],
                "broadcaster": name,
                "channels":    list(meta["channels"]),
                "type":        meta["type"],
                "coverage":    "live",
                "confidence":  "medium",
                "source":      "rights",
                **({"note": note} if note else {}),
            })

    # Tier 3 — always-include OTT / FTA alternatives
    present = {(b["territory"], b["broadcaster"]) for b in out}
    for extra in ALWAYS_INCLUDE.get(code, []):
        if (extra["territory"], extra["broadcaster"]) in present:
            continue
        meta = broadcaster_meta(extra["broadcaster"])
        out.append({
            "territory":   extra["territory"],
            "region":      extra["region"],
            "broadcaster": extra["broadcaster"],
            "channels":    list(meta["channels"]),
            "type":        extra["type"],
            "coverage":    "live",
            "confidence":  "medium",
            "source":      "rights",
            "note":        extra.get("note", ""),
        })

    # UK, Ireland, then Europe → Americas → Asia-Pacific → Asia → MENA →
    # Africa → International; confirmed (high) entries before rights rows.
    t_order = {"United Kingdom": 0, "Republic of Ireland": 1}
    out.sort(key=lambda b: (t_order.get(b["territory"], 2),
                            REGION_ORDER.get(b["region"], 9), b["territory"],
                            0 if b["confidence"] == "high" else 1))
    return out


def assemble(fixtures: list, index) -> list:
    out = []
    for f in fixtures:
        los = liveonsat_territories(index, f)
        bcs = build_broadcasters(f, los)
        # Free-to-air badge only when we're sure: liveonsat-confirmed FTA
        # channel, or a competition that is wholly FTA in the UK.
        uk_fta = any(b["territory"] == "United Kingdom" and b["type"] == "free_tv"
                     and (b["confidence"] == "high" or f["comp_code"] in ("SIXN", "NATC"))
                     for b in bcs)
        rec = {
            "id":           f["id"],
            "sport":        "rugby_union",
            "competition":  f["competition"],
            "comp_code":    f["comp_code"],
            "home_team":    f["home_team"],
            "away_team":    f["away_team"],
            "kickoff":      f["kickoff"],
            "matchday":     f.get("matchday"),
            "stage":        f.get("stage", ""),
            "group":        f.get("group"),
            "venue":        f.get("venue"),
            "status":       f.get("status", ""),
            "is_blackout":  False,
            "uk_free_to_air": uk_fta,
            "liveonsat_confirmed": bool(los),
            "broadcasters": bcs,
            "broadcaster_count": len(bcs),
        }
        if f.get("source") == "liveonsat":
            rec.update({"source": "liveonsat", "needs_review": True})
        out.append(rec)
    return out


def main():
    logger.info("=" * 60)
    logger.info("TVsport RUGBY pipeline starting")
    logger.info("=" * 60)

    fixtures = fetch_fixtures()
    index = load_liveonsat_rugby()
    fixtures = backfill_from_liveonsat(fixtures, index)

    if not fixtures:
        logger.error("[rugby] No fixtures from any source — aborting (previous rugby_fixtures.json kept)")
        sys.exit(1)

    fixtures.sort(key=lambda f: f["kickoff"])
    output = assemble(fixtures, index)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "sport": "rugby_union",
            "generated_at": now_iso,
            "lastUpdated": now_iso,
            "fixture_count": len(output),
            "competitions": [{"code": c, "name": v["display"]} for c, v in RUGBY_COMPETITIONS.items()],
            "fixtures": output,
        }, fh, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Written {len(output)} rugby fixtures to {OUTPUT_PATH}")
    for comp, n in sorted(Counter(f["competition"] for f in output).items()):
        conf = sum(1 for f in output if f["competition"] == comp and f["liveonsat_confirmed"])
        logger.info(f"  {comp}: {n} fixtures ({conf} with liveonsat-confirmed channels)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
