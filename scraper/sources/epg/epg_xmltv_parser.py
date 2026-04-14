"""
epg_xmltv_parser.py
Parses the XMLTV guide.xml from iptv-org/epg and maps programmes to fixtures.
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# Map XMLTV channel IDs → broadcaster name + specific channel name
CHANNEL_ID_TO_BROADCASTER = {
    # UK — sky.com
    "SkySportsMainEvent.uk":     ("Sky Sports", "Sky Sports Main Event"),
    "SkySportsPremierLeague.uk": ("Sky Sports", "Sky Sports Premier League"),
    "SkySportsFootball.uk":      ("Sky Sports", "Sky Sports Football"),
    "SkySportsAction.uk":        ("Sky Sports", "Sky Sports Action"),
    "SkySportsArena.uk":         ("Sky Sports", "Sky Sports Arena"),
    "TNTSports1.uk":             ("TNT Sports", "TNT Sports 1"),
    "TNTSports2.uk":             ("TNT Sports", "TNT Sports 2"),
    "TNTSports3.uk":             ("TNT Sports", "TNT Sports 3"),
    "TNTSports4.uk":             ("TNT Sports", "TNT Sports 4"),
    # France/MENA — canalplus.com
    "beINSports1.qa":            ("beIN Sports", "beIN Sports 1"),
    "beINSports2.qa":            ("beIN Sports", "beIN Sports 2"),
    "beINSportsMax1.qa":         ("beIN Sports", "beIN Sports Max 1"),
    "beINSportsMax2.qa":         ("beIN Sports", "beIN Sports Max 2"),
    "beINSportsMax3.qa":         ("beIN Sports", "beIN Sports Max 3"),
    "CanalPlusSport.fr":         ("CANAL+", "Canal+ Sport"),
    "CanalPlusFoot.fr":          ("CANAL+", "Canal+ Foot"),
    # Germany — sky.de
    "SkySport1.de":              ("Sky Deutschland", "Sky Sport 1"),
    "SkySport2.de":              ("Sky Deutschland", "Sky Sport 2"),
    "SkySportBundesliga1.de":    ("Sky Deutschland", "Sky Sport Bundesliga 1"),
    "DAZN1.de":                  ("DAZN", "DAZN 1"),
    "DAZN2.de":                  ("DAZN", "DAZN 2"),
}

FOOTBALL_KEYWORDS = [
    "premier league", "champions league", "bundesliga", "la liga", "serie a",
    "ligue 1", "eredivisie", "championship", "fa cup", "football", "soccer",
    "calcio", "fussball", "futbol", "futebol", "efl", "spfl",
]

TEAM_ALIASES = {
    "man united": "manchester united", "man utd": "manchester united",
    "man city": "manchester city", "spurs": "tottenham",
    "tottenham hotspur": "tottenham", "arsenal fc": "arsenal",
    "chelsea fc": "chelsea", "liverpool fc": "liverpool",
    "brighton & hove albion": "brighton", "wolverhampton wanderers": "wolves",
    "wolverhampton": "wolves", "west ham united": "west ham",
    "nottingham forest": "nottm forest", "afc bournemouth": "bournemouth",
    "leicester city": "leicester", "bayer 04 leverkusen": "bayer leverkusen",
    "fc barcelona": "barcelona", "real madrid cf": "real madrid",
    "atletico de madrid": "atletico madrid",
    "club atletico de madrid": "atletico madrid",
    "paris saint-germain": "psg", "paris saint germain": "psg",
    "fc bayern munchen": "bayern munich", "fc bayern münchen": "bayern munich",
    "southampton fc": "southampton", "blackburn rovers fc": "blackburn rovers",
    "blackburn rovers": "blackburn", "sheffield united": "sheffield utd",
    "sheffield wednesday": "sheffield wed", "queens park rangers": "qpr",
    "huddersfield town": "huddersfield", "stoke city": "stoke",
    "birmingham city": "birmingham", "cardiff city": "cardiff",
    "swansea city": "swansea", "coventry city": "coventry",
    "preston north end": "preston", "west bromwich albion": "west brom",
    "millwall fc": "millwall", "watford fc": "watford",
    "norwich city": "norwich", "bristol city": "bristol city",
}


def _normalise_team(name: str) -> str:
    n = name.lower().strip()
    # Remove common suffixes
    n = re.sub(r'\s+(fc|afc|f\.c\.|a\.f\.c\.)$', '', n).strip()
    return TEAM_ALIASES.get(n, n)


def _match_channel_id(ch_id: str):
    """Match a channel ID against our known channels — handles suffix variations."""
    # Try exact match first
    if ch_id in CHANNEL_ID_TO_BROADCASTER:
        return CHANNEL_ID_TO_BROADCASTER[ch_id]
    # Try prefix match (channel IDs often have @HD, @SD suffixes)
    for key, val in CHANNEL_ID_TO_BROADCASTER.items():
        if ch_id.startswith(key) or key in ch_id:
            return val
    return None


def _parse_start_time(start_str: str):
    try:
        parts = start_str.strip().split()
        dt_str = parts[0]
        tz_str = parts[1] if len(parts) > 1 else "+0000"
        dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
        sign = 1 if tz_str[0] == "+" else -1
        tz_hours = int(tz_str[1:3])
        tz_mins = int(tz_str[3:5])
        offset = timedelta(hours=tz_hours, minutes=tz_mins) * sign
        return (dt - offset).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_teams_from_title(title: str):
    """Extract home/away teams from EPG title. Handles many formats."""
    # Strip competition prefix e.g. "Sky Sports PL: ", "EFL: ", "UCL: "
    cleaned = re.sub(r'^[A-Za-z0-9\s]+:\s*', '', title).strip()
    if not cleaned:
        cleaned = title

    # Pattern: "Team A v Team B" or "Team A vs Team B"
    for pattern in [
        r'^(.{3,40}?)\s+v\.?\s+(.{3,40})$',
        r'^(.{3,40}?)\s+vs\.?\s+(.{3,40})$',
        r'^(.{3,40}?)\s+v\s+(.{3,40})',
    ]:
        m = re.search(pattern, cleaned, re.IGNORECASE)
        if m:
            h = m.group(1).strip().rstrip('-').strip()
            a = m.group(2).strip().lstrip('-').strip()
            # Filter out obvious non-team strings
            if len(h) >= 3 and len(a) >= 3:
                return h, a
    return None


def _fuzzy_match_fixture(epg_home: str, epg_away: str, fixtures: list, epg_dt=None):
    """Match EPG teams to a fixture. Returns fixture_id or None."""
    epg_h = _normalise_team(epg_home)
    epg_a = _normalise_team(epg_away)

    best_id = None
    best_score = 0

    for f in fixtures:
        fix_h = _normalise_team(f.get("home_team", ""))
        fix_a = _normalise_team(f.get("away_team", ""))

        # Score the match
        score = 0
        # Exact match
        if epg_h == fix_h: score += 3
        if epg_a == fix_a: score += 3
        # Substring match
        if epg_h and fix_h and (epg_h in fix_h or fix_h in epg_h): score += 2
        if epg_a and fix_a and (epg_a in fix_a or fix_a in epg_a): score += 2
        # First 5 chars match
        if epg_h[:5] == fix_h[:5] and len(epg_h) >= 5: score += 1
        if epg_a[:5] == fix_a[:5] and len(epg_a) >= 5: score += 1
        # Time match bonus (if both within 30 mins of each other)
        if epg_dt and f.get("kickoff"):
            try:
                fix_dt = datetime.fromisoformat(f["kickoff"].replace("Z", "+00:00"))
                diff = abs((epg_dt - fix_dt).total_seconds())
                if diff < 1800:  # within 30 mins
                    score += 2
            except Exception:
                pass

        if score >= 4 and score > best_score:
            best_score = score
            best_id = f["id"]

    return best_id


def parse_guide(guide_xml: str, fixtures: list = None, days_ahead: int = 3) -> dict:
    """
    Parse guide.xml → { fixture_id: { broadcaster: channel_name } }
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

    # Map channel IDs
    channel_map = {}
    for ch in root.findall("channel"):
        ch_id = ch.get("id", "")
        match = _match_channel_id(ch_id)
        if match:
            channel_map[ch_id] = {
                "broadcaster": match[0],
                "channel_name": match[1],
            }

    logger.info(f"[epg_parser] Mapped {len(channel_map)} channels from guide.xml")

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    result = {}
    matched = 0
    total_football = 0
    sample_titles = []  # Log sample titles for debugging

    for prog in root.findall("programme"):
        ch_id = prog.get("channel", "")
        if ch_id not in channel_map:
            continue

        title_el = prog.find("title")
        if title_el is None:
            continue
        title = title_el.text or ""

        title_lower = title.lower()
        is_football = any(kw in title_lower for kw in FOOTBALL_KEYWORDS)
        if not is_football:
            continue

        start_str = prog.get("start", "")
        start_dt = _parse_start_time(start_str)
        if not start_dt or start_dt < now or start_dt > cutoff:
            continue

        total_football += 1

        # Collect sample titles for debugging (first 20)
        if len(sample_titles) < 20:
            sample_titles.append(f"  [{channel_map[ch_id]['channel_name']}] {title}")

        ch_info = channel_map[ch_id]
        broadcaster = ch_info["broadcaster"]
        channel_name = ch_info["channel_name"]

        if fixtures:
            teams = _extract_teams_from_title(title)
            if teams:
                fixture_id = _fuzzy_match_fixture(teams[0], teams[1], fixtures, start_dt)
                if fixture_id:
                    if fixture_id not in result:
                        result[fixture_id] = {}
                    if broadcaster not in result[fixture_id]:
                        result[fixture_id][broadcaster] = channel_name
                        matched += 1

    # Log sample titles so we can see what EPG is returning
    if sample_titles:
        logger.info(f"[epg_parser] Sample football programme titles from EPG:")
        for t in sample_titles:
            logger.info(t)
    else:
        logger.warning("[epg_parser] No football programmes found in mapped channels")

    logger.info(f"[epg_parser] {total_football} football programmes found, {matched} matched to fixtures")
    return result
