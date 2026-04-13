"""
fixtures_spfl.py
Scrapes Scottish Premiership and Championship fixtures.
Uses multiple selector patterns to handle SPFL site structure.
"""

import logging
import requests
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

COMPETITIONS = {
    "SP1": {"name": "Scottish Premiership",  "code": "SP1", "url": "https://spfl.co.uk/league/premier-league/fixtures"},
    "SC1": {"name": "Scottish Championship", "code": "SC1", "url": "https://spfl.co.uk/league/championship/fixtures"},
}


def _make_fixture(home, away, date_str, comp_info):
    date_slug = date_str[:10] if len(date_str) >= 10 else "unknown"
    return {
        "id":          f"{comp_info['code'].lower()}_{home[:3].upper()}_{away[:3].upper()}_{date_slug}",
        "competition": comp_info["name"],
        "comp_code":   comp_info["code"],
        "home_team":   home,
        "away_team":   away,
        "kickoff":     date_str,
        "matchday":    None,
        "stage":       "REGULAR_SEASON",
        "group":       None,
        "source":      "spfl.co.uk",
    }


def _parse(html, comp_info):
    fixtures = []
    soup = BeautifulSoup(html, "html.parser")

    # Try structured selectors first
    for selector in [".fixture", ".match", "[class*='fixture']", "[class*='match']", "tr", "li"]:
        blocks = soup.select(selector)
        for block in blocks:
            text = block.get_text(" ", strip=True)
            m = re.search(r'([A-Z][a-zA-Z\s&]{2,25})\s+(?:v|vs\.?)\s+([A-Z][a-zA-Z\s&]{2,25})', text)
            if m:
                home, away = m.group(1).strip(), m.group(2).strip()
                date_m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text)
                date_str = date_m.group(0) if date_m else ""
                if len(home) > 2 and len(away) > 2:
                    fixtures.append(_make_fixture(home, away, date_str, comp_info))
        if fixtures:
            return _dedup(fixtures)

    # Fallback: scan all lines
    for line in soup.get_text("\n").split("\n"):
        line = line.strip()
        m = re.search(r'^([A-Z][a-zA-Z\s&]{2,25})\s+(?:v|vs\.?)\s+([A-Z][a-zA-Z\s&]{2,25})$', line)
        if m:
            home, away = m.group(1).strip(), m.group(2).strip()
            skip = ["fixture", "result", "match", "round", "league", "cup", "table"]
            if not any(s in home.lower() for s in skip):
                fixtures.append(_make_fixture(home, away, "", comp_info))

    return _dedup(fixtures)


def _dedup(fixtures):
    seen, out = set(), []
    for f in fixtures:
        k = (f["home_team"].lower(), f["away_team"].lower())
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def scrape_fixtures():
    all_fixtures = []
    for key, comp_info in COMPETITIONS.items():
        try:
            logger.info(f"[spfl] Fetching {comp_info['name']}...")
            resp = requests.get(comp_info["url"], headers=HEADERS, timeout=20)
            resp.raise_for_status()
            fixtures = _parse(resp.text, comp_info)
            logger.info(f"[spfl] {comp_info['name']}: {len(fixtures)} fixtures")
            all_fixtures.extend(fixtures)
        except Exception as e:
            logger.error(f"[spfl] Failed {comp_info['name']}: {e}")
    return all_fixtures
