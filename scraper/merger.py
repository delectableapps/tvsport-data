"""
merger.py  (v2 — EPG-first architecture)
==========================================
Combines all data sources into fixtures.json using a layered approach:

LAYER 1 — Fixture List (authoritative)
  EPL: premierleague.com fixture changes page
  UCL: Hardcoded UEFA schedule + uefa.com updates

LAYER 2 — EPG Sources (PRIMARY channel data — structured, reliable)
  Sky EPG API     → Sky Sports + TNT Sports (UK/Ireland)
  dp247 Freeview  → BBC, ITV (UK FTA)
  epg.pw          → beIN, SuperSport, Canal+, Viaplay, DAZN, Astro, Stan Sport

LAYER 3 — HTML Scrapers (SUPPLEMENT / FALLBACK)
  live-footballontv.com  → UK channels (fallback if Sky EPG fails)
  tvguide.co.uk          → UK coverage start times
  nbcsports.com          → US NBC/Peacock per fixture
  cbssports.com          → US Paramount+ per UCL fixture

LAYER 4 — Rights DB (FALLBACK for any territory not covered above)
  rights_db.py: your Excel file as Python — covers all 175 territories

Priority: EPG > HTML scraper > Rights DB
"""

import os, sys, json, logging, hashlib
from datetime import datetime, date, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

from rights_db import get_rights, get_meta, is_streaming_service
from sources.fixtures_premierleague import get_all_fixtures as get_epl_fixtures
from sources.fixtures_uefa import get_ucl_fixtures
from sources.epg.epg_xmltv_parser import scrape_all_epg
from sources.uk_live_footballontv import scrape_all as scrape_uk_html
from sources.uk_tvguide import scrape as scrape_tvguide
from sources.us_nbcsports import scrape_epl as scrape_us_epl, scrape_ucl as scrape_us_ucl
from sources.africa_supersport import scrape_all as scrape_africa
from sources.asia_scrapers import scrape_astro, assign_bein_channels

logger = logging.getLogger(__name__)
DAYS_AHEAD = 30
EPG_RELIABLE_DAYS = 14

REGION_ORDER = [
    "🇬🇧 United Kingdom","🇮🇪 Republic of Ireland","🇪🇺 Europe",
    "🇺🇸 United States","🇨🇦 Canada","🌎 Americas",
    "🌍 Middle East & North Africa","🌍 Sub-Saharan Africa",
    "🇮🇳 India / South Asia","🌏 Asia",
    "🇦🇺 Australia / New Zealand","🌏 Pacific Islands","✈️ In-flight / Ships",
]
COUNTRY_REGION = {
    "United Kingdom":"🇬🇧 United Kingdom","Republic of Ireland":"🇮🇪 Republic of Ireland",
    "United States":"🇺🇸 United States","Canada":"🇨🇦 Canada",
    "Australia":"🇦🇺 Australia / New Zealand","New Zealand":"🇦🇺 Australia / New Zealand",
    "Middle East & North Africa":"🌍 Middle East & North Africa",
    "Sub-Saharan Africa":"🌍 Sub-Saharan Africa",
    "India / South Asia":"🇮🇳 India / South Asia","South Asia":"🇮🇳 India / South Asia",
    "Brazil":"🌎 Americas","South America":"🌎 Americas",
    "Central America":"🌎 Americas","Mexico":"🌎 Americas","Caribbean":"🌎 Americas",
    "In-flight / Ships":"✈️ In-flight / Ships",
}
EUROPEAN_COUNTRIES = {
    "Albania","Andorra","Armenia","Austria","Azerbaijan","Belarus","Belgium",
    "Bosnia & Herzegovina","Bulgaria","Croatia","Cyprus","Czechia","Czech Republic",
    "Denmark","Estonia","Finland","France","Georgia","Germany","Gibraltar","Greece",
    "Hungary","Iceland","Israel","Italy","Kazakhstan","Kosovo","Latvia","Lithuania",
    "Luxembourg","Malta","Moldova","Montenegro","Netherlands","North Macedonia",
    "Norway","Poland","Portugal","Romania","Russia","Serbia","Slovakia","Slovenia",
    "Spain","Sweden","Switzerland","Turkey","Ukraine",
}
ASIAN_COUNTRIES = {
    "Afghanistan","Brunei","Cambodia","China","Chinese Taipei","Hong Kong",
    "Indonesia","Japan","Laos","Macau","Malaysia","Mongolia","Myanmar",
    "Philippines","Singapore","South Korea","Taiwan","Thailand","Uzbekistan","Vietnam",
}

def get_region(country):
    if country in COUNTRY_REGION: return COUNTRY_REGION[country]
    if country in EUROPEAN_COUNTRIES: return "🇪🇺 Europe"
    if country in ASIAN_COUNTRIES: return "🌏 Asia"
    return f"🌐 {country}"

def normalise_key(home, away):
    def n(s):
        return s.strip().lower().replace("&","and").replace(".","").replace("'","").replace("-"," ")
    return f"{n(home)} v {n(away)}"

def fixture_id(competition, home, away, kickoff_utc):
    raw = f"{competition}_{home}_{away}_{kickoff_utc[:10]}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{competition.lower()}_{kickoff_utc[:10].replace('-','')}_{home.lower().replace(' ','_')[:15]}_{away.lower().replace(' ','_')[:15]}_{h}"

def make_entry(broadcaster, country, channels, highlights_only=False,
               coverage_start=None, source="rights_db"):
    meta = get_meta(broadcaster)
    return {
        "broadcaster": broadcaster, "country": country,
        "region": get_region(country), "channels": channels,
        "type": meta["type"], "icon": meta["icon"],
        "coverageType": "HIGHLIGHTS" if highlights_only else "LIVE",
        "coverageStart": coverage_start, "_source": source,
    }

def merge_layers(epg, html, rights):
    """Merge EPG > HTML > Rights DB, deduplicating by (broadcaster, country)."""
    seen = {}
    for entry in epg:
        k = (entry["broadcaster"], entry["country"])
        if k not in seen:
            seen[k] = entry
    for entry in html:
        k = (entry["broadcaster"], entry["country"])
        if k not in seen:
            seen[k] = entry
        elif seen[k].get("coverageStart") is None and entry.get("coverageStart"):
            seen[k]["coverageStart"] = entry["coverageStart"]
    for entry in rights:
        k = (entry["broadcaster"], entry["country"])
        if k not in seen:
            seen[k] = entry
    result = list(seen.values())
    for b in result:
        b.pop("_source", None)
    return result

def run(output_path=None):
    if output_path is None:
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output","fixtures.json")

    logger.info("═══ TVsport data pipeline starting ═══")

    # Layer 1: fixture lists
    logger.info("Layer 1: Fetching fixture lists...")
    epl_fixtures = get_epl_fixtures(DAYS_AHEAD)
    ucl_fixtures  = get_ucl_fixtures(DAYS_AHEAD)
    logger.info(f"  EPL: {len(epl_fixtures)}  UCL: {len(ucl_fixtures)}")

    # Layer 2: EPG (primary)
    logger.info("Layer 2: EPG sources...")
    epg_data = scrape_all_epg(EPG_RELIABLE_DAYS)
    logger.info(f"  EPG fixtures with channel data: {len(epg_data)}")

    # Layer 3: HTML scrapers (supplement)
    logger.info("Layer 3: HTML scrapers...")
    uk_html     = scrape_uk_html()
    tvguide     = scrape_tvguide()
    us_epl_data = scrape_us_epl()
    us_ucl_data = scrape_us_ucl()
    africa_data = scrape_africa(DAYS_AHEAD)
    astro_data  = scrape_astro(DAYS_AHEAD)

    # beIN importance ranking
    all_fx_list = (
        [{"home":f["home"],"away":f["away"],"date":f["date"]} for f in epl_fixtures.values()] +
        [{"home":f["home"],"away":f["away"],"date":f["date"]} for f in ucl_fixtures]
    )
    ranked = assign_bein_channels(all_fx_list)
    bein_map = {normalise_key(f["home"],f["away"]): f.get("bein_channel","beIN Sports HD 1") for f in ranked}

    # Layer 4: Build fixtures
    logger.info("Layer 4: Building broadcaster lists...")
    output_fixtures = []
    all_fixtures = (
        [{**f, "_key": k} for k, f in epl_fixtures.items()] +
        [{**f, "_key": f["fixture_key"]} for f in ucl_fixtures]
    )

    for fx in all_fixtures:
        key         = fx["_key"]
        competition = fx["competition"]
        home        = fx["home"]
        away        = fx["away"]
        uk_blackout = fx.get("uk_blackout", False)
        bein_ch     = bein_map.get(key, "beIN Sports HD 1")

        # ── EPG entries ────────────────────────────────────────────
        epg_entry = epg_data.get(key, {})
        epg_entries = [
            make_entry(b["broadcaster"], b["country"], b["channels"],
                       highlights_only=(b.get("coverageType")=="HIGHLIGHTS"),
                       coverage_start=b.get("coverageStart"), source="epg")
            for b in epg_entry.get("broadcasters", [])
        ]

        # ── HTML scraper entries ───────────────────────────────────
        html_entries = []
        uk_scraped = uk_html.get(key, {})
        tvg_scraped = tvguide.get(key, {})
        cov_start = tvg_scraped.get("coverage_start_utc")

        if competition == "EPL":
            if not uk_blackout:
                uk_bc = fx.get("uk_broadcaster") or uk_scraped.get("uk_broadcaster")
                uk_ch = fx.get("uk_channels",[]) or uk_scraped.get("uk_channels",[])
                if uk_bc == "Sky Sports":
                    ch = " · ".join(uk_ch) if uk_ch else "Sky Sports Main Event · Sky Sports Premier League"
                    html_entries.append(make_entry("Sky Sports","United Kingdom",ch,coverage_start=cov_start,source="html"))
                    html_entries.append(make_entry("BBC Sport","United Kingdom","BBC One · BBC iPlayer (MOTD)",highlights_only=True,source="html"))
                elif uk_bc == "TNT Sports":
                    ch = " · ".join(uk_ch) if uk_ch else "TNT Sports 1 · TNT Sports Ultimate · HBO Max"
                    html_entries.append(make_entry("TNT Sports","United Kingdom",ch,coverage_start=cov_start,source="html"))
                    html_entries.append(make_entry("BBC Sport","United Kingdom","BBC One · BBC iPlayer (MOTD)",highlights_only=True,source="html"))
            # US EPL
            ud = us_epl_data.get(key,{})
            html_entries.append(make_entry("NBC Sports / Peacock","United States",ud.get("us_channels","NBC / USA Network / Peacock"),source="html"))
        elif competition == "UCL":
            # UK UCL
            ucl_ch = " · ".join(uk_scraped.get("uk_channels",[])) or "TNT Sports 1 / TNT Sports 2"
            html_entries.append(make_entry("TNT Sports","United Kingdom",ucl_ch,coverage_start=cov_start,source="html"))
            html_entries.append(make_entry("Amazon Prime Video","United Kingdom","Amazon Prime Video",source="html"))
            html_entries.append(make_entry("BBC Sport","United Kingdom","BBC One · BBC iPlayer",highlights_only=True,source="html"))
            # US UCL
            ud = us_ucl_data.get(key,{})
            html_entries.append(make_entry("CBS Sports / Paramount+","United States",ud.get("us_channels","Paramount+"),source="html"))

        # Africa + Astro from HTML
        africa_d = africa_data.get(key,{})
        africa_ch = africa_d.get("africa_channel_display",
            "SuperSport Premier League (DStv #203)" if competition=="EPL" else "SuperSport Football (DStv #205)")
        html_entries.append(make_entry("SuperSport","Sub-Saharan Africa",africa_ch,source="html"))
        astro_d = astro_data.get(key,{})
        html_entries.append(make_entry("Astro","Malaysia",astro_d.get("astro_channel","Astro SuperSport 3"),source="html"))

        # ── Rights DB fallback ────────────────────────────────────
        rights_entries = []
        skip = {"United Kingdom","Republic of Ireland","United States",
                "Sub-Saharan Africa","Middle East & North Africa","Malaysia"}
        for country, entries in get_rights(competition).items():
            if country in skip: continue
            for e in entries:
                ch = e["name"] if is_streaming_service(e["name"]) else e.get("default_channels",e["name"])
                rights_entries.append(make_entry(e["name"],country,ch,highlights_only=e.get("highlights_only",False),source="rights_db"))

        # Ireland
        if competition == "EPL" and uk_blackout:
            rights_entries.append(make_entry("Premier Sports","Republic of Ireland","Premier Sports 1",source="rights_db"))
        else:
            for e in get_rights(competition).get("Republic of Ireland",[]):
                ch = e["name"] if is_streaming_service(e["name"]) else e.get("default_channels",e["name"])
                rights_entries.append(make_entry(e["name"],"Republic of Ireland",ch,highlights_only=e.get("highlights_only",False),source="rights_db"))

        # beIN MENA (importance-ranked channel)
        rights_entries.append(make_entry("beIN Sports","Middle East & North Africa",bein_ch,source="bein_ranking"))

        # ── Merge layers and build fixture ────────────────────────
        merged = merge_layers(epg_entries, html_entries, rights_entries)

        epg_count = len(epg_entries)
        quality = "epg" if epg_count >= 3 else ("html" if len(html_entries) >= 2 else "rights_db")

        output_fixtures.append({
            "id":           fixture_id(competition, home, away, fx.get("kickoff_utc","")),
            "competition":  competition,
            "round":        fx.get("round", f"Matchday {fx.get('matchday','?')}"),
            "home":         home,
            "away":         away,
            "homeEmoji":    fx.get("homeEmoji","⚽"),
            "awayEmoji":    fx.get("awayEmoji","⚽"),
            "date":         fx.get("date",""),
            "kickoff_utc":  fx.get("kickoff_utc",""),
            "venue":        fx.get("venue",""),
            "uk_blackout":  uk_blackout,
            "note":         fx.get("note",""),
            "data_quality": quality,
            "broadcasters": merged,
        })

    output_fixtures.sort(key=lambda f: f.get("kickoff_utc",""))
    quality_counts = {}
    for fx in output_fixtures:
        q = fx.get("data_quality","unknown")
        quality_counts[q] = quality_counts.get(q,0) + 1

    logger.info(f"Complete: {len(output_fixtures)} fixtures. Quality: {quality_counts}")

    output = {
        "generated":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days":   DAYS_AHEAD,
        "fixture_count": len(output_fixtures),
        "competitions":  ["EPL","UCL"],
        "data_quality":  quality_counts,
        "data_sources": {
            "primary_epg": [
                "Sky EPG API (Sky Sports + TNT Sports 1-6)",
                "dp247/Freeview-EPG (BBC, ITV)",
                "epg.pw (beIN, SuperSport, Canal+, Viaplay, DAZN, Astro, Stan Sport)",
            ],
            "supplementary_html": [
                "live-footballontv.com","tvguide.co.uk",
                "nbcsports.com (US EPL)","cbssports.com (US UCL)",
                "thesportsdb.com (SuperSport backup)","content.astro.com.my (Astro backup)",
            ],
            "rights_fallback": ["Broadcast_rights_updated_08-04-26.xlsx"],
        },
        "fixtures": output_fixtures,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path,"w",encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Written to {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    path = run()
    with open(path) as f:
        data = json.load(f)
    print(f"\n✅ Done → {path}")
    print(f"Fixtures: {data['fixture_count']}  Quality: {data['data_quality']}")
    print("\nSources:")
    for cat, srcs in data["data_sources"].items():
        print(f"  {cat}:")
        for s in srcs: print(f"    · {s}")
