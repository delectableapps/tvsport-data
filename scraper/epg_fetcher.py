"""
epg_fetcher.py — EPGshare01 integration for TVsport
=====================================================
Downloads and parses EPG XML feeds from epgshare01.online to provide
match-level broadcaster data for fixtures worldwide.

3-tier confidence system:
    Tier 1 — EPG confirmed:  exact channel verified from schedule data  → confidence: "high",   source: "epg"
    Tier 2 — Rights known:   broadcaster from rights_db, no EPG file   → confidence: "medium", source: "rights"
    Tier 3 — Generic rights: broadcaster name only, no schedule detail  → confidence: "low",    source: "rights_db_generic"

Usage:
    from epg_fetcher import EPGFetcher
    fetcher = EPGFetcher()
    fetcher.fetch_all()   # downloads + parses all feeds
    result = fetcher.lookup(home="Liverpool", away="Crystal Palace", kickoff_utc="2026-04-25T13:30:00Z")
    # returns { "Republic of Ireland": { "channels": ["Premier Sports 1 HD Ireland"], "broadcaster": "Premier Sports", "confidence": "high", "source": "epg" }, ... }
"""

import gzip
import io
import logging
import os
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — EPGshare01 feed URLs and territory mappings
# ─────────────────────────────────────────────────────────────────────────────

EPGSHARE_BASE = "https://epgshare01.online/epgshare01"

# Maps EPG file key → list of territories it covers
# Each entry: (file_key, [territories], region_label)
EPG_FEED_MAP = [
    ("UK1",   ["United Kingdom"],                                    "Europe"),
    ("IE1",   ["Republic of Ireland"],                               "Europe"),
    ("US2",   ["United States"],                                     "Americas"),
    ("AU1",   ["Australia"],                                         "Asia-Pacific"),
    ("DE1",   ["Germany"],                                           "Europe"),
    ("IT1",   ["Italy"],                                             "Europe"),
    ("FR1",   ["France"],                                            "Europe"),
    ("IN1",   ["India"],                                             "Asia-Pacific"),
    ("MY1",   ["Malaysia"],                                          "Asia-Pacific"),
    ("SG1",   ["Singapore"],                                         "Asia-Pacific"),
    ("NL1",   ["Netherlands"],                                       "Europe"),
    ("PT1",   ["Portugal"],                                          "Europe"),
    ("TR1",   ["Turkey"],                                            "Europe"),
    ("NO1",   ["Norway"],                                            "Europe"),
    ("SE1",   ["Sweden"],                                            "Europe"),
    ("DK1",   ["Denmark"],                                           "Europe"),
    ("CA2",   ["Canada"],                                            "Americas"),
    ("NZ1",   ["New Zealand"],                                       "Asia-Pacific"),
    ("BEIN1", ["Qatar", "Saudi Arabia", "UAE", "Kuwait", "Bahrain",
               "Oman", "Jordan", "Lebanon", "Iraq", "Egypt",
               "Libya", "Tunisia", "Algeria", "Morocco"],            "Middle East & N. Africa"),
    ("ZA1",   ["South Africa", "Nigeria", "Ghana", "Kenya",
               "Tanzania", "Uganda", "Zimbabwe", "Zambia",
               "Botswana", "Namibia"],                               "Sub-Saharan Africa"),
    ("GR1",   ["Greece"],                                            "Europe"),
    ("PL1",   ["Poland"],                                            "Europe"),
    ("BE2",   ["Belgium"],                                           "Europe"),
    ("HU1",   ["Hungary"],                                           "Europe"),
    ("RO1",   ["Romania"],                                           "Europe"),
    ("HR1",   ["Croatia"],                                           "Europe"),
    ("HK1",   ["Hong Kong"],                                         "Asia-Pacific"),
    ("KR1",   ["South Korea"],                                       "Asia-Pacific"),
    ("JP1",   ["Japan"],                                             "Asia-Pacific"),
    ("BR1",   ["Brazil"],                                            "Americas"),
]

# Channel ID prefix → broadcaster name mapping (for EPG channel ID normalisation)
# Used to map EPG channel IDs like "Sky.Sports.Premier.League.HD.ie" → "Sky Sports"
CHANNEL_ID_TO_BROADCASTER = {
    # Ireland
    "Premier.Sports.1":           "Premier Sports",
    "Premier.Sports.2":           "Premier Sports",
    "Sky.Sports.Premier.League":  "Sky Sports",
    "Sky.Sports.Main.Event":      "Sky Sports",
    "Sky.Sports.Football":        "Sky Sports",
    "Sky.Sports.Action":          "Sky Sports",
    "TNT.Sports":                 "TNT Sports",
    # UK
    "SkySp.PL":                   "Sky Sports",
    "SkySpMainEv":                "Sky Sports",
    "SkySp.Fball":                "Sky Sports",
    "SkySp.Action":               "Sky Sports",
    "Sky.Sports.Football":        "Sky Sports",
    "TNT.Sports":                 "TNT Sports",
    "Premier.Sports":             "Premier Sports",
    # USA
    "NBC":                        "NBC Sports / Peacock",
    "Peacock":                    "NBC Sports / Peacock",
    "USA.Network":                "NBC Sports / Peacock",
    "NBCSN":                      "NBC Sports / Peacock",
    # Australia
    "Optus":                      "Optus Sport",
    "Fox.Sports":                 "Fox Sports Australia",
    "Stan":                       "Stan Sport",
    # Germany
    "Sky.Sport":                  "Sky Deutschland",
    "DAZN":                       "DAZN",
    # Italy
    "Sky.Sport.IT":               "Sky Italia",
    "Sky.Calcio":                 "Sky Italia",
    # France
    "Canal.Plus":                 "CANAL+",
    "Canal+":                     "CANAL+",
    # India
    "Star.Sports":                "JioStar",
    "JioStar":                    "JioStar",
    "Hotstar":                    "JioStar",
    # Malaysia
    "Astro.SuperSport":           "Astro",
    "Astro":                      "Astro",
    # Singapore
    "StarHub":                    "StarHub",
    "Hub.Premier":                "Hub (Singapore)",
    "Hub.Sports":                 "Hub (Singapore)",
    "Hub":                        "Hub (Singapore)",
    "beIN.Sports":                "beIN Sports",
    # Netherlands
    "Ziggo.Sport":                "Ziggo Sport",
    "Viaplay":                    "Viaplay",
    # beIN
    "beIN_SPORTS":                "beIN Sports",
    "beIN.SPORTS":                "beIN Sports",
    # SuperSport / Africa
    "SS.Premier.League":          "SuperSport",
    "SuperSport":                 "SuperSport",
    "TNT.Africa":                 "TNT Sports Africa",
}

# Football keywords that identify a programme as a live football match
LIVE_KEYWORDS = {"live:", "live ", "premier league", "champions league",
                 "europa league", "fa cup", "efl", "bundesliga", "serie a",
                 "ligue 1", "la liga", "eredivisie", "primeira liga",
                 "scottish", "championship", "league one", "league two"}

# Cache directory for downloaded XML files
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".epg_cache")
CACHE_MAX_AGE_HOURS = 20  # Re-download if older than this


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_team(name: str) -> str:
    """Normalise team name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in (" fc", " cf", " afc", " utd", " united", " city", " town",
                   " hotspur", " athletic", " wanderers", " rovers", " albion"):
        name = name.replace(suffix, "")
    # Remove punctuation
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name.strip()


def _teams_match(epg_subtitle: str, home: str, away: str) -> bool:
    """
    Check if an EPG sub-title matches a fixture's home/away teams.
    EPG format is typically "Liverpool v Crystal Palace" or "Liverpool vs Crystal Palace"
    """
    if not epg_subtitle:
        return False
    sub = epg_subtitle.lower()
    # Split on " v " or " vs "
    parts = re.split(r"\s+vs?\s+", sub)
    if len(parts) != 2:
        return False
    epg_home = _normalise_team(parts[0])
    epg_away = _normalise_team(parts[1])
    fix_home = _normalise_team(home)
    fix_away = _normalise_team(away)
    # Both must match (either order)
    forward = (fix_home in epg_home or epg_home in fix_home) and \
              (fix_away in epg_away or epg_away in fix_away)
    reverse = (fix_away in epg_home or epg_home in fix_away) and \
              (fix_home in epg_away or epg_away in fix_home)
    return forward or reverse


def _parse_epg_time(ts: str) -> datetime | None:
    """Parse EPGshare timestamp format: '20260425133000 +0000'"""
    try:
        # Strip offset, parse base
        base = ts.split()[0]
        dt = datetime.strptime(base, "%Y%m%d%H%M%S")
        # Handle offset
        if "+" in ts or (ts.count("-") > 2):
            offset_str = ts.split()[-1] if len(ts.split()) > 1 else "+0000"
            sign = 1 if "+" in offset_str else -1
            offset_str = offset_str.replace("+", "").replace("-", "")
            oh, om = int(offset_str[:2]), int(offset_str[2:])
            dt = dt - timedelta(hours=sign*oh, minutes=sign*om)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_live_programme(title: str) -> bool:
    """Check if a programme title indicates a live match (not highlights/repeat)."""
    t = title.lower()
    return t.startswith("live:") or t.startswith("live ")


def _channel_id_to_display(channel_id: str) -> str:
    """
    Convert EPG channel ID to human-readable display name.
    Preserves meaningful territory context (Ireland, UK etc.)

    Examples:
        Premier.Sports.1.HD.ie  → Premier Sports 1 HD Ireland
        Premier.Sports.2.ie     → Premier Sports 2 Ireland
        Sky.Sports.PL.HD.uk     → Sky Sports PL HD
        SkySp.PL.HD.uk          → Sky Sports Premier League HD
        TNT.Sports.1.HD.ie      → TNT Sports 1 HD Ireland
        beIN_SPORTS1.bein       → beIN Sports 1
        SS.Premier.League.za    → SuperSport Premier League
    """
    # Territory suffix → display label
    TERRITORY_LABELS = {
        ".ie": " Ireland",
        ".uk": "",           # UK channels don't need suffix
        ".bein": "",
        ".za": "",
        ".us": "",
        ".au": "",
        ".de": "",
        ".it": "",
        ".fr": "",
        ".in": "",
        ".my": "",
        ".sg": "",
        ".nl": "",
        ".pt": "",
        ".tr": "",
        ".no": "",
        ".se": "",
        ".dk": "",
        ".ca": " Canada",
        ".nz": "",
        ".gr": "",
        ".pl": "",
        ".be": "",
        ".hu": "",
        ".ro": "",
        ".hr": "",
        ".hk": "",
        ".kr": "",
        ".jp": "",
        ".br": "",
    }

    territory_label = ""
    working = channel_id

    # Check for territory suffix and extract label
    for suffix, label in TERRITORY_LABELS.items():
        # Handle both .ie and .HD.ie patterns
        if working.lower().endswith(suffix) or f"{suffix}@" in working.lower():
            territory_label = label
            # Remove the suffix (and anything after @)
            working = re.sub(re.escape(suffix) + r'(@.*)?$', '', working, flags=re.IGNORECASE)
            break

    # Known channel ID → clean name mappings
    KNOWN_IDS = {
        "premier.sports.1.hd":    "Premier Sports 1 HD",
        "premier.sports.1":       "Premier Sports 1",
        "premier.sports.2.hd":    "Premier Sports 2 HD",
        "premier.sports.2":       "Premier Sports 2",
        "sky.sports.premier.league.hd": "Sky Sports Premier League HD",
        "sky.sports.premier.league":    "Sky Sports Premier League",
        "sky.sports.main.event.hd":     "Sky Sports Main Event HD",
        "sky.sports.main.event":        "Sky Sports Main Event",
        "sky.sports.football.hd":       "Sky Sports Football HD",
        "sky.sports.football":          "Sky Sports Football",
        "sky.sports.action.hd":         "Sky Sports Action HD",
        "sky.sports.action":            "Sky Sports Action",
        "skysp.pl.hd":                  "Sky Sports Premier League HD",
        "skysp.pl":                     "Sky Sports Premier League",
        "skyspmainev hd":               "Sky Sports Main Event HD",
        "skyspmainevhd":                "Sky Sports Main Event HD",
        "skysp.fball.hd":               "Sky Sports Football HD",
        "skysp.fball":                  "Sky Sports Football",
        "skysp.actionhd":               "Sky Sports Action HD",
        "skysp.action":                 "Sky Sports Action",
        "tnt.sports.1.hd":              "TNT Sports 1 HD",
        "tnt.sports.1":                 "TNT Sports 1",
        "tnt.sports.2.hd":              "TNT Sports 2 HD",
        "tnt.sports.2":                 "TNT Sports 2",
        "tnt.sports.3.hd":              "TNT Sports 3 HD",
        "tnt.sports.3":                 "TNT Sports 3",
        "tnt.sports.4.hd":              "TNT Sports 4 HD",
        "tnt.sports.4":                 "TNT Sports 4",
        "ss.premier.league":            "SuperSport Premier League",
        "supersport.premier.league":    "SuperSport Premier League",
        "hub.premier.1":                "Hub Premier 1",
        "hub.premier.2":                "Hub Premier 2",
        "hub.premier.3":                "Hub Premier 3",
        "hub.premier.4":                "Hub Premier 4",
        "hub.sports.1":                 "Hub Sports 1",
        "hub.sports.2":                 "Hub Sports 2",
        "bein_sports1":                 "beIN Sports 1",
        "bein_sports2":                 "beIN Sports 2",
        "bein_sports3":                 "beIN Sports 3",
        "bein_sports4":                 "beIN Sports 4",
        "bein_sports5":                 "beIN Sports 5",
    }

    lower = working.lower()
    if lower in KNOWN_IDS:
        return KNOWN_IDS[lower] + territory_label

    # Generic fallback: replace dots/underscores with spaces, title case
    name = re.sub(r"[._]", " ", working).strip()
    name = re.sub(r"\s+", " ", name)
    # Title case but preserve known acronyms
    words = []
    for w in name.split():
        if w.upper() in ("HD", "SD", "TV", "FC", "BBC", "ITV", "ESPN", "NBC", "NFL", "NBA", "NHL"):
            words.append(w.upper())
        else:
            words.append(w.title())
    return " ".join(words) + territory_label


def _get_broadcaster_from_channel_id(channel_id: str) -> str:
    """Best-effort broadcaster name from channel ID."""
    cid_upper = channel_id.upper()
    for prefix, broadcaster in CHANNEL_ID_TO_BROADCASTER.items():
        if prefix.upper() in cid_upper:
            return broadcaster
    # Fallback: use first part of channel ID
    parts = channel_id.split(".")
    if parts:
        return parts[0].replace("_", " ").title()
    return channel_id


# ─────────────────────────────────────────────────────────────────────────────
# CORE FETCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class EPGFetcher:
    """
    Downloads, caches, and parses EPGshare01 feeds.
    Provides fixture-level broadcaster lookup.
    """

    def __init__(self, cache_dir: str = CACHE_DIR, max_age_hours: int = CACHE_MAX_AGE_HOURS):
        self.cache_dir = cache_dir
        self.max_age_hours = max_age_hours
        os.makedirs(cache_dir, exist_ok=True)

        # Main data store:
        # { feed_key: { channel_id: [ {start, stop, title, subtitle, desc, is_live} ] } }
        self._feed_data: dict = {}

        # Channel → territory mapping built from feed map
        # { feed_key: [territories] }
        self._feed_territories: dict = {
            entry[0]: entry[1] for entry in EPG_FEED_MAP
        }

    # ── Download & Cache ──────────────────────────────────────────────────────

    def _cache_path(self, feed_key: str) -> str:
        return os.path.join(self.cache_dir, f"epg_{feed_key}.xml")

    def _is_cache_fresh(self, feed_key: str) -> bool:
        path = self._cache_path(feed_key)
        if not os.path.isfile(path):
            return False
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        return age_hours < self.max_age_hours

    def _download_feed(self, feed_key: str) -> bool:
        """Download and decompress a feed. Returns True on success."""
        url = f"{EPGSHARE_BASE}/epg_ripper_{feed_key}.xml.gz"
        cache_path = self._cache_path(feed_key)
        try:
            logger.info(f"[epg] Downloading {feed_key} from {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "TVsport/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                compressed = resp.read()
            # Decompress
            with gzip.open(io.BytesIO(compressed)) as gz:
                xml_bytes = gz.read()
            with open(cache_path, "wb") as f:
                f.write(xml_bytes)
            logger.info(f"[epg] {feed_key}: downloaded {len(xml_bytes):,} bytes")
            return True
        except Exception as e:
            logger.warning(f"[epg] {feed_key}: download failed — {e}")
            return False

    # ── Parse ─────────────────────────────────────────────────────────────────

    def _parse_feed(self, feed_key: str) -> dict:
        """
        Parse a cached XML file.
        Returns { channel_id: [ programme_dict, ... ] }
        """
        cache_path = self._cache_path(feed_key)
        if not os.path.isfile(cache_path):
            return {}

        programmes: dict = {}
        try:
            tree = ET.parse(cache_path)
            root = tree.getroot()

            for prog in root.iter("programme"):
                channel = prog.get("channel", "")
                start_str = prog.get("start", "")
                stop_str = prog.get("stop", "")

                start_dt = _parse_epg_time(start_str)
                stop_dt  = _parse_epg_time(stop_str)

                # Extract title, sub-title, description
                title = ""
                subtitle = ""
                desc = ""
                for child in prog:
                    if child.tag == "title" and not title:
                        title = (child.text or "").strip()
                    elif child.tag == "sub-title" and not subtitle:
                        subtitle = (child.text or "").strip()
                    elif child.tag == "desc" and not desc:
                        desc = (child.text or "").strip()

                if not channel or not start_dt:
                    continue

                # Only store programmes that could be football
                combined = (title + " " + subtitle + " " + desc).lower()
                if not any(kw in combined for kw in LIVE_KEYWORDS):
                    continue

                entry = {
                    "start":    start_dt,
                    "stop":     stop_dt,
                    "title":    title,
                    "subtitle": subtitle,
                    "desc":     desc,
                    "is_live":  _is_live_programme(title),
                }

                programmes.setdefault(channel, []).append(entry)

        except Exception as e:
            logger.warning(f"[epg] {feed_key}: parse error — {e}")

        channel_count = len(programmes)
        prog_count = sum(len(v) for v in programmes.values())
        logger.info(f"[epg] {feed_key}: parsed {prog_count} football programmes across {channel_count} channels")
        return programmes

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_all(self, force: bool = False) -> None:
        """Download and parse all configured EPG feeds."""
        logger.info(f"[epg] Starting EPG fetch ({len(EPG_FEED_MAP)} feeds)")
        success = 0
        for feed_key, territories, _ in EPG_FEED_MAP:
            if force or not self._is_cache_fresh(feed_key):
                ok = self._download_feed(feed_key)
                if not ok:
                    continue
            else:
                logger.info(f"[epg] {feed_key}: using cached file")

            data = self._parse_feed(feed_key)
            if data:
                self._feed_data[feed_key] = data
                success += 1

        logger.info(f"[epg] Fetch complete: {success}/{len(EPG_FEED_MAP)} feeds loaded")

    def fetch_selective(self, feed_keys: list, force: bool = False) -> None:
        """Download and parse a specific subset of feeds."""
        for feed_key in feed_keys:
            # Find territories for this key
            territories = self._feed_territories.get(feed_key, [])
            if not territories:
                logger.warning(f"[epg] Unknown feed key: {feed_key}")
                continue
            if force or not self._is_cache_fresh(feed_key):
                ok = self._download_feed(feed_key)
                if not ok:
                    continue
            data = self._parse_feed(feed_key)
            if data:
                self._feed_data[feed_key] = data

    def lookup(self, home: str, away: str, kickoff_utc: str) -> dict:
        """
        Look up broadcaster data for a specific fixture across all loaded feeds.

        Args:
            home:         Home team name (e.g. "Liverpool")
            away:         Away team name (e.g. "Crystal Palace")
            kickoff_utc:  ISO kickoff time (e.g. "2026-04-25T13:30:00Z")

        Returns:
            {
                "Republic of Ireland": {
                    "broadcaster":  "Premier Sports",
                    "channels":     ["Premier Sports 1 HD Ireland"],
                    "channel_ids":  ["Premier.Sports.1.HD.ie"],
                    "is_live":      True,
                    "confidence":   "high",
                    "source":       "epg",
                    "start":        "2026-04-25T13:30:00Z",
                },
                ...
            }
        """
        try:
            kickoff_dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        except Exception:
            logger.warning(f"[epg] Invalid kickoff: {kickoff_utc}")
            return {}

        # Search window: kickoff ±3 hours (handles pre-show, slight time differences)
        window_start = kickoff_dt - timedelta(hours=1)
        window_end   = kickoff_dt + timedelta(hours=3)

        results = {}

        for feed_key, feed_programmes in self._feed_data.items():
            territories = self._feed_territories.get(feed_key, [])
            if not territories:
                continue

            # Find matching programmes in this feed
            matched_channels = []  # [ (channel_id, programme_entry) ]

            for channel_id, programmes in feed_programmes.items():
                for prog in programmes:
                    prog_start = prog["start"]
                    if not prog_start:
                        continue
                    # Must be within window
                    if not (window_start <= prog_start <= window_end):
                        continue
                    # Must match teams
                    if not _teams_match(prog["subtitle"], home, away):
                        # Also try matching against title
                        if not _teams_match(prog["title"], home, away):
                            continue
                    matched_channels.append((channel_id, prog))

            if not matched_channels:
                continue

            # Group matched channels by territory
            # For multi-territory feeds (BEIN1, ZA1), assign all to each territory
            for territory in territories:
                # Collect unique channels, prefer live over non-live
                live_channels = [(cid, p) for cid, p in matched_channels if p["is_live"]]
                any_channels  = matched_channels

                best = live_channels if live_channels else any_channels

                # Deduplicate channel IDs
                seen_cids = set()
                unique = []
                for cid, prog in best:
                    if cid not in seen_cids:
                        seen_cids.add(cid)
                        unique.append((cid, prog))

                channel_ids    = [cid for cid, _ in unique]
                display_names  = [_channel_id_to_display(cid) for cid in channel_ids]
                broadcaster    = _get_broadcaster_from_channel_id(channel_ids[0]) if channel_ids else ""
                is_live        = any(p["is_live"] for _, p in unique)
                best_prog      = unique[0][1] if unique else {}

                results[territory] = {
                    "broadcaster":  broadcaster,
                    "channels":     display_names,
                    "channel_ids":  channel_ids,
                    "is_live":      is_live,
                    "confidence":   "high",
                    "source":       "epg",
                    "start":        best_prog.get("start", kickoff_dt).strftime("%Y-%m-%dT%H:%M:%SZ") if best_prog.get("start") else kickoff_utc,
                }

                logger.debug(f"[epg] {territory}: {broadcaster} — {channel_ids} (live={is_live})")

        return results

    def lookup_all_fixtures(self, fixtures: list) -> dict:
        """
        Batch lookup for all fixtures.

        Args:
            fixtures: list of fixture dicts with keys: id, home_team, away_team, kickoff

        Returns:
            { fixture_id: { territory: broadcaster_data } }
        """
        results = {}
        matched = 0

        for fixture in fixtures:
            fid     = fixture.get("id", "")
            home    = fixture.get("home_team", "")
            away    = fixture.get("away_team", "")
            kickoff = fixture.get("kickoff", "")

            if not all([fid, home, away, kickoff]):
                continue

            epg_result = self.lookup(home, away, kickoff)
            if epg_result:
                results[fid] = epg_result
                matched += 1

        logger.info(f"[epg] Batch lookup: {matched}/{len(fixtures)} fixtures matched in EPG")
        return results

    def get_loaded_feeds(self) -> list:
        """Return list of successfully loaded feed keys."""
        return list(self._feed_data.keys())

    def get_stats(self) -> dict:
        """Return stats about loaded feed data."""
        stats = {}
        for feed_key, data in self._feed_data.items():
            total_progs = sum(len(v) for v in data.values())
            stats[feed_key] = {
                "channels": len(data),
                "programmes": total_progs,
                "territories": self._feed_territories.get(feed_key, []),
            }
        return stats
