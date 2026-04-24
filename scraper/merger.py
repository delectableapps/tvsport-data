"""
merger.py — TVsport scraper pipeline
Run this to generate output/fixtures.json

Usage:
    cd scraper && python merger.py

Sources (in priority order):
    1. football-data.org API  — primary fixtures (EPL, UCL, EFL, European leagues)
    2. efl.com scraper        — fallback/validator for EFL
    3. spfl.co.uk scraper     — Scottish leagues
    4. livefootballontv.com   — UK channel assignments per fixture
    5. iptv-org/epg (XMLTV)   — international channel assignments
    6. rights_db.py           — broadcast rights layer (who has rights per territory)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

# Add scraper directory to path
sys.path.insert(0, os.path.dirname(__file__))

from rights_db import (
    EPL_RIGHTS, UCL_RIGHTS, EFL_RIGHTS, SCOTTISH_RIGHTS,
    EUROPEAN_LEAGUES_RIGHTS, BROADCASTER_META,
    get_all_rights_for_competition, is_epl_blackout,
    COMP_CODE_TO_RIGHTS_KEY,
)
from channel_normaliser import normalise_channel_list

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "fixtures.json")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — FETCH FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fixtures() -> list:
    """Pull fixtures from all sources and merge."""
    all_fixtures = []
    seen_ids = set()

    # Primary: football-data.org
    try:
        from sources.fixtures_footballdata import scrape_fixtures as fd_scrape
        fd_fixtures = fd_scrape()
        logger.info(f"[pipeline] football-data.org: {len(fd_fixtures)} fixtures")
        for f in fd_fixtures:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
    except Exception as e:
        logger.error(f"[pipeline] football-data.org failed: {e}")

    # Fallback: EFL official site (catches anything football-data.org missed)
    try:
        from sources.fixtures_efl import scrape_fixtures as efl_scrape
        efl_fixtures = efl_scrape()
        added = 0
        for f in efl_fixtures:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
                added += 1
        logger.info(f"[pipeline] efl.com: {added} new fixtures added")
    except Exception as e:
        logger.warning(f"[pipeline] efl.com scraper failed: {e}")

    # Scottish leagues — primary: Sportmonks API, fallback: spfl.co.uk
    try:
        from sources.fixtures_sportmonks import scrape_fixtures as sportmonks_scrape
        sportmonks_fixtures = sportmonks_scrape()
        added = 0
        for f in sportmonks_fixtures:
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
                if f["id"] not in seen_ids:
                    seen_ids.add(f["id"])
                    all_fixtures.append(f)
                    added += 1
            logger.info(f"[pipeline] spfl.co.uk fallback: {added} fixtures added")
        except Exception as e2:
            logger.warning(f"[pipeline] spfl.co.uk fallback also failed: {e2}")

    logger.info(f"[pipeline] Total fixtures before dedup: {len(all_fixtures)}")
    return all_fixtures


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────

def dedup_fixtures(fixtures: list) -> list:
    """Remove duplicate fixtures keyed by (competition, home, away, date)."""
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
    """
    Fetch UK channel data from skysports.com (primary) and livefootballontv.com (fallback).
    Returns { fixture_id: { channels: [...], kickoff_display: "..." } }
    """
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
    """
    Download and parse EPGshare01 feeds to get match-level broadcaster data.
    Returns { fixture_id: { territory: broadcaster_data_dict } }

    Tier 1 (high confidence): exact match confirmed from EPG schedule.
    Falls back gracefully — failure here is non-fatal, rights_db fills the gap.
    """
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
# STEP 5 — BUILD BROADCASTER LIST PER FIXTURE
# ─────────────────────────────────────────────────────────────────────────────

def build_broadcaster_list(fixture: dict, uk_channels: dict, epg_data: dict) -> list:
    """
    Build the full worldwide broadcaster list for a single fixture.
    Returns list of broadcaster dicts:
        { territory, region, broadcaster, channels: [...], type, coverage }
    """
    comp_code    = fixture.get("comp_code", "")
    fixture_id   = fixture.get("id", "")
    kickoff      = fixture.get("kickoff", "")
    is_blackout  = (comp_code == "PL" and is_epl_blackout(kickoff))
    rights_key   = COMP_CODE_TO_RIGHTS_KEY.get(comp_code, "")

    broadcasters = []

    # Get the appropriate rights dictionary for this competition
    if comp_code == "PL":
        rights_map = dict(EPL_RIGHTS)
        rights_map["United Kingdom"] = {"broadcaster": "Sky Sports; TNT Sports", "region": "UK"}
    elif comp_code in ("CL", "EL", "ECL"):
        rights_map = dict(UCL_RIGHTS)
    elif comp_code in ("ELC", "EL1", "EL2", "FAC"):
        rights_map = dict(EFL_RIGHTS)
    elif comp_code in ("SP1", "SC1"):
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
        # 3pm Saturday: suppress all UK broadcasters
        pass
    elif comp_code == "PL" and uk_data:
        # We have specific UK channel data from livefootballontv
        channels = uk_data.get("channels", [])
        # Group channels by broadcaster
        bcast_channels: dict = {}
        for ch in channels:
            from sources.uk_channels import CHANNEL_TO_BROADCASTER
            bcast = CHANNEL_TO_BROADCASTER.get(ch, ch)
            bcast_channels.setdefault(bcast, []).append(ch)

        for bcast, chans in bcast_channels.items():
            meta = BROADCASTER_META.get(bcast, {})
            # BBC is highlights only for EPL
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
        # No livefootballontv data — derive UK broadcaster from kickoff slot rules:
        # TNT Sports:  Saturday 12:30 (11:30 UTC summer / 12:30 UTC winter)
        # Sky Sports:  all other live slots
        # BBC:         highlights only, always added alongside live broadcaster
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            day  = dt.weekday()   # 0=Mon … 5=Sat … 6=Sun
            hour = dt.hour
            minute = dt.minute
            # Saturday 12:30 BST = 11:30 UTC (BST season Apr–Oct)
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
        # BBC always added as highlights only
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
        # Non-EPL fallback: use rights DB for UK as-is
        entry = rights_map["United Kingdom"]
        for bcast_name in entry["broadcaster"].split(";"):
            bcast_name = bcast_name.strip()
            if not bcast_name:
                continue
            meta = BROADCASTER_META.get(bcast_name, {})
            coverage = "highlights" if bcast_name == "BBC" else "live"
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
            continue  # handled above

        # Republic of Ireland — EPL slot logic mirrors UK
        # TNT: Saturday 12:30 only. Sky: all other slots. Premier Sports: always.
        if comp_code == "PL" and territory == "Republic of Ireland":
            # Check EPG first (Tier 1)
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

            # Tier 2: slot-based inference
            if is_blackout:
                broadcasters.append({
                    "territory":   "Republic of Ireland",
                    "region":      "Europe",
                    "broadcaster": "Premier Sports",
                    "channels":    ["Premier Sports 1 Ireland HD"],
                    "type":        "pay_tv",
                    "coverage":    "live",
                    "confidence":  "medium",
                    "source":      "rights",
                })
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

        # United States — EPL slot logic
        if comp_code == "PL" and territory == "United States":
            # Check EPG first (Tier 1)
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

            # Tier 2: slot-based inference
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                day  = dt.weekday()
                hour = dt.hour
                if day == 5 and hour == 11:
                    channel = "NBC"
                    broadcaster = "NBC Sports / Peacock"
                elif day == 5 and hour == 16:
                    channel = "USA Network"
                    broadcaster = "NBC Sports / Peacock"
                elif day == 6 and hour <= 15:
                    channel = "NBC"
                    broadcaster = "NBC Sports / Peacock"
                else:
                    channel = "Peacock Premium"
                    broadcaster = "NBC Sports / Peacock"

                broadcasters.append({
                    "territory":   "United States",
                    "region":      "Americas",
                    "broadcaster": broadcaster,
                    "channels":    [channel, "Peacock Premium"],
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

            # ── Tier 1: EPG confirmed ─────────────────────────────────────
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
                    "coverage":    "live" if epg_territory.get("is_live") else "live",
                    "confidence":  "high",
                    "source":      "epg",
                })
                continue

            # ── Tier 2: Rights-db with channel list ───────────────────────
            channels = meta.get("channels")
            if channels:
                broadcasters.append({
                    "territory":   territory,
                    "region":      region,
                    "broadcaster": bcast_name,
                    "channels":    channels,
                    "type":        meta.get("type", "pay_tv"),
                    "coverage":    "live",
                    "confidence":  "medium",
                    "source":      "rights",
                })
                continue

            # ── Tier 3: Broadcaster name only ─────────────────────────────
            broadcasters.append({
                "territory":   territory,
                "region":      region,
                "broadcaster": bcast_name,
                "channels":    [bcast_name],
                "type":        meta.get("type", "pay_tv"),
                "coverage":    "live",
                "confidence":  "low",
                "source":      "rights_db_generic",
            })

    # Normalise all channel names to canonical forms
    for b in broadcasters:
        if b.get("channels"):
            b["channels"] = normalise_channel_list(b["channels"])

    return broadcasters


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — ASSEMBLE OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def assemble_output(fixtures: list, uk_channels: dict, epg_data: dict) -> list:
    """Build the final fixtures list with full broadcaster data."""
    output = []
    for fixture in fixtures:
        broadcasters = build_broadcaster_list(fixture, uk_channels, epg_data)

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

    # Step 1: Fetch fixtures
    raw_fixtures = fetch_fixtures()

    if not raw_fixtures:
        logger.error("[pipeline] No fixtures fetched — aborting. Check FOOTBALL_DATA_API_KEY.")
        sys.exit(1)

    # Step 2: Deduplicate
    fixtures = dedup_fixtures(raw_fixtures)

    # Step 3: UK channel enrichment
    uk_channels = enrich_uk_channels(fixtures)

    # Step 4: EPG channel enrichment (best-effort — failure is non-fatal)
    epg_data = enrich_epg(fixtures)

    # Step 5+6: Build output
    output = assemble_output(fixtures, uk_channels, epg_data)

    # Write JSON
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

    # Summary by competition
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
