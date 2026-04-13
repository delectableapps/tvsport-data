"""
merger.py — TVsport Nightly Fixture Pipeline
Main entry point. Runs all scrapers, merges rights data, outputs fixtures.json

Competitions covered:
  EPL, UCL, EFL (CH/L1/L2/NAT), Scottish (SPL/SCH/SCUP),
  La Liga, Bundesliga, Serie A, Serie B, Ligue 1, Eredivisie, Primeira Liga,
  FA Cup, EFL Cup

Run:
  cd scraper && python merger.py
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("merger")

# ── Path setup ────────────────────────────────────────────────────────
SCRAPER_DIR = Path(__file__).parent
OUTPUT_DIR  = SCRAPER_DIR.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "fixtures.json"

sys.path.insert(0, str(SCRAPER_DIR))

# ── Rights DB ─────────────────────────────────────────────────────────
from rights_db import COMPETITION_RIGHTS


# ─────────────────────────────────────────────────────────────────────
# IMPORT SCRAPERS (each returns list of fixture dicts)
# ─────────────────────────────────────────────────────────────────────

def _safe_import(module_name: str, *func_names):
    """
    Import a scraper function safely, trying multiple possible function names.
    Returns the first one found, or None if none exist.
    This handles cases where existing scrapers use different naming conventions.
    """
    try:
        mod = __import__(f"sources.{module_name}", fromlist=list(func_names))
    except ImportError as e:
        log.warning(f"Could not import module {module_name}: {e}")
        return None

    for func_name in func_names:
        fn = getattr(mod, func_name, None)
        if fn is not None:
            log.debug(f"  {module_name}: using function '{func_name}'")
            return fn

    # None of the expected names found — list what IS available
    available = [x for x in dir(mod) if not x.startswith('_')]
    log.warning(f"  {module_name}: none of {func_names} found. Available: {available}")
    return None


def _run_scraper(label: str, fn, *args) -> list:
    """Run a scraper function and return results, logging any errors."""
    if fn is None:
        log.warning(f"  {label}: scraper not available, skipping")
        return []
    try:
        results = fn(*args) or []
        log.info(f"  {label}: {len(results)} items")
        return results
    except Exception as e:
        log.error(f"  {label}: FAILED — {e}")
        return []


# ─────────────────────────────────────────────────────────────────────
# FIXTURE ASSEMBLY
# ─────────────────────────────────────────────────────────────────────

def attach_rights(fixture: dict) -> dict:
    """
    Attach broadcast rights to a fixture.
    EPG-type rights: channels resolved at runtime by EPG pipeline.
    Static-type rights: channels embedded directly.
    """
    comp = fixture.get("competition", "")
    rights = COMPETITION_RIGHTS.get(comp, {})

    broadcaster_regions = []
    for territory, data in rights.items():
        entry = {
            "territory": territory,
            "broadcaster": data.get("broadcaster", ""),
            "channels": data.get("channels", []),
            "type": data.get("type", "static"),
            "badges": data.get("badges", ["live", "tv"]),
        }
        # Handle UK blackout
        if (data.get("blackout_rule") and
                fixture.get("blackout") and
                territory == "United Kingdom"):
            entry["blackout"] = True
            entry["channels"] = []

        broadcaster_regions.append(entry)

    fixture["broadcasters"] = broadcaster_regions
    return fixture


def normalise_fixture(f: dict) -> dict:
    """
    Normalise fixture dict to a consistent schema.
    Different scrapers use different field names — this maps them all
    to the standard keys the rest of merger.py expects.
    """
    if not isinstance(f, dict):
        return {}

    # Competition key
    if "competition" not in f or not f["competition"]:
        f["competition"] = (
            f.get("competition_code") or
            f.get("league") or
            f.get("comp") or
            "?"
        )

    # Team names
    if "home_team" not in f or not f["home_team"]:
        f["home_team"] = f.get("home") or f.get("home_team_name") or ""
    if "away_team" not in f or not f["away_team"]:
        f["away_team"] = f.get("away") or f.get("away_team_name") or ""

    # Kickoff
    if "kickoff" not in f or not f["kickoff"]:
        f["kickoff"] = f.get("date") or f.get("datetime") or f.get("kick_off") or ""

    # Blackout flag
    if "blackout" not in f:
        f["blackout"] = False

    return f



    """Remove duplicate fixtures by (competition, home, away, date)."""
    seen = set()
    out = []
    for f in fixtures:
        ko = f.get("kickoff", "")[:10]  # date only
        key = (f.get("competition"), f.get("home_team"), f.get("away_team"), ko)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def run():
    log.info("=" * 60)
    log.info("TVsport nightly scrape starting")
    log.info(f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 60)

    all_fixtures = []

    # ── 1. EPL ────────────────────────────────────────────────────────
    log.info("── EPL ──")
    scrape_epl = _safe_import("fixtures_premierleague",
                               "get_all_fixtures", "scrape_epl_fixtures",
                               "get_epl_fixtures", "scrape_fixtures", "get_fixtures")
    all_fixtures += _run_scraper("EPL fixtures", scrape_epl)

    # ── 2. UK channels (EPL + UCL) ────────────────────────────────────
    log.info("── UK channels ──")
    scrape_uk_fotv = _safe_import("uk_live_footballontv",
                                   "scrape_uk_channels", "get_uk_channels",
                                   "scrape", "get_channels", "scrape_footballontv")
    scrape_uk_tvg  = _safe_import("uk_tvguide",
                                   "scrape_uk_times", "get_uk_times",
                                   "scrape", "scrape_tvguide", "get_times")
    uk_channels = _run_scraper("UK live-footballontv", scrape_uk_fotv)
    uk_times    = _run_scraper("UK tvguide.co.uk",     scrape_uk_tvg)

    # ── 3. UCL ────────────────────────────────────────────────────────
    log.info("── UCL ──")
    scrape_ucl = _safe_import("fixtures_uefa",
                               "scrape_ucl_fixtures", "get_ucl_fixtures",
                               "get_all_fixtures", "scrape_fixtures", "get_fixtures")
    all_fixtures += _run_scraper("UCL fixtures", scrape_ucl)

    # ── 4. US channels ────────────────────────────────────────────────
    log.info("── US channels ──")
    scrape_us = _safe_import("us_nbcsports",
                              "scrape_all", "scrape_epl", "scrape_ucl",
                              "scrape_us_channels", "get_us_channels", "get_channels")
    us_channels = _run_scraper("US NBC/CBS", scrape_us)

    # ── 5. Africa channels ────────────────────────────────────────────
    log.info("── Africa ──")
    scrape_africa = _safe_import("africa_supersport",
                                  "scrape_all", "scrape_channel",
                                  "scrape_supersport", "get_supersport", "get_channels")
    africa_data = _run_scraper("SuperSport Africa", scrape_africa)

    # ── 6. Asia channels ──────────────────────────────────────────────
    log.info("── Asia ──")
    scrape_asia = _safe_import("asia_scrapers",
                                "scrape_asia", "get_asia_channels",
                                "scrape", "scrape_astro", "get_channels")
    asia_data = _run_scraper("Asia (Astro/Star)", scrape_asia)

    # ── 7. EPG (beIN, Sky, TNT, Canal+, Viaplay, etc.) ───────────────
    log.info("── EPG ──")
    scrape_epg = _safe_import("epg.epg_runner",
                               "get_epg_fixtures", "grab_epg",
                               "run_epg_grab", "scrape_epg", "run", "main")
    epg_data = _run_scraper("iptv-org/epg", scrape_epg)

    # ── 7b. Amazon Prime Video ─────────────────────────────────────────
    # Amazon holds: UCL top-pick Tuesday (to 2030/31) + EFL selected matches
    # Amazon has NO EPL rights from 2025/26 onwards
    # No EPG feed available — scraped from live-footballontv.com
    log.info("── Amazon Prime Video ──")
    scrape_amazon = _safe_import("amazon_prime", "scrape_amazon_fixtures")
    amazon_raw = _run_scraper("Amazon Prime", scrape_amazon)
    # amazon_prime returns a dict, not a list — handle that
    amazon_lookup = amazon_raw if isinstance(amazon_raw, dict) else {}

    # ── 8. EFL (NEW) ──────────────────────────────────────────────────
    log.info("── EFL (Championship / League One / League Two / National) ──")
    scrape_efl = _safe_import("fixtures_efl", "scrape_efl_fixtures")
    all_fixtures += _run_scraper("EFL", scrape_efl)

    # ── 9. Scottish (NEW) ─────────────────────────────────────────────
    log.info("── Scottish (SPL / Championship / Cup) ──")
    scrape_spfl = _safe_import("fixtures_spfl", "scrape_spfl_fixtures")
    all_fixtures += _run_scraper("SPFL", scrape_spfl)

    # ── 10. European leagues (NEW) ────────────────────────────────────
    log.info("── European Leagues (La Liga / Bundesliga / Serie A / Ligue 1 / Eredivisie / Primeira) ──")
    scrape_eur = _safe_import("fixtures_european", "scrape_european_fixtures")
    all_fixtures += _run_scraper("European leagues", scrape_eur)

    # ── Merge supplemental data onto fixtures ─────────────────────────
    log.info("── Merging channel data onto fixtures ──")

    def safe_lookup(data_list):
        """Build a (home, away) lookup dict, safely skipping non-dict items."""
        result = {}
        for d in (data_list or []):
            if isinstance(d, dict):
                home = d.get("home") or d.get("home_team")
                away = d.get("away") or d.get("away_team")
                if home and away:
                    result[(home, away)] = d
        return result

    uk_ch_lookup   = safe_lookup(uk_channels)
    uk_time_lookup = safe_lookup(uk_times)
    us_ch_lookup   = safe_lookup(us_channels)
    africa_lookup  = safe_lookup(africa_data)
    asia_lookup    = safe_lookup(asia_data)
    epg_lookup     = safe_lookup(epg_data)

    # Filter out any non-dict items that scrapers may have returned
    all_fixtures = [f for f in all_fixtures if isinstance(f, dict)]

    for f in all_fixtures:
        key = (f.get("home_team"), f.get("away_team"))

        # Override UK channel assignments from live-footballontv
        if key in uk_ch_lookup:
            f["uk_channels"] = uk_ch_lookup[key].get("channels", [])
        if key in uk_time_lookup:
            f["uk_coverage_start"] = uk_time_lookup[key].get("coverage_start")

        # Amazon Prime override — marks fixture as Amazon if scraped
        if key in amazon_lookup:
            f["amazon_prime"] = True
            f["amazon_channel"] = amazon_lookup[key]

        # US channel assignments
        if key in us_ch_lookup:
            f["us_channels"] = us_ch_lookup[key].get("channels", [])

        # Africa channel override
        if key in africa_lookup:
            f["africa_channels"] = africa_lookup[key].get("channels", [])

        # Asia
        if key in asia_lookup:
            f["asia_channels"] = asia_lookup[key].get("channels", [])

        # EPG data — most accurate, overrides static rights where available
        if key in epg_lookup:
            f["epg_channels"] = epg_lookup[key].get("channels", {})

    # ── Normalise all fixtures to consistent schema ───────────────────
    all_fixtures = [normalise_fixture(f) for f in all_fixtures if isinstance(f, dict)]
    all_fixtures = [f for f in all_fixtures if f.get("competition") and f.get("home_team")]

    # Log what we have before dedup
    raw_by_comp = {}
    for f in all_fixtures:
        raw_by_comp[f["competition"]] = raw_by_comp.get(f["competition"], 0) + 1
    log.info("── Raw fixture counts before dedup ──")
    for comp, n in sorted(raw_by_comp.items()):
        log.info(f"  {comp:<14} {n}")

    # ── Dedup, attach rights, sort ────────────────────────────────────
    all_fixtures = dedup_fixtures(all_fixtures)
    all_fixtures = [attach_rights(f) for f in all_fixtures]
    all_fixtures.sort(key=lambda f: f.get("kickoff", ""))

    # ── Summary ───────────────────────────────────────────────────────
    by_comp = {}
    for f in all_fixtures:
        by_comp.setdefault(f.get("competition", "?"), 0)
        by_comp[f["competition"]] += 1

    log.info("")
    log.info("── Fixture summary ──")
    for comp, count in sorted(by_comp.items()):
        log.info(f"  {comp:<14} {count} fixtures")
    log.info(f"  {'TOTAL':<14} {len(all_fixtures)} fixtures")

    # ── Output ────────────────────────────────────────────────────────
    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(all_fixtures),
        "competitions": list(by_comp.keys()),
        "fixtures": all_fixtures,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    log.info("")
    log.info(f"✅ Written {len(all_fixtures)} fixtures to {OUTPUT_FILE}")
    return len(all_fixtures)


if __name__ == "__main__":
    count = run()
    sys.exit(0 if count > 0 else 1)
