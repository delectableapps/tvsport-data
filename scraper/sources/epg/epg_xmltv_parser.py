"""
epg_xmltv_parser.py
Parses the XMLTV guide.xml output from iptv-org/epg and extracts
football match listings, mapping them to TVsport fixture IDs.

Returns: dict keyed by fixture_id → { broadcaster: channel_name }
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# Map XMLTV channel IDs (from epg_channels.xml xmltv_id) → broadcaster name
CHANNEL_ID_TO_BROADCASTER = {
    # UK — sky.com
    "SkySportsMainEvent.uk@HD":      "Sky Sports",
    "SkySportsPremierLeague.uk@HD":  "Sky Sports",
    "SkySportsFootball.uk@HD":       "Sky Sports",
    "SkySportsAction.uk@HD":         "Sky Sports",
    "TNTSports1.uk@HD":              "TNT Sports",
    "TNTSports2.uk@HD":              "TNT Sports",
    "TNTSports3.uk@HD":              "TNT Sports",
    "TNTSports4.uk@HD":              "TNT Sports",
    # France/MENA — canalplus.com
    "beINSports1.qa@France":         "beIN Sports",
    "beINSports2.qa@France":         "beIN Sports",
    "beINSportsMax1.qa@France":      "beIN Sports",
    "beINSportsMax2.qa@France":      "beIN Sports",
    "CanalPlusSport.fr@SD":          "CANAL+",
    "CanalPlusFoot.fr@SD":           "CANAL+",
    # Germany — sky.de
    "SkySport1.de@HD":               "Sky Deutschland",
    "SkySport2.de@HD":               "Sky Deutschland",
    "SkySportBundesliga1.de@HD":     "Sky Deutschland",
    "DAZN1.de@HD":                   "DAZN",
    "DAZN2.de@HD":                   "DAZN",
    # India — airtelxstream.in
    "StarSports1.in@HD":             "JioStar",
    "StarSports2.in@HD":             "JioStar",
    "StarSports3.in@SD":             "JioStar",
    "SonyTen1.in@HD":                "JioStar",
    "SonyTen2.in@HD":                "JioStar",
    "SonyTen3.in@HD":                "JioStar",
    "Sports18.in@HD":                "JioStar",
    # Malaysia — astro.com.my
    "AstroSupersport2.my@HD":        "Astro",
    "AstroSupersport3.my@HD":        "Astro",
    "AstroSupersport4.my@HD":        "Astro",
    # Africa — dstv.com
    "SuperSportPremierLeague.za@HD": "SuperSport",
    "SuperSportFootball.za@HD":      "SuperSport",
    "SuperSportVariety1.za@HD":      "SuperSport",
    "SuperSportVariety2.za@HD":      "SuperSport",
}

# Football keywords to identify sport programmes
FOOTBALL_KEYWORDS = [
    "premier league", "champions league", "bundesliga", "la liga", "serie a",
    "ligue 1", "eredivisie", "championship", "fa cup", "football", "soccer",
    "calcio", "fussball", "futbol", "futebol",
]

# Team name normalisation — common variations
TEAM_ALIASES = {
    "man united": "manchester united",
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "arsenal fc": "arsenal",
    "chelsea fc": "chelsea",
    "liverpool fc": "liverpool",
    "brighton & hove albion": "brighton",
    "wolverhampton": "wolves",
    "wolverhampton wanderers": "wolves",
    "west ham united": "west ham",
    "nottingham forest": "nottm forest",
    "afc bournemouth": "bournemouth",
    "leicester city": "leicester",
    "bayer 04 leverkusen": "bayer leverkusen",
    "fc barcelona": "barcelona",
    "real madrid cf": "real madrid",
    "atletico de madrid": "atletico madrid",
    "club atletico de madrid": "atletico madrid",
    "paris saint-germain": "psg",
    "paris saint germain": "psg",
    "fc bayern munchen": "bayern munich",
    "fc bayern münchen": "bayern munich",
}


def _normalise_team(name: str) -> str:
    """Normalise team name for fuzzy matching."""
    n = name.lower().strip()
    return TEAM_ALIASES.get(n, n)


def _parse_start_time(start_str: str) -> datetime | None:
    """Parse XMLTV start time format: '20260413200000 +0000'"""
    try:
        # Remove timezone offset, parse the base datetime
        parts = start_str.strip().split()
        dt_str = parts[0]
        tz_str = parts[1] if len(parts) > 1 else "+0000"

        dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")

        # Apply timezone offset
        sign = 1 if tz_str[0] == "+" else -1
        tz_hours = int(tz_str[1:3])
        tz_mins = int(tz_str[3:5])
        offset = timedelta(hours=tz_hours, minutes=tz_mins) * sign

        return (dt - offset).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_teams_from_title(title: str) -> tuple[str, str] | None:
    """
    Try to extract home and away team names from an EPG programme title.
    Common patterns: "Team A v Team B", "Team A vs Team B", "PL: Team A v Team B"
    """
    # Strip competition prefix (e.g. "Premier League: ", "UCL: ")
    title = re.sub(r'^[^:]+:\s*', '', title)

    # Match "Team A v/vs Team B"
    m = re.search(
        r'(.{3,35}?)\s+(?:v\.?s?\.?)\s+(.{3,35})',
        title, re.IGNORECASE
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def _fuzzy_match_fixture(epg_home: str, epg_away: str, fixtures: list) -> str | None:
    """
    Find the fixture ID that best matches the EPG team names.
    Returns fixture_id or None.
    """
    epg_h = _normalise_team(epg_home)
    epg_a = _normalise_team(epg_away)

    for f in fixtures:
        fix_h = _normalise_team(f.get("home_team", ""))
        fix_a = _normalise_team(f.get("away_team", ""))

        # Check if team names are substrings of each other (handles truncation)
        h_match = epg_h in fix_h or fix_h in epg_h or epg_h[:6] == fix_h[:6]
        a_match = epg_a in fix_a or fix_a in epg_a or epg_a[:6] == fix_a[:6]

        if h_match and a_match:
            return f["id"]

    return None


def parse_guide(guide_xml: str, fixtures: list = None, days_ahead: int = 3) -> dict:
    """
    Parse guide.xml and return a dict mapping:
        fixture_id → { broadcaster_name: specific_channel_name }

    If fixtures list is provided, attempts to match EPG entries to fixture IDs.
    """
    if not os.path.isfile(guide_xml):
        logger.warning(f"[epg_parser] guide.xml not found: {guide_xml}")
        return {}

    try:
        tree = ET.parse(guide_xml)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"[epg_parser] Failed to parse guide.xml: {e}")
        return {}

    # Build channel ID → broadcaster mapping from the XML
    channel_map = {}
    for ch in root.findall("channel"):
        ch_id = ch.get("id", "")
        # Try to match against our known IDs
        for xmltv_id, broadcaster in CHANNEL_ID_TO_BROADCASTER.items():
            if xmltv_id in ch_id or ch_id in xmltv_id:
                channel_map[ch_id] = {
                    "broadcaster": broadcaster,
                    "channel_name": ch.findtext("display-name", ch_id),
                }
                break

    logger.info(f"[epg_parser] Mapped {len(channel_map)} channels from guide.xml")

    # Time window
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    # Parse programmes
    result = {}  # fixture_id → { broadcaster: channel_name }
    matched = 0
    total_football = 0

    for prog in root.findall("programme"):
        ch_id = prog.get("channel", "")
        if ch_id not in channel_map:
            continue

        title_el = prog.find("title")
        if title_el is None:
            continue
        title = title_el.text or ""

        # Check if it's a football programme
        title_lower = title.lower()
        if not any(kw in title_lower for kw in FOOTBALL_KEYWORDS):
            continue

        # Parse start time
        start_str = prog.get("start", "")
        start_dt = _parse_start_time(start_str)
        if not start_dt:
            continue

        # Only within our window
        if start_dt < now or start_dt > cutoff:
            continue

        total_football += 1

        ch_info = channel_map[ch_id]
        broadcaster = ch_info["broadcaster"]
        channel_name = ch_info["channel_name"]

        # Try to match to a fixture
        if fixtures:
            teams = _extract_teams_from_title(title)
            if teams:
                fixture_id = _fuzzy_match_fixture(teams[0], teams[1], fixtures)
                if fixture_id:
                    if fixture_id not in result:
                        result[fixture_id] = {}
                    # Only update if we don't have this broadcaster yet
                    # (first match = most specific channel)
                    if broadcaster not in result[fixture_id]:
                        result[fixture_id][broadcaster] = channel_name
                        matched += 1

    logger.info(f"[epg_parser] {total_football} football programmes found, {matched} matched to fixtures")
    return result
