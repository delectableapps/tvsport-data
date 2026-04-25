"""
bbc_cups.py
-----------
Scrapes cup fixtures from BBC Sport's date-indexed football pages.

URL pattern
-----------

Two parallel pages serve UK football fixtures on BBC Sport:

    https://www.bbc.co.uk/sport/football/scores-fixtures/YYYY-MM-DD
    https://www.bbc.co.uk/sport/football/scottish/scores-fixtures/YYYY-MM-DD

Each page lists every competition with a fixture on that date, grouped
by competition heading ("FA Cup", "Carabao Cup", "Scottish Cup", etc.).

We fetch each date in a rolling 30-day window, parse both the English
and Scottish feeds, and filter each page's content down to the four
cups we care about. Because the BBC already groups fixtures by
competition heading, our filter is a straightforward "does this group's
heading match one of our cup aliases?".

Why per-day rather than per-competition
---------------------------------------

BBC does have per-competition landing pages (e.g. /sport/football/fa-cup)
but they're JS-hydrated and require a headless browser. The per-day
pages are fully server-rendered HTML that loads cleanly with requests.

Parsing strategy
----------------

BBC Sport renders each day's fixtures in a structure like:

    <h3>FA Cup</h3>
    <ul class="gs-u-list-unstyled">
      <li>
        <div class="sp-c-fixture__...">
          <span class="sp-c-fixture__team-name">Manchester City</span>
          <span class="sp-c-fixture__number--home">3</span>
          <span class="sp-c-fixture__team-name">Exeter City</span>
          <span class="sp-c-fixture__number--away">1</span>
          ...
          <span class="sp-c-fixture__status">Full time</span>
          OR
          <span class="sp-c-fixture__block-time sp-c-fixture__time">15:00</span>
        </div>
      </li>
      ...
    </ul>

The exact class names have changed over time; BBC has used
`sp-c-fixture`, `gs-c-fixture`, and plainer `qa-...` data-test
selectors in different eras. We scan for several candidate selectors
and pick the first that yields parseable rows.

Dependencies
------------

requests + beautifulsoup4 + lxml. No Playwright needed for BBC.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

from ._common import (
    CUPS, CupMeta, Match,
    date_window, find_cup_by_name,
    make_kickoff_utc, parse_date, parse_score, parse_time,
)

log = logging.getLogger(__name__)


BBC_ENGLAND_URL = "https://www.bbc.co.uk/sport/football/scores-fixtures/{date}"
BBC_SCOTLAND_URL = "https://www.bbc.co.uk/sport/football/scottish/scores-fixtures/{date}"


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
# HTML parsing
# ---------------------------------------------------------------------------

# Selector candidates, tried in order. Each must return "fixture group"
# elements — a heading with its associated fixture list. The parser then
# extracts fixtures from within each group.
#
# These are deliberately generous: we match on substrings of class names
# rather than exact equality, because BBC mangles class names across
# redesigns but keeps the semantic roots ("fixture", "block", "team-name").
GROUP_HEADING_SELECTORS = (
    # Modern (2022+): each competition section has its own <h3>
    "h3",
    # Older BBC structure
    "h2.gs-c-promo-heading__title",
    # Fallback
    "header",
)


def _find_competition_groups(soup: BeautifulSoup) -> list[tuple[str, Tag]]:
    """Yield (competition_name, container) for each competition section
    on a BBC day page. The container is the element immediately following
    the heading that holds the fixture list.

    BBC's layout: heading immediately precedes a <ul> or <div> of fixtures.
    We walk siblings until we find the next heading or run out."""
    groups: list[tuple[str, Tag]] = []

    # Prefer explicit fixture-list containers when present
    for heading in soup.find_all(["h3", "h2"]):
        name = heading.get_text(" ", strip=True)
        if not name:
            continue
        # The heading should sit above fixture rows — find them by walking
        # forward through siblings until the next heading or a non-fixture
        # container. We collect everything in between into a pseudo-group.
        container = heading.find_next_sibling()
        if container is None:
            continue
        # If the next sibling is itself a fixture list, use it; otherwise
        # wrap the run of siblings up to the next heading in a SoupStrainer-
        # style wrapper.
        groups.append((name, container))

    return groups


def _text(element: Tag | None) -> str:
    if element is None:
        return ""
    return element.get_text(" ", strip=True)


def _parse_fixture_element(fix: Tag, date: str, cup: CupMeta,
                           round_label: str | None) -> Match | None:
    """Parse a single BBC fixture element (li or article-level block)."""
    # Home / away team names — BBC uses a class that contains "team-name"
    team_name_tags = fix.select("[class*='team-name']")
    if len(team_name_tags) < 2:
        # Fallback: BBC sometimes uses data-test attrs
        team_name_tags = fix.find_all(attrs={"data-testid": lambda v: v and "team" in v.lower()})
    if len(team_name_tags) < 2:
        return None

    home = _text(team_name_tags[0])
    away = _text(team_name_tags[1])
    if not home or not away:
        return None

    # Score — cells with "number" in the class. Two of them if the match
    # has been played, zero if upcoming.
    score_tags = fix.select("[class*='number']")
    score_ft: list[int] | None = None
    status = "scheduled"
    if len(score_tags) >= 2:
        try:
            home_goals = int(_text(score_tags[0]))
            away_goals = int(_text(score_tags[1]))
            score_ft = [home_goals, away_goals]
            status = "finished"
        except (ValueError, IndexError):
            pass

    # Time — a cell containing text like "15:00" or "Full time" / "Postponed"
    time_local = None
    status_text = ""
    # Prefer explicit status / time class substrings
    time_tag = fix.select_one("[class*='block-time'], [class*='fixture__time'], time")
    if time_tag:
        t = _text(time_tag)
        parsed = parse_time(t)
        if parsed:
            time_local = parsed

    status_tag = fix.select_one("[class*='status'], [class*='fixture__status']")
    if status_tag:
        status_text = _text(status_tag).lower()
        if "postponed" in status_text or "cancelled" in status_text:
            status = "postponed"
        elif "full time" in status_text or "ft" in status_text.split():
            # Already set via score, but confirm
            if score_ft is not None:
                status = "finished"

    # Final kickoff string
    kickoff_utc = make_kickoff_utc(date, time_local) if status == "scheduled" else None

    return Match(
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
        raw={"html_snippet": str(fix)[:400]},
    )


def _parse_day_page(html: str, date: str) -> list[Match]:
    soup = BeautifulSoup(html, "lxml")
    matches: list[Match] = []

    for comp_name, container in _find_competition_groups(soup):
        cup = find_cup_by_name(comp_name)
        if not cup:
            continue

        # Round label sometimes appears as a sub-heading inside the
        # container (e.g. "Third round proper"). Grab it if present.
        round_label = None
        sub = container.find(["h4", "h5"])
        if sub:
            round_label = _text(sub)

        # Fixture rows: BBC uses <li> items most commonly, but we also
        # look for article-level fixture blocks.
        fixture_elements: list[Tag] = []
        fixture_elements.extend(container.select("li"))
        fixture_elements.extend(container.select("[class*='fixture'][class*='block']"))
        # Deduplicate (order-preserving) — an <li> that also matches the
        # block-class selector would otherwise be parsed twice.
        seen_ids: set[int] = set()
        unique_elements: list[Tag] = []
        for el in fixture_elements:
            if id(el) in seen_ids:
                continue
            seen_ids.add(id(el))
            unique_elements.append(el)

        for fix in unique_elements:
            m = _parse_fixture_element(fix, date, cup, round_label)
            if m:
                matches.append(m)

    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_day(
    date: str,
    session: requests.Session | None = None,
) -> list[Match]:
    """Fetch both the English and Scottish BBC feeds for one date."""
    s = session or _session()
    out: list[Match] = []
    for tmpl in (BBC_ENGLAND_URL, BBC_SCOTLAND_URL):
        url = tmpl.format(date=date)
        html = _fetch_html(s, url)
        if html:
            found = _parse_day_page(html, date)
            log.debug("bbc_cups: %s -> %d cup matches from %s",
                      date, len(found), url)
            out.extend(found)
    return out


def fetch_all(
    days_ahead: int = 30,
    session: requests.Session | None = None,
) -> list[Match]:
    """Scan a rolling date window and collect every cup fixture found."""
    s = session or _session()
    dates = date_window(days_ahead=days_ahead)
    all_matches: list[Match] = []
    for date in dates:
        all_matches.extend(fetch_day(date, session=s))
    log.info("bbc_cups: %d cup matches across %d dates",
             len(all_matches), len(dates))
    return all_matches


# ---------------------------------------------------------------------------
# CLI / offline test mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Scrape BBC Sport for cup fixtures")
    ap.add_argument("--date", help="Single date YYYY-MM-DD (default: today onwards)")
    ap.add_argument("--days", type=int, default=30,
                    help="Days ahead to scan (default: 30)")
    ap.add_argument("--html-file",
                    help="Parse a locally saved BBC page for offline testing")
    ap.add_argument("--out", help="Write matches as JSON to this path")
    args = ap.parse_args()

    if args.html_file:
        date = args.date or "2026-01-10"
        with open(args.html_file, "r", encoding="utf-8") as fh:
            html = fh.read()
        matches = _parse_day_page(html, date)
    elif args.date:
        matches = fetch_day(args.date)
    else:
        matches = fetch_all(days_ahead=args.days)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            _json.dump([m.to_dict() for m in matches], fh, indent=2, ensure_ascii=False)
        print(f"Wrote {len(matches)} matches to {args.out}")
    else:
        for m in matches[:40]:
            print(f"{m.date} {m.time_local or 'TBC':5s}  {m.competition_code:5s}  "
                  f"{m.home} vs {m.away}  [{m.status}]")
        if len(matches) > 40:
            print(f"... and {len(matches) - 40} more")
