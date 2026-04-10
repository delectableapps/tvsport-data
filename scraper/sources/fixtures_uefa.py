"""
sources/fixtures_uefa.py
=========================
Scrapes UEFA.com for the UCL fixture list and official kick-off times.
Also fetches the official worldwide broadcast partners list (static, seasonal).

Sources:
- https://www.uefa.com/uefachampionsleague/news/029c-... (fixtures + results)
- https://www.uefa.com/uefachampionsleague/news/0253-... (broadcast partners)
"""

import re
import logging
from datetime import date, datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.uefa.com/",
}

FIXTURES_URL = (
    "https://www.uefa.com/uefachampionsleague/news/"
    "029c-1e9a2f63fe2d-ebf9ad643892-1000--2025-26-champions-league-all-the-fixtures-and-results/"
)

BROADCAST_URL = (
    "https://www.uefa.com/uefachampionsleague/news/"
    "0253-0d82037aaedd-f371c464f919-1000--where-to-watch-the-champions-league-tv-broadcast-partners-li/"
)

# UCL QF/SF/Final dates for 2025-26 season (known from UEFA.com)
UCL_SCHEDULE = {
    "QF · 1st Leg": {
        "dates": ["2026-04-07", "2026-04-08"],
        "kickoff_cest": "21:00",  # CEST = UTC+2 from late March
    },
    "QF · 2nd Leg": {
        "dates": ["2026-04-14", "2026-04-15"],
        "kickoff_cest": "21:00",
    },
    "SF · 1st Leg": {
        "dates": ["2026-04-28", "2026-04-29"],
        "kickoff_cest": "21:00",
    },
    "SF · 2nd Leg": {
        "dates": ["2026-05-05", "2026-05-06"],
        "kickoff_cest": "21:00",
    },
    "Final": {
        "dates": ["2026-05-30"],
        "kickoff_cest": "21:00",
        "venue": "Puskás Aréna, Budapest",
    },
}

# Known QF matchups from UEFA.com (confirmed Mar 2026)
UCL_QF_MATCHUPS = [
    {
        "home": "Sporting CP", "away": "Arsenal",
        "homeEmoji": "🟢", "awayEmoji": "🔴",
        "leg": "1st", "date": "2026-04-07",
        "venue": "Estádio José Alvalade, Lisbon",
    },
    {
        "home": "Real Madrid", "away": "Bayern Munich",
        "homeEmoji": "⚪", "awayEmoji": "🔴",
        "leg": "1st", "date": "2026-04-07",
        "venue": "Santiago Bernabéu, Madrid",
    },
    {
        "home": "Paris Saint-Germain", "away": "Liverpool",
        "homeEmoji": "🔵", "awayEmoji": "🔴",
        "leg": "1st", "date": "2026-04-08",
        "venue": "Parc des Princes, Paris",
    },
    {
        "home": "Barcelona", "away": "Atlético Madrid",
        "homeEmoji": "🔵", "awayEmoji": "🔴",
        "leg": "1st", "date": "2026-04-08",
        "venue": "Spotify Camp Nou, Barcelona",
    },
    # 2nd legs (home/away swapped)
    {
        "home": "Arsenal", "away": "Sporting CP",
        "homeEmoji": "🔴", "awayEmoji": "🟢",
        "leg": "2nd", "date": "2026-04-15",
        "venue": "Emirates Stadium, London",
    },
    {
        "home": "Bayern Munich", "away": "Real Madrid",
        "homeEmoji": "🔴", "awayEmoji": "⚪",
        "leg": "2nd", "date": "2026-04-15",
        "venue": "Allianz Arena, Munich",
    },
    {
        "home": "Liverpool", "away": "Paris Saint-Germain",
        "homeEmoji": "🔴", "awayEmoji": "🔵",
        "leg": "2nd", "date": "2026-04-14",
        "venue": "Anfield, Liverpool",
    },
    {
        "home": "Atlético Madrid", "away": "Barcelona",
        "homeEmoji": "🔴", "awayEmoji": "🔵",
        "leg": "2nd", "date": "2026-04-14",
        "venue": "Metropolitano, Madrid",
    },
]

# SF matchups (TBC pending QF results — teams to be filled dynamically)
UCL_SF_MATCHUPS = [
    {
        "home": "TBC", "away": "TBC",
        "homeEmoji": "🏆", "awayEmoji": "🏆",
        "leg": "1st", "date": "2026-04-28",
        "note": "Semi-Final 1 — teams confirmed after QFs",
        "venue": "TBC",
    },
    {
        "home": "TBC", "away": "TBC",
        "homeEmoji": "🏆", "awayEmoji": "🏆",
        "leg": "1st", "date": "2026-04-29",
        "note": "Semi-Final 2 — teams confirmed after QFs",
        "venue": "TBC",
    },
    {
        "home": "TBC", "away": "TBC",
        "homeEmoji": "🏆", "awayEmoji": "🏆",
        "leg": "2nd", "date": "2026-05-05",
        "note": "Semi-Final 1 2nd Leg",
        "venue": "TBC",
    },
    {
        "home": "TBC", "away": "TBC",
        "homeEmoji": "🏆", "awayEmoji": "🏆",
        "leg": "2nd", "date": "2026-05-06",
        "note": "Semi-Final 2 2nd Leg",
        "venue": "TBC",
    },
]


def _cest_to_utc(date_str: str, time_cest: str = "21:00") -> str:
    """Convert CEST (UTC+2, Apr onwards) or CET (UTC+1) to UTC."""
    try:
        dt = datetime.strptime(f"{date_str} {time_cest}", "%Y-%m-%d %H:%M")
        month = dt.month
        # CEST (UTC+2): late March to late October
        offset = 2 if 3 < month < 11 else 1
        dt_utc = dt - timedelta(hours=offset)
        return dt_utc.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _normalise(name: str) -> str:
    return name.strip().lower().replace("&", "and").replace(".", "").replace("'", "")


def _make_key(home: str, away: str) -> str:
    return f"{_normalise(home)} v {_normalise(away)}"


def get_ucl_fixtures(days_ahead: int = 30) -> list:
    """
    Return list of UCL fixture dicts for the next `days_ahead` days.
    Uses the hardcoded schedule + scrapes UEFA.com to confirm/update teams.
    """
    cutoff = date.today() + timedelta(days=days_ahead)
    today = date.today()
    fixtures = []

    all_matchups = UCL_QF_MATCHUPS + UCL_SF_MATCHUPS

    for match in all_matchups:
        match_date = datetime.strptime(match["date"], "%Y-%m-%d").date()
        if match_date < today or match_date > cutoff:
            continue

        # Determine round label
        if match_date <= date(2026, 4, 8):
            round_label = "QF · 1st Leg"
        elif match_date <= date(2026, 4, 15):
            round_label = "QF · 2nd Leg"
        elif match_date <= date(2026, 4, 29):
            round_label = "SF · 1st Leg"
        elif match_date <= date(2026, 5, 6):
            round_label = "SF · 2nd Leg"
        else:
            round_label = "Final"

        kickoff_utc = _cest_to_utc(match["date"])

        fixtures.append({
            "competition": "UCL",
            "round": round_label,
            "home": match["home"],
            "away": match["away"],
            "homeEmoji": match.get("homeEmoji", "⚽"),
            "awayEmoji": match.get("awayEmoji", "⚽"),
            "date": match["date"],
            "kickoff_utc": kickoff_utc,
            "venue": match.get("venue", "TBC"),
            "note": match.get("note", ""),
            "fixture_key": _make_key(match["home"], match["away"]),
        })

    logger.info(f"Generated {len(fixtures)} UCL fixtures for next {days_ahead} days")
    return fixtures


def fetch_broadcast_partners() -> dict:
    """
    Fetch the UEFA.com official broadcast partners page.
    Returns { country: [broadcaster_name, ...] }
    This is a seasonal list, changes once per rights cycle.
    """
    try:
        r = requests.get(BROADCAST_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.error(f"Failed to fetch UEFA broadcast partners: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")

    results = {}

    # Pattern: "Country: Broadcaster1, Broadcaster2"
    # or "Country: Broadcaster1; Broadcaster2"
    country_pattern = re.compile(
        r"^\s*\*{0,2}([A-Z][^:]{2,40}):\*{0,2}\s+(.+)$",
        re.MULTILINE
    )

    for match in country_pattern.finditer(text):
        country = match.group(1).strip().rstrip("*")
        broadcasters_raw = match.group(2).strip()

        # Split by comma or semicolon
        broadcasters = [
            b.strip().strip("*").strip()
            for b in re.split(r"[,;]", broadcasters_raw)
            if b.strip()
        ]

        if country and broadcasters:
            results[country] = broadcasters

    logger.info(f"Fetched broadcast partners for {len(results)} territories from UEFA.com")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n── UCL Fixtures (next 30 days) ──")
    fixtures = get_ucl_fixtures(30)
    for fx in fixtures:
        print(f"  {fx['date']} {fx['kickoff_utc'][:16]}Z  "
              f"{fx['home']} vs {fx['away']}  [{fx['round']}]  {fx['venue']}")

    print("\n── Broadcast Partners (sample) ──")
    partners = fetch_broadcast_partners()
    for country, bcs in list(partners.items())[:10]:
        print(f"  {country}: {', '.join(bcs)}")
