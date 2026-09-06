"""
merger.py — TVsport scraper pipeline
Run this to generate output/fixtures.json

Usage:
    cd scraper && python merger.py

Sources (in priority order):
    1. football-data.org API     — primary fixtures (EPL, UCL, EFL, European leagues)
    2. efl.com scraper           — fallback/validator for EFL
    3. Sportmonks / spfl.co.uk   — Scottish leagues
    4. thesportsdb               — lower English/Scottish + cups
    5. openfootball              — broad league baseline (EFL, Scottish, top-5 Euro)
    6. cup_fetcher (BBC+Wiki)    — FA/EFL/Scottish/Scottish League cups, merged
    7. livefootballontv.com      — UK channel assignments per fixture
    8. iptv-org/epg (XMLTV)      — international channel assignments
    9. rights_db.py              — broadcast rights layer (who has rights per territory)
"""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:                                     # pragma: no cover
    ZoneInfo = None

sys.path.insert(0, os.path.dirname(__file__))

from rights_db import (
    EPL_RIGHTS, UCL_RIGHTS, EFL_RIGHTS, SCOTTISH_RIGHTS,
    EUROPEAN_LEAGUES_RIGHTS, BROADCASTER_META,
    get_all_rights_for_competition, is_epl_blackout,
    COMP_CODE_TO_RIGHTS_KEY,
)
# Per-competition UK overrides and territory exclusions. Imported defensively
# so this file remains compatible with older rights_db.py during the upgrade
# window — both default to empty if missing.
try:
    from rights_db import EFL_UK_OVERRIDES                # type: ignore
except ImportError:                                       # pragma: no cover
    EFL_UK_OVERRIDES = {}
try:
    from rights_db import EFL_TERRITORY_EXCLUSIONS        # type: ignore
except ImportError:                                       # pragma: no cover
    EFL_TERRITORY_EXCLUSIONS = {}
# UCL per-fixture overrides (UK Tue/Wed Amazon-vs-TNT rotation, IRE
# RTÉ/Virgin/Premier rotation, FRA M6 final-only) and the highlights-only
# broadcaster set (BBC, ZDF for UCL).
try:
    from rights_db import UCL_MATCH_OVERRIDES, get_ucl_match_override   # type: ignore
except ImportError:                                       # pragma: no cover
    UCL_MATCH_OVERRIDES = {}
    def get_ucl_match_override(home, away, kickoff_iso):
        return None
try:
    from rights_db import UCL_HIGHLIGHTS_ONLY              # type: ignore
except ImportError:                                       # pragma: no cover
    UCL_HIGHLIGHTS_ONLY = set()

from channel_normaliser import normalise_channel_list

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "fixtures.json")


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTER FOR openfootball + cup_fetcher
# ─────────────────────────────────────────────────────────────────────────────

OPENFOOTBALL_CODE_MAP = {
    "EPL":   "PL",
    "CHAMP": "ELC",
    "L1":    "EL1",
    "L2":    "EL2",
    "NAT":   "NAT",
    "SPFL":  "SP1",
    "BUND":  "BL1",
    "LL":    "PD",
    "SA":    "SA",
    "L1F":   "FL1",
    "ERE":   "DED",
    "PPL":   "PPL",
}

CUP_FETCHER_CODE_MAP = {
    "FAC":   "FACUP",
    "EFLC":  "EFLCUP",
    "SFAC":  "SCUP",
    "SLFC":  "SLCUP",
}

CANONICAL_COMP_NAMES = {
    "PL":     "Premier League",
    "ELC":    "Championship",
    "EL1":    "League One",
    "EL2":    "League Two",
    "NAT":    "National League",
    "SP1":    "Scottish Premiership",
    "SCH":    "Scottish Championship",
    "SC1":    "Scottish League One",
    "BL1":    "Bundesliga",
    "PD":     "La Liga",
    "SA":     "Serie A",
    "FL1":    "Ligue 1",
    "DED":    "Eredivisie",
    "PPL":    "Primeira Liga",
    "CL":     "UEFA Champions League",
    "EL":     "UEFA Europa League",
    "ECL":    "UEFA Conference League",
    "FACUP":  "FA Cup",
    "FAC":    "FA Cup",
    "EFLCUP": "EFL Cup",
    "SCUP":   "Scottish Cup",
    "SLCUP":  "Scottish League Cup",
}

COMPETITION_TIMEZONE = {
    "PL":     "Europe/London",
    "ELC":    "Europe/London",
    "EL1":    "Europe/London",
    "EL2":    "Europe/London",
    "NAT":    "Europe/London",
    "FACUP":  "Europe/London",
    "FAC":    "Europe/London",
    "EFLCUP": "Europe/London",
    "SP1":    "Europe/London",
    "SCH":    "Europe/London",
    "SC1":    "Europe/London",
    "SCUP":   "Europe/London",
    "SLCUP":  "Europe/London",
    "BL1":    "Europe/Berlin",
    "PD":     "Europe/Madrid",
    "SA":     "Europe/Rome",
    "FL1":    "Europe/Paris",
    "DED":    "Europe/Amsterdam",
    "PPL":    "Europe/Lisbon",
    "CL":     "Europe/Zurich",
    "EL":     "Europe/Zurich",
    "ECL":    "Europe/Zurich",
}

DEFAULT_TIMEZONE = "Europe/London"


def _local_to_utc_iso(date: str, time_local: str | None,
                      pipeline_code: str) -> str:
    if not time_local:
        return f"{date}T12:00:00Z"

    if ZoneInfo is None:
        return f"{date}T{time_local}:00Z"

    tz_name = COMPETITION_TIMEZONE.get(pipeline_code, DEFAULT_TIMEZONE)
    try:
        local_dt = datetime.strptime(
            f"{date}T{time_local}:00", "%Y-%m-%dT%H:%M:%S"
        ).replace(tzinfo=ZoneInfo(tz_name))
        utc_dt = local_dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, KeyError) as e:
        logger.warning(
            "[merger] timezone conversion failed for %s %s %s (%s) — "
            "falling back to naive Z tag",
            pipeline_code, date, time_local, e,
        )
        return f"{date}T{time_local}:00Z"


def _synthesise_fixture_id(comp_code: str, home: str, away: str, date: str) -> str:
    raw = f"{comp_code}|{home}|{away}|{date}".lower()
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"of-{digest}"


def _match_to_fixture(match, code_map: dict) -> dict | None:
    pipeline_code = code_map.get(match.competition_code)
    if not pipeline_code:
        return None

    if match.time_local:
        time_local = match.time_local
    elif match.kickoff_utc and "T" in match.kickoff_utc:
        time_local = match.kickoff_utc.split("T", 1)[1][:5]
    else:
        time_local = None

    kickoff = _local_to_utc_iso(match.date, time_local, pipeline_code)

    competition_name = CANONICAL_COMP_NAMES.get(
        pipeline_code, match.competition_name)

    return {
        "id":         _synthesise_fixture_id(
                          pipeline_code, match.home, match.away, match.date),
        "competition": competition_name,
        "comp_code":   pipeline_code,
        "home_team":   match.home,
        "away_team":   match.away,
        "kickoff":     kickoff,
        "matchday":    None,
        "stage":       match.round_label or "",
        "group":       "",
    }


def _normalise_existing_fixture(fixture: dict) -> dict:
    code = fixture.get("comp_code", "")
    canonical = CANONICAL_COMP_NAMES.get(code)
    if canonical:
        fixture["competition"] = canonical
    return fixture


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — FETCH FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fixtures() -> list:
    all_fixtures = []
    seen_ids = set()

    try:
        from sources.fixtures_footballdata import scrape_fixtures as fd_scrape
        fd_fixtures = fd_scrape()
        logger.info(f"[pipeline] football-data.org: {len(fd_fixtures)} fixtures")
        for f in fd_fixtures:
            _normalise_existing_fixture(f)
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
    except Exception as e:
        logger.error(f"[pipeline] football-data.org failed: {e}")

    try:
        from sources.fixtures_efl import scrape_fixtures as efl_scrape
        efl_fixtures = efl_scrape()
        added = 0
        for f in efl_fixtures:
            _normalise_existing_fixture(f)
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
                added += 1
        logger.info(f"[pipeline] efl.com: {added} new fixtures added")
    except Exception as e:
        logger.warning(f"[pipeline] efl.com scraper failed: {e}")

    try:
        from sources.fixtures_sportmonks import scrape_fixtures as sportmonks_scrape
        sportmonks_fixtures = sportmonks_scrape()
        added = 0
        for f in sportmonks_fixtures:
            _normalise_existing_fixture(f)
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
                added += 1
        logger.info(f"[pipeline] sportmonks: {added} Scottish fixtures added")
    except Exception as e:
        logger.warning(f"[pipeline] Sportmonks failed: {e}")
        try:
            from sources.fixtures_spfl import scrape_fixtures as spfl_scrape
            spfl_fixtures = spfl_scrape()
            added = 0
            for f in spfl_fixtures:
                _normalise_existing_fixture(f)
                if f["id"] not in seen_ids:
                    seen_ids.add(f["id"])
                    all_fixtures.append(f)
                    added += 1
            logger.info(f"[pipeline] spfl.co.uk fallback: {added} fixtures added")
        except Exception as e2:
            logger.warning(f"[pipeline] spfl.co.uk fallback also failed: {e2}")

    try:
        from sources.fixtures_thesportsdb import scrape_fixtures as tsdb_scrape
        tsdb_fixtures = tsdb_scrape()
        added = 0
        for f in tsdb_fixtures:
            _normalise_existing_fixture(f)
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
                added += 1
        logger.info(f"[pipeline] thesportsdb: {added} new fixtures added")
    except Exception as e:
        logger.warning(f"[pipeline] thesportsdb failed: {e}")

    try:
        from sources.openfootball_fetcher import fetch_all as of_fetch
        of_matches = of_fetch()
        of_added = 0
        of_skipped_no_code = 0
        for m in of_matches:
            fx = _match_to_fixture(m, OPENFOOTBALL_CODE_MAP)
            if fx is None:
                of_skipped_no_code += 1
                continue
            if fx["id"] not in seen_ids:
                seen_ids.add(fx["id"])
                all_fixtures.append(fx)
                of_added += 1
        logger.info(
            f"[pipeline] openfootball: {of_added} new fixtures added "
            f"(received {len(of_matches)}, skipped {of_skipped_no_code} with no code mapping)"
        )
    except Exception as e:
        logger.warning(f"[pipeline] openfootball failed: {e}")

    try:
        from sources.cups.cup_fetcher import fetch_all_cups as cup_fetch
        cup_matches = cup_fetch()
        cup_added = 0
        for m in cup_matches:
            fx = _match_to_fixture(m, CUP_FETCHER_CODE_MAP)
            if fx is None:
                continue
            if fx["id"] not in seen_ids:
                seen_ids.add(fx["id"])
                all_fixtures.append(fx)
                cup_added += 1
        logger.info(
            f"[pipeline] cup_fetcher (BBC+Wiki): {cup_added} new cup fixtures added "
            f"(received {len(cup_matches)})"
        )
    except Exception as e:
        logger.warning(f"[pipeline] cup_fetcher failed: {e}")

    logger.info(f"[pipeline] Total fixtures before dedup: {len(all_fixtures)}")
    return all_fixtures


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────

def dedup_fixtures(fixtures: list) -> list:
    seen = set()
    out = []
    for f in fixtures:
        ko = f.get("kickoff", "")[:10]
        key = (
            f.get("competition", "").lower(),
            f.get("home_team", "").lower(),
            f.get("away_team", "").lower(),
            ko,
        )
        if key not in seen:
            seen.add(key)
            out.append(f)
    logger.info(f"[pipeline] After dedup: {len(out)} fixtures")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — UK CHANNEL LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

def enrich_uk_channels(fixtures: list) -> dict:
    result = {}
    try:
        from sources.uk_skysports import get_uk_channels as sky_channels
        sky_data = sky_channels(fixtures)
        for fixture_id, data in sky_data.items():
            result[fixture_id] = {"channels": [data["channel"]], "kickoff_display": data.get("kickoff_display", "")}
        logger.info(f"[pipeline] skysports.com: {len(sky_data)} fixtures matched")
    except Exception as e:
        logger.warning(f"[pipeline] skysports.com failed: {e}")
    try:
        from sources.uk_channels import get_uk_channels
        lf_data = get_uk_channels(fixtures)
        added = sum(1 for fid in lf_data if fid not in result)
        result.update({fid: d for fid, d in lf_data.items() if fid not in result})
        logger.info(f"[pipeline] livefootballontv: {added} additional fixtures matched")
    except Exception as e:
        logger.warning(f"[pipeline] livefootballontv failed: {e}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — EPG CHANNEL LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

def enrich_epg(fixtures: list) -> dict:
    try:
        from epg_fetcher import EPGFetcher
        fetcher = EPGFetcher()
        fetcher.fetch_all()

        loaded = fetcher.get_loaded_feeds()
        if not loaded:
            logger.warning("[pipeline] EPG: no feeds loaded — falling back to rights_db only")
            return {}

        stats = fetcher.get_stats()
        total_progs = sum(s["programmes"] for s in stats.values())
        logger.info(f"[pipeline] EPG: {len(loaded)} feeds loaded, {total_progs:,} football programmes indexed")

        epg_data = fetcher.lookup_all_fixtures(fixtures)
        logger.info(f"[pipeline] EPG: matched {len(epg_data)}/{len(fixtures)} fixtures")
        return epg_data

    except Exception as e:
        logger.warning(f"[pipeline] EPG enrichment failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4b — LIVEONSAT CONFIRMATION (per-match, per-territory)
# Resolves things static rights cannot: e.g. which single 3pm-BST Saturday
# EPL match Premier Sports Ireland actually selected.
# ─────────────────────────────────────────────────────────────────────────────

def enrich_liveonsat(fixtures: list) -> dict:
    try:
        from liveonsat_match import LiveOnSatIndex
        index = LiveOnSatIndex.build()
        data = index.lookup_all_fixtures(fixtures)
        logger.info(f"[pipeline] liveonsat: matched {len(data)}/{len(fixtures)} fixtures")
        return data
    except Exception as e:
        logger.warning(f"[pipeline] liveonsat enrichment failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — BUILD BROADCASTER LIST PER FIXTURE
# ─────────────────────────────────────────────────────────────────────────────

def build_broadcaster_list(fixture: dict, uk_channels: dict, epg_data: dict,
                           los_data: dict | None = None) -> list:
    comp_code    = fixture.get("comp_code", "")
    fixture_id   = fixture.get("id", "")
    los_terrs    = (los_data or {}).get(fixture.get("id", "")) or {}
    kickoff      = fixture.get("kickoff", "")
    is_blackout  = (comp_code == "PL" and is_epl_blackout(kickoff))
    rights_key   = COMP_CODE_TO_RIGHTS_KEY.get(comp_code, "")

    def _resolve_coverage(default: str, broadcaster: str) -> str:
        """For UCL/UEL/UECL, force highlights-only broadcasters to highlights."""
        if comp_code in ("CL", "EL", "ECL") and broadcaster in UCL_HIGHLIGHTS_ONLY:
            return "highlights"
        return default

    broadcasters = []

    # Get the appropriate rights dictionary for this competition
    if comp_code == "PL":
        rights_map = dict(EPL_RIGHTS)
        rights_map["United Kingdom"] = {"broadcaster": "Sky Sports; TNT Sports", "region": "UK"}
    elif comp_code in ("CL", "EL", "ECL"):
        rights_map = dict(UCL_RIGHTS)
        # ── Per-fixture overrides for UCL knockout rotations ──
        # See rights_db.UCL_MATCH_OVERRIDES for the seeded fixtures.
        # The override row REPLACES the default rights row for that
        # territory only — all other territories retain their default
        # UCL_RIGHTS entry.
        home = fixture.get("home_team", "")
        away = fixture.get("away_team", "")
        override = get_ucl_match_override(home, away, kickoff)
        if override:
            for territory, row in override.items():
                # Canonicalise both directions: "Ireland" → "Republic of
                # Ireland" (the form used by EPL_RIGHTS, EFL_RIGHTS and
                # the frontend). Hand-edited overrides may use either,
                # but the output should always be canonical.
                if territory == "Ireland":
                    rights_map.pop("Ireland", None)
                    rights_map["Republic of Ireland"] = row
                elif territory == "Republic of Ireland":
                    rights_map.pop("Ireland", None)
                    rights_map["Republic of Ireland"] = row
                else:
                    rights_map[territory] = row
            logger.info(
                f"[ucl_override] {home} v {away} ({kickoff[:10]}): "
                f"applied override for {sorted(override.keys())}"
            )
    elif comp_code in ("ELC", "EL1", "EL2", "NAT", "FACUP", "EFLCUP"):
        rights_map = dict(EFL_RIGHTS)
        # ── Per-competition UK override ──
        if comp_code in EFL_UK_OVERRIDES:
            rights_map["United Kingdom"] = EFL_UK_OVERRIDES[comp_code]
        # ── Per-competition territory exclusions ──
        excluded = EFL_TERRITORY_EXCLUSIONS.get(comp_code, set())
        for territory in excluded:
            rights_map.pop(territory, None)
    elif comp_code in ("SP1", "SC1", "SCH", "SCUP", "SLCUP"):
        rights_map = dict(SCOTTISH_RIGHTS)
    elif rights_key in ("la_liga", "bundesliga", "serie_a", "ligue_1", "eredivisie"):
        rights_map = {}
        for territory, row in EUROPEAN_LEAGUES_RIGHTS.items():
            broadcaster = row.get(rights_key, "")
            if broadcaster:
                rights_map[territory] = {"broadcaster": broadcaster, "region": territory}
    else:
        rights_map = {}

    # UK — special handling with blackout logic
    uk_data = uk_channels.get(fixture_id)

    if comp_code == "PL" and is_blackout:
        pass
    elif comp_code == "PL" and uk_data:
        channels = uk_data.get("channels", [])
        bcast_channels: dict = {}
        for ch in channels:
            from sources.uk_channels import CHANNEL_TO_BROADCASTER
            bcast = CHANNEL_TO_BROADCASTER.get(ch, ch)
            bcast_channels.setdefault(bcast, []).append(ch)

        for bcast, chans in bcast_channels.items():
            meta = BROADCASTER_META.get(bcast, {})
            coverage = "highlights" if bcast == "BBC" else "live"
            broadcasters.append({
                "territory":   "United Kingdom",
                "region":      "UK",
                "broadcaster": bcast,
                "channels":    chans,
                "type":        meta.get("type", "pay_tv"),
                "coverage":    coverage,
                "confidence":  "high",
            })
    elif comp_code == "PL":
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            day  = dt.weekday()
            hour = dt.hour
            minute = dt.minute
            is_tnt = (day == 5 and hour == 11 and minute == 30)
        except Exception:
            is_tnt = False

        live_broadcaster = "TNT Sports" if is_tnt else "Sky Sports"
        live_meta = BROADCASTER_META.get(live_broadcaster, {})
        broadcasters.append({
            "territory":   "United Kingdom",
            "region":      "UK",
            "broadcaster": live_broadcaster,
            "channels":    live_meta.get("channels", [live_broadcaster]),
            "type":        live_meta.get("type", "pay_tv"),
            "coverage":    "live",
            "confidence":  "medium",
        })
        bbc_meta = BROADCASTER_META.get("BBC", {})
        broadcasters.append({
            "territory":   "United Kingdom",
            "region":      "UK",
            "broadcaster": "BBC",
            "channels":    ["BBC iPlayer", "BBC One"],
            "type":        "free_tv",
            "coverage":    "highlights",
            "confidence":  "high",
            "source":      "rights",
        })
    elif "United Kingdom" in rights_map:
        entry = rights_map["United Kingdom"]
        for bcast_name in entry["broadcaster"].split(";"):
            bcast_name = bcast_name.strip()
            if not bcast_name:
                continue
            meta = BROADCASTER_META.get(bcast_name, {})
            # BBC is highlights for UCL (forced by _resolve_coverage via
            # UCL_HIGHLIGHTS_ONLY); for other comps where it's listed as
            # a UK rights holder it's live (e.g. FA Cup).
            default_coverage = "highlights" if bcast_name == "BBC" else "live"
            coverage = _resolve_coverage(default_coverage, bcast_name)
            broadcasters.append({
                "territory":   "United Kingdom",
                "region":      "UK",
                "broadcaster": bcast_name,
                "channels":    meta.get("channels", [bcast_name]),
                "type":        meta.get("type", "pay_tv"),
                "coverage":    coverage,
                "confidence":  "medium",
            })

    # All other territories from rights map
    for territory, entry in rights_map.items():
        if territory == "United Kingdom":
            continue

        if comp_code == "PL" and territory == "Republic of Ireland":
            # Tier 0: liveonsat explicitly lists the ROI broadcaster per match.
            # This is the only source that says WHICH 3pm match Premier Sports
            # Ireland picked, so it outranks both EPG and static rights.
            los_roi = los_terrs.get("Republic of Ireland")
            if los_roi:
                broadcasters.append({
                    "territory":   "Republic of Ireland",
                    "region":      "Europe",
                    "broadcaster": los_roi["broadcaster"],
                    "channels":    los_roi["channels"],
                    "type":        "pay_tv",
                    "coverage":    "live",
                    "confidence":  "high",
                    "source":      "liveonsat",
                })
                continue

            # If liveonsat matched this fixture but listed NO Irish channel,
            # Ireland genuinely isn't showing it — omit rather than guess.
            if los_terrs and is_blackout:
                continue

            epg_territory = (epg_data.get(fixture_id) or {}).get("Republic of Ireland")
            if epg_territory:
                broadcasters.append({
                    "territory":   "Republic of Ireland",
                    "region":      "Europe",
                    "broadcaster": epg_territory["broadcaster"],
                    "channels":    epg_territory["channels"],
                    "type":        "pay_tv",
                    "coverage":    "live" if epg_territory.get("is_live") else "live",
                    "confidence":  "high",
                    "source":      "epg",
                })
                continue

            if is_blackout:
                continue
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                is_tnt = (dt.weekday() == 5 and dt.hour == 11 and dt.minute == 30)
            except Exception:
                is_tnt = False

            live_broadcaster = "TNT Sports" if is_tnt else "Sky Sports"
            live_meta = BROADCASTER_META.get(live_broadcaster, {})
            broadcasters.append({
                "territory":   "Republic of Ireland",
                "region":      "Europe",
                "broadcaster": live_broadcaster,
                "channels":    live_meta.get("channels", [live_broadcaster]),
                "type":        live_meta.get("type", "pay_tv"),
                "coverage":    "live",
                "confidence":  "medium",
                "source":      "rights",
            })
            continue

        if comp_code == "PL" and territory == "United States":
            epg_territory = (epg_data.get(fixture_id) or {}).get("United States")
            if epg_territory:
                broadcasters.append({
                    "territory":   "United States",
                    "region":      "Americas",
                    "broadcaster": epg_territory["broadcaster"],
                    "channels":    epg_territory["channels"],
                    "type":        "pay_tv",
                    "coverage":    "live" if epg_territory.get("is_live") else "live",
                    "confidence":  "high",
                    "source":      "epg",
                })
                continue

            from datetime import datetime
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                day  = dt.weekday()
                hour = dt.hour
                minute = dt.minute

                if day == 5 and hour == 11 and minute == 30:
                    channels    = ["USA Network", "Peacock"]
                    broadcaster = "NBC Sports / Peacock"
                elif day == 5 and hour == 14:
                    channels    = ["Peacock", "USA Network"]
                    broadcaster = "NBC Sports / Peacock"
                elif day == 5 and hour == 16 and minute == 30:
                    channels    = ["USA Network", "Peacock"]
                    broadcaster = "NBC Sports / Peacock"
                elif day == 6 and 13 <= hour <= 15:
                    channels    = ["USA Network", "Peacock"]
                    broadcaster = "NBC Sports / Peacock"
                elif day in (0, 1, 2, 3, 4):
                    channels    = ["USA Network", "Peacock"]
                    broadcaster = "NBC Sports / Peacock"
                else:
                    channels    = ["Peacock"]
                    broadcaster = "NBC Sports / Peacock"

                broadcasters.append({
                    "territory":   "United States",
                    "region":      "Americas",
                    "broadcaster": broadcaster,
                    "channels":    channels,
                    "type":        "pay_tv",
                    "coverage":    "live",
                    "confidence":  "medium",
                    "source":      "rights",
                })
                continue
            except Exception:
                pass

        broadcaster_names = entry.get("broadcaster", "")
        region = entry.get("region", "")

        for bcast_name in broadcaster_names.split(";"):
            bcast_name = bcast_name.strip()
            if not bcast_name:
                continue

            meta = BROADCASTER_META.get(bcast_name, {})

            epg_fixture = epg_data.get(fixture_id) or {}
            epg_territory = epg_fixture.get(territory)

            if epg_territory and epg_territory.get("broadcaster", "").lower() in bcast_name.lower() or \
               epg_territory and bcast_name.lower() in epg_territory.get("broadcaster", "").lower():
                broadcasters.append({
                    "territory":   territory,
                    "region":      region,
                    "broadcaster": epg_territory["broadcaster"],
                    "channels":    epg_territory["channels"],
                    "type":        meta.get("type", "pay_tv"),
                    "coverage":    _resolve_coverage(
                                       "live" if epg_territory.get("is_live") else "live",
                                       epg_territory["broadcaster"]),
                    "confidence":  "high",
                    "source":      "epg",
                })
                continue

            channels = meta.get("channels")
            if channels:
                broadcasters.append({
                    "territory":   territory,
                    "region":      region,
                    "broadcaster": bcast_name,
                    "channels":    channels,
                    "type":        meta.get("type", "pay_tv"),
                    "coverage":    _resolve_coverage("live", bcast_name),
                    "confidence":  "medium",
                    "source":      "rights",
                })
                continue

            broadcasters.append({
                "territory":   territory,
                "region":      region,
                "broadcaster": bcast_name,
                "channels":    [bcast_name],
                "type":        meta.get("type", "pay_tv"),
                "coverage":    _resolve_coverage("live", bcast_name),
                "confidence":  "low",
                "source":      "rights_db_generic",
            })

    for b in broadcasters:
        if b.get("channels"):
            b["channels"] = normalise_channel_list(b["channels"])

    return broadcasters


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — ASSEMBLE OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def assemble_output(fixtures: list, uk_channels: dict, epg_data: dict,
                    los_data: dict | None = None) -> list:
    output = []
    for fixture in fixtures:
        broadcasters = build_broadcaster_list(fixture, uk_channels, epg_data, los_data)

        output.append({
            "id":           fixture["id"],
            "competition":  fixture["competition"],
            "comp_code":    fixture["comp_code"],
            "home_team":    fixture["home_team"],
            "away_team":    fixture["away_team"],
            "kickoff":      fixture["kickoff"],
            "matchday":     fixture.get("matchday"),
            "stage":        fixture.get("stage", ""),
            "group":        fixture.get("group", ""),
            "is_blackout":  fixture.get("comp_code") == "PL" and is_epl_blackout(fixture.get("kickoff", "")),
            "broadcasters": broadcasters,
            "broadcaster_count": len(broadcasters),
        })

    return output


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("TVsport scraper pipeline starting")
    logger.info("=" * 60)

    raw_fixtures = fetch_fixtures()

    if not raw_fixtures:
        logger.error("[pipeline] No fixtures fetched — aborting. Check FOOTBALL_DATA_API_KEY.")
        sys.exit(1)

    fixtures = dedup_fixtures(raw_fixtures)

    uk_channels = enrich_uk_channels(fixtures)
    epg_data = enrich_epg(fixtures)
    los_data = enrich_liveonsat(fixtures)

    output = assemble_output(fixtures, uk_channels, epg_data, los_data)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump({
            "generated_at": now_iso,
            "lastUpdated":  now_iso,
            "fixture_count": len(output),
            "fixtures": output,
        }, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Written {len(output)} fixtures to {OUTPUT_PATH}")

    from collections import Counter
    comp_counts = Counter(f["competition"] for f in output)
    for comp, count in sorted(comp_counts.items()):
        logger.info(f"  {comp}: {count} fixtures")

    blackouts = sum(1 for f in output if f.get("is_blackout"))
    if blackouts:
        logger.info(f"  (of which {blackouts} EPL fixtures are UK 3pm blackouts)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
