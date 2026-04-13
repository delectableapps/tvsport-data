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

    # Scottish leagues
    try:
        from sources.fixtures_spfl import scrape_fixtures as spfl_scrape
        spfl_fixtures = spfl_scrape()
        added = 0
        for f in spfl_fixtures:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                all_fixtures.append(f)
                added += 1
        logger.info(f"[pipeline] spfl.co.uk: {added} new fixtures added")
    except Exception as e:
        logger.warning(f"[pipeline] spfl.co.uk scraper failed: {e}")

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
    Fetch livefootballontv.com and return per-fixture UK channel data.
    Returns { fixture_id: { channels: [...], kickoff_display: "..." } }
    """
    try:
        from sources.uk_channels import get_uk_channels
        return get_uk_channels(fixtures)
    except Exception as e:
        logger.warning(f"[pipeline] UK channel enrichment failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — EPG CHANNEL LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

def enrich_epg(fixtures: list) -> dict:
    """
    Run iptv-org/epg grab and parse guide.xml.
    Returns { fixture_id: { territory: channel_name, ... } }
    """
    try:
        from sources.epg.epg_runner import run_epg_grab
        from sources.epg.epg_xmltv_parser import parse_guide

        channels_xml = os.path.join(os.path.dirname(__file__), "sources", "epg", "epg_channels.xml")
        guide_xml = os.path.join(os.path.dirname(__file__), "..", "guide.xml")

        run_epg_grab(channels_xml, guide_xml)
        epg_data = parse_guide(guide_xml, days_ahead=14)
        logger.info(f"[pipeline] EPG: {len(epg_data)} programme entries parsed")
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
    elif rights_key in ("la_liga", "bundesliga", "serie_a", "ligue_1"):
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
            if is_blackout:
                continue  # no ROI broadcasters during blackout either
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
            })
            # Premier Sports always shown for ROI
            ps_meta = BROADCASTER_META.get("Premier Sports", {})
            broadcasters.append({
                "territory":   "Republic of Ireland",
                "region":      "Europe",
                "broadcaster": "Premier Sports",
                "channels":    ps_meta.get("channels", ["Premier Sports 1", "Premier Sports 2"]),
                "type":        "pay_tv",
                "coverage":    "live",
                "confidence":  "medium",
            })
            continue

        broadcaster_names = entry.get("broadcaster", "")
        region = entry.get("region", "")

        for bcast_name in broadcaster_names.split(";"):
            bcast_name = bcast_name.strip()
            if not bcast_name:
                continue

            meta = BROADCASTER_META.get(bcast_name, {})

            # Try to find specific channel from EPG
            epg_channel = None
            if epg_data:
                # EPG data is keyed by (home_team, away_team) or fixture_id
                epg_entry = epg_data.get(fixture_id) or epg_data.get(
                    f"{fixture.get('home_team', '')} v {fixture.get('away_team', '')}"
                )
                if epg_entry:
                    # Match by broadcaster name
                    epg_channel = epg_entry.get(bcast_name)

            channels = [epg_channel] if epg_channel else meta.get("channels", [bcast_name])
            confidence = "high" if epg_channel else "medium"

            broadcasters.append({
                "territory":   territory,
                "region":      region,
                "broadcaster": bcast_name,
                "channels":    channels,
                "type":        meta.get("type", "pay_tv"),
                "coverage":    "live",
                "confidence":  confidence,
            })

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
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
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
