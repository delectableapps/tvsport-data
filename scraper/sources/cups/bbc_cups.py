"""
bbc_cups.py
-----------
Scrapes cup fixtures from BBC Sport's per-competition fixture pages.

URL pattern (verified live, April 2026)
---------------------------------------

BBC publishes fixtures at:

    https://www.bbc.co.uk/sport/football/{slug}/scores-fixtures
    https://www.bbc.co.uk/sport/football/{slug}/scores-fixtures/YYYY-MM

Where {slug} is the competition slug. The bare URL shows the current
month; appending YYYY-MM lets us walk forwards through future months.
We hit one URL per (cup, month) pair across a 3-month rolling window.

Per-competition URLs are the right choice over per-day URLs in the
current BBC layout: the per-day pattern only exists for "all sports
on this date" pages and routes through a different rendering path
that doesn't carry per-competition fixture context.

HTML structure (current as of 2026)
-----------------------------------

BBC has migrated to styled-components, so class names look like::

    ssrcss-1pj9vd3-StyledTeam-HomeTeam eirdlos1
                  ↑                    ↑
                  semantic suffix      hash (changes per release)

The hash prefix is volatile across deploys, so all selectors in this
file use **substring matching on the semantic suffix**, never the full
class name. This is the only reliable strategy.

Page structure for one fixture::

    <h2 class="ssrcss-...-GroupHeader">Sunday 26th April</h2>
    <h3 class="ssrcss-...-SecondaryHeading">Semi-finals</h3>
    <ul>
      <li class="ssrcss-...-HeadToHeadWrapper">
        <div class="ssrcss-...-StyledHeadToHead">
          <div class="ssrcss-...-WithInlineFallback-TeamHome">
            <div class="ssrcss-...-StyledTeam-HomeTeam">
              <div class="ssrcss-...-TeamNameWrapper">
                <span class="...-MobileValue">Chelsea</span>      ← shown on mobile
                <span class="...-DesktopValue">Chelsea</span>     ← shown on desktop
                <span class="visually-hidden">Chelsea</span>      ← canonical, screen-reader
              </div>
              <div data-testid="badge-container-chelsea">...</div> ← team slug
            </div>
          </div>

          <div class="ssrcss-...-WithInlineFallback-Scores">
            <time class="ssrcss-...-StyledTime">15:00</time>      ← upcoming match
            OR
            <span ...>3 - 1</span>                                ← played match
          </div>

          <div class="ssrcss-...-WithInlineFallback-TeamAway">
            ...same nesting as home...
          </div>
        </div>
      </li>
      ... more <li> wrappers if more fixtures on this date ...
    </ul>

Team-name extraction
--------------------

The TeamNameWrapper holds three repeats of the name (mobile abbrev,
desktop full, visually-hidden full). The visually-hidden span carries
the canonical full name in every case, so we always read from that.
If it's missing for any reason, we fall back to the data-testid badge
slug (e.g. ``badge-container-leeds-united`` → "Leeds United").

Score / time
------------

A scheduled fixture has a `<time>` element inside the Scores wrapper.
A played fixture replaces the time with score numbers. We parse both
shapes and let the orchestrator decide which view wins per source.

Dependencies: requests + beautifulsoup4 + lxml. No Playwright needed —
BBC serves fully rendered HTML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

from ._common import (
    CUPS, CupMeta, Match,
    find_cup_by_name,
    make_kickoff_utc, parse_date, parse_score, parse_time,
)

log = logging.getLogger(__name__)


BBC_BASE_URL  = "https://www.bbc.co.uk/sport/football/{slug}/scores-fixtures"
BBC_MONTH_URL = "https://www.bbc.co.uk/sport/football/{slug}/scores-fixtures/{year:04d}-{month:02d}"

# How many months ahead to scan (including the current one). 3 covers a
# typical FA Cup round-to-round gap and the EFL Cup's compressed schedule.
MONTHS_AHEAD = 3


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "tvsport.live scraper (+https://tvsport.live)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return s


def _fetch_html(session: requests.Session, url: str, timeout: float = 20.0) -> str | None:
    try:
        r = session.get(url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("bbc_cups: network error %s -> %s", url, e)
        return None
    if r.status_code == 404:
        log.debug("bbc_cups: 404 for %s", url)
        return None
    if r.status_code != 200:
        log.warning("bbc_cups: HTTP %s for %s", r.status_code, url)
        return None
    return r.text


# ---------------------------------------------------------------------------
# Month iteration
# ---------------------------------------------------------------------------

def _months_to_scan(today: datetime | None = None,
                    count: int = MONTHS_AHEAD) -> list[tuple[int, int]]:
    """Return a list of (year, month) pairs covering today's month and
    the next `count - 1` months."""
    today = today or datetime.now(timezone.utc)
    out: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(count):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ---------------------------------------------------------------------------
# HTML parsing — uses substring matching on ssrcss-* class semantic suffixes
# ---------------------------------------------------------------------------

def _has_class_substr(substr: str):
    """Build a BeautifulSoup class-matcher that looks for `substr` anywhere
    in any of the element's class names. Robust against BBC's volatile
    ssrcss-* hash prefixes."""
    def matcher(cls):
        if not cls:
            return False
        if isinstance(cls, list):
            return any(substr in c for c in cls)
        return substr in cls
    return matcher


_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bteam\s+to\s+be\s+confirmed\b", re.I),
    re.compile(r"\bto\s+be\s+confirmed\b", re.I),
    re.compile(r"^\s*(tbc|tbd)\s*$", re.I),
    # "Winner of match X vs Y" — bracket placeholder
    re.compile(r"\bwinner\s+of\b", re.I),
    re.compile(r"\bloser\s+of\b", re.I),
)


def _looks_like_placeholder(name: str) -> bool:
    """Return True if a team name is a bracket placeholder rather than a
    real club. BBC populates these for fixtures whose teams haven't been
    determined yet — keeping them would clutter output and break dedupe."""
    if not name:
        return True
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(name):
            return True
    return False


def _clean_team_name(team_div: Tag) -> str | None:
    """Pull the canonical team name from a HomeTeam / AwayTeam div.

    Strategy:
      1. Read the `visually-hidden` span — always carries the full name
      2. If absent, fall back to the badge-container data-testid slug
      3. If neither works, return None
    """
    if team_div is None:
        return None

    # Primary: the visually-hidden screen-reader span has the full name
    vh = team_div.find('span', class_=_has_class_substr('VisuallyHidden'))
    if vh is None:
        # Some pages use the literal class "visually-hidden" (no prefix)
        vh = team_div.find('span', class_=lambda c: c and 'visually-hidden' in (c if isinstance(c, str) else ' '.join(c)))
    if vh:
        text = vh.get_text(' ', strip=True)
        if text:
            return text

    # Fallback: the badge container data-testid encodes a slug like
    # "badge-container-leeds-united" — convert "leeds-united" -> "Leeds United".
    badge = team_div.find(attrs={'data-testid': lambda v: v and isinstance(v, str) and v.startswith('badge-container-')})
    if badge:
        slug = badge['data-testid'].replace('badge-container-', '')
        return slug.replace('-', ' ').title()

    return None


def _extract_score_or_time(scores_wrapper: Tag) -> tuple[str | None, list[int] | None, str]:
    """Inspect the Scores wrapper and return (time_local, score_ft, status).

    For a scheduled match: score_ft=None, time_local="HH:MM", status="scheduled"
    For a played match:    score_ft=[h, a], time_local=None, status="finished"
    For postponed/other:   all None, status reflecting what we could detect
    """
    if scores_wrapper is None:
        return (None, None, "scheduled")

    # Time first — a <time> element is the cleanest signal of an upcoming match.
    time_el = scores_wrapper.find('time')
    if time_el:
        # The <time> may have a datetime attribute too — prefer parsed text
        # since BBC's datetime attr is often the full ISO including timezone.
        time_text = time_el.get_text(' ', strip=True)
        time_local = parse_time(time_text)
        if time_local:
            return (time_local, None, "scheduled")

    # No <time>: look for a score pattern in the wrapper text. BBC renders
    # scores in their own spans; any "N-N" / "N - N" we find is a final score.
    full_text = scores_wrapper.get_text(' ', strip=True)
    if re.search(r'\bpostpon', full_text, re.I):
        return (None, None, "postponed")
    if re.search(r'\bcancel', full_text, re.I):
        return (None, None, "postponed")
    score = parse_score(full_text)
    if score:
        score_ft, status = score
        return (None, score_ft, status)
    # Fallback: looser score regex inside the noise
    score_m = re.search(r'\b(\d{1,2})\s*[\u2013\u2014\-]\s*(\d{1,2})\b', full_text)
    if score_m:
        return (None, [int(score_m.group(1)), int(score_m.group(2))], "finished")

    return (None, None, "scheduled")


def _nearest_date_for(node: Tag) -> str | None:
    """Walk backwards from a fixture <li> to find the nearest preceding
    GroupHeader heading whose text is a date like 'Sunday 26th April'."""
    cur = node
    for _ in range(60):
        cur = cur.find_previous(['h2', 'h3'])
        if cur is None:
            return None
        # Only trust GroupHeader-style date headings to avoid scraping a
        # date out of unrelated promo text.
        cls = cur.get('class') or []
        if any('GroupHeader' in c for c in cls):
            text = cur.get_text(' ', strip=True)
            date = parse_date(text)
            if date:
                return date
            # GroupHeader without a year — common on per-month pages where
            # the year is implicit. Append the current page's year/month
            # if we can find one in the URL pattern.
            return _augment_undated_heading(text)
    return None


def _nearest_round_for(node: Tag) -> str | None:
    """Walk backwards to find the nearest SecondaryHeading (e.g. 'Semi-finals')."""
    cur = node
    for _ in range(60):
        cur = cur.find_previous(['h2', 'h3', 'h4'])
        if cur is None:
            return None
        cls = cur.get('class') or []
        if any('SecondaryHeading' in c for c in cls):
            return cur.get_text(' ', strip=True)
    return None


# ---------------------------------------------------------------------------
# Year-augmentation helper for headings like "Sunday 26th April" (no year)
# ---------------------------------------------------------------------------

# This is set per-page-fetch via _parse_page so the date parser knows which
# year to attribute year-less headings to.
_PAGE_CONTEXT_YEAR: int | None = None
_PAGE_CONTEXT_MONTH: int | None = None


def _augment_undated_heading(text: str) -> str | None:
    """Try to parse a date from a heading that lacks a year.
    Uses the year/month context set by the current fetch."""
    if _PAGE_CONTEXT_YEAR is None:
        return None
    # Strip ordinals and try with the page's year appended.
    augmented = f"{text} {_PAGE_CONTEXT_YEAR}"
    return parse_date(augmented)


# ---------------------------------------------------------------------------
# Page parser
# ---------------------------------------------------------------------------

def _parse_page(html: str, cup: CupMeta,
                page_year: int | None = None,
                page_month: int | None = None) -> list[Match]:
    """Parse one BBC competition+month page into Match objects."""
    global _PAGE_CONTEXT_YEAR, _PAGE_CONTEXT_MONTH
    _PAGE_CONTEXT_YEAR  = page_year
    _PAGE_CONTEXT_MONTH = page_month

    soup = BeautifulSoup(html, 'lxml')

    fixture_lis = soup.find_all('li', class_=_has_class_substr('HeadToHeadWrapper'))
    if not fixture_lis:
        log.debug("bbc_cups: no fixture wrappers found for %s", cup.code)
        return []

    matches: list[Match] = []
    for li in fixture_lis:
        # Date and round from preceding headings
        date = _nearest_date_for(li)
        if not date:
            log.debug("bbc_cups: skipping fixture with no date — %s",
                      li.get_text(' ', strip=True)[:60])
            continue
        round_label = _nearest_round_for(li)

        # Team divs
        home_div = li.find('div', class_=_has_class_substr('Team-HomeTeam'))
        away_div = li.find('div', class_=_has_class_substr('Team-AwayTeam'))
        home = _clean_team_name(home_div)
        away = _clean_team_name(away_div)
        if not home or not away:
            log.debug("bbc_cups: skipping fixture with missing teams (%s vs %s)",
                      home, away)
            continue

        # Skip placeholder fixtures where the teams aren't confirmed yet
        # (e.g. "Team to be confirmed" / "TBC" appears in unfilled brackets).
        # These aren't real fixtures and would create noise in dedupe.
        if _looks_like_placeholder(home) or _looks_like_placeholder(away):
            log.debug("bbc_cups: skipping placeholder fixture (%s vs %s)",
                      home, away)
            continue

        # Time / score
        scores_wrapper = li.find('div', class_=_has_class_substr('WithInlineFallback-Scores'))
        time_local, score_ft, status = _extract_score_or_time(scores_wrapper)

        kickoff_utc = make_kickoff_utc(date, time_local) if status == "scheduled" else None

        matches.append(Match(
            competition_code=cup.code,
            competition_name=cup.name,
            country=cup.country,
            round_label=round_label,
            kickoff_utc=kickoff_utc,
            date=date,
            time_local=time_local,
            home=home,
            away=away,
            status=status,
            score_ft=score_ft,
            source="bbc",
            raw={"li_html": str(li)[:400]},
        ))

    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_cup(cup: CupMeta, session: requests.Session | None = None,
              months: list[tuple[int, int]] | None = None) -> list[Match]:
    """Fetch every per-month page for one cup and merge results.
    Deduplicates by (date, home, away) — same fixture can show up on
    multiple per-month pages near a month boundary."""
    if not cup.bbc_slug:
        return []
    s = session or _session()
    months = months or _months_to_scan()

    seen: set[tuple[str, str, str]] = set()
    all_matches: list[Match] = []
    for year, month in months:
        url = BBC_MONTH_URL.format(slug=cup.bbc_slug, year=year, month=month)
        log.info("bbc_cups: fetching %s %04d-%02d (%s)", cup.code, year, month, url)
        html = _fetch_html(s, url)
        if not html:
            continue
        for m in _parse_page(html, cup, page_year=year, page_month=month):
            key = (m.date, m.home.lower(), m.away.lower())
            if key in seen:
                continue
            seen.add(key)
            all_matches.append(m)
    log.info("bbc_cups: %s -> %d matches across %d months",
             cup.code, len(all_matches), len(months))
    return all_matches


def fetch_all(cups: Iterable[CupMeta] | None = None,
              months: list[tuple[int, int]] | None = None) -> list[Match]:
    cups = tuple(cups) if cups is not None else CUPS
    s = _session()
    out: list[Match] = []
    for cup in cups:
        out.extend(fetch_cup(cup, session=s, months=months))
    log.info("bbc_cups: total %d matches across %d cups", len(out), len(cups))
    return out


# ---------------------------------------------------------------------------
# CLI / offline test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Scrape BBC Sport for cup fixtures")
    ap.add_argument("--cup", help="Cup code (FAC/EFLC/SFAC/SLFC)")
    ap.add_argument("--month", help="Single month YYYY-MM (default: 3 months ahead)")
    ap.add_argument("--html-file", help="Parse a local saved page for offline testing")
    ap.add_argument("--year", type=int, default=None,
                    help="Year context for --html-file (for headings missing year)")
    ap.add_argument("--month-num", type=int, default=None,
                    help="Month context for --html-file")
    ap.add_argument("--out", help="Write matches as JSON")
    args = ap.parse_args()

    if args.html_file:
        cup_code = args.cup or "FAC"
        chosen = next((c for c in CUPS if c.code == cup_code), None)
        if not chosen:
            raise SystemExit(f"Unknown --cup code: {cup_code}")
        with open(args.html_file, "r", encoding="utf-8") as fh:
            html = fh.read()
        matches = _parse_page(html, chosen,
                              page_year=args.year, page_month=args.month_num)
    elif args.month:
        cup_code = args.cup or "FAC"
        chosen = next((c for c in CUPS if c.code == cup_code), None)
        if not chosen:
            raise SystemExit(f"Unknown --cup code: {cup_code}")
        y, m = args.month.split("-")
        matches = fetch_cup(chosen, months=[(int(y), int(m))])
    else:
        cups = CUPS
        if args.cup:
            cups = tuple(c for c in CUPS if c.code == args.cup)
            if not cups:
                raise SystemExit(f"Unknown cup code {args.cup!r}")
        matches = fetch_all(cups=cups)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            _json.dump([m.to_dict() for m in matches], fh, indent=2, ensure_ascii=False)
        print(f"Wrote {len(matches)} matches to {args.out}")
    else:
        for m in matches[:40]:
            print(f"{m.date} {m.time_local or 'TBC':5s}  {m.competition_code:5s}  "
                  f"{(m.round_label or '?')[:18]:18s}  "
                  f"{m.home} vs {m.away}  [{m.status}]")
        if len(matches) > 40:
            print(f"... and {len(matches) - 40} more")
