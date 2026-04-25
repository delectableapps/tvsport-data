"""
sky_cups.py
-----------
Scrapes cup fixtures from Sky Sports' per-competition fixture pages.

URL pattern
-----------

    https://www.skysports.com/{slug}-scores-fixtures
    https://www.skysports.com/{slug}-scores-fixtures/{YYYY-MM-DD}

Where {slug} is the competition slug:
    fa-cup
    carabao-cup     (EFL Cup)
    scottish-cup
    scottish-league-cup

Unlike BBC's one-URL-per-day pattern, Sky has a single "this month's
fixtures" page per competition that already lists dates ahead. We hit
the base URL once per cup and parse the multi-day list.

If the base URL doesn't expose enough of the date window, we also hit
a handful of dated URLs inside the window. In practice one base-URL
fetch per cup is plenty for upcoming fixtures.

Parsing strategy
----------------

Sky's fixture block structure (as of early 2026):

    <div class="fixres__item">
      <div class="fixres__header3">Saturday 10th January 2026</div>     (date)
      <div class="matches__item">
        <span class="matches__date">15:00</span>                         (kickoff)
        <span class="swap-text__target">Manchester City</span>           (home)
        <span class="matches__teamscores">...</span>
        <span class="swap-text__target">Exeter City</span>               (away)
      </div>
      ...
    </div>

As with BBC, class names have drifted across redesigns. We target
several candidate selectors; the first that yields parseable rows wins.

Sky pages are partially server-rendered: the fixture list is present
in HTML but some decoration may be JS-hydrated. We don't need the
decoration. If a fetch returns suspiciously thin HTML we trigger the
Playwright fallback.

Dependencies
------------

requests + beautifulsoup4 + lxml. Playwright optional.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

from ._common import (
    CUPS, CupMeta, Match,
    date_window, find_cup_by_name,
    make_kickoff_utc, parse_date, parse_score, parse_time,
)

log = logging.getLogger(__name__)


SKY_BASE_URL = "https://www.skysports.com/{slug}-scores-fixtures"
SKY_DATED_URL = "https://www.skysports.com/{slug}-scores-fixtures/{date}"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "tvsport.live scraper (+https://tvsport.live)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return s


def _fetch_html(session: requests.Session, url: str, timeout: float = 25.0) -> str | None:
    try:
        r = session.get(url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("sky_cups: network error %s -> %s", url, e)
        return None
    if r.status_code == 404:
        log.info("sky_cups: 404 for %s", url)
        return None
    if r.status_code != 200:
        log.warning("sky_cups: HTTP %s for %s", r.status_code, url)
        return None
    return r.text


def _playwright_fetch_html(url: str) -> str | None:
    """Used only when the static HTML returned by Sky doesn't contain any
    fixture blocks — suggests the page has gone fully JS-hydrated."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        log.info("sky_cups: playwright not installed, skipping fallback")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Give the hydrator a moment to run
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.warning("sky_cups: playwright failed for %s -> %s", url, e)
        return None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

# The "fixture item" candidates. Sky has used at least three different
# class-name schemes over the years; we try each in order.
FIXTURE_ITEM_SELECTORS = (
    "div.fixres__item",
    "div.matches__item",
    "div[class*='fixture'][class*='item']",
)

# The "date section" selector — each fixture item belongs to a dated
# section whose heading sits above the items.
DATE_HEADING_SELECTORS = (
    "h4.fixres__header2",
    "h3.fixres__header3",
    "div.fixres__header3",
    "h3[class*='date']",
    "h4[class*='date']",
)

# Team-name span candidates inside a fixture row.
TEAM_NAME_SELECTORS = (
    ".swap-text__target",
    ".matches__item-col.matches__participant .swap-text__target",
    "span[class*='participant']",
    "span[class*='team-name']",
)


def _text(element: Tag | None) -> str:
    if element is None:
        return ""
    return element.get_text(" ", strip=True)


def _find_fixture_items(soup: BeautifulSoup) -> list[Tag]:
    """Return every fixture row element on the page, in document order."""
    for selector in FIXTURE_ITEM_SELECTORS:
        items = soup.select(selector)
        if items:
            log.debug("sky_cups: using fixture selector %r (%d items)",
                      selector, len(items))
            return items
    return []


def _find_date_for(item: Tag) -> str | None:
    """Find the nearest preceding date heading for a fixture item.

    Sky's page puts a date heading above a run of fixtures for that date,
    then another heading above the next run. So we walk backwards through
    previous elements until we hit something that parses as a date."""
    # Walk previous siblings at the top level first, then widen.
    node: Tag | None = item
    for _ in range(100):  # generous safety bound
        node = node.find_previous(["h2", "h3", "h4", "h5", "div", "header"])
        if node is None:
            return None
        text = _text(node)
        if not text:
            continue
        # Only consider short-ish headings: a date heading is typically
        # "Saturday 10th January 2026" — under ~40 chars. This avoids
        # accidentally parsing a date out of prose elsewhere on the page.
        if len(text) > 60:
            continue
        date = parse_date(text)
        if date:
            return date
    return None


def _parse_fixture_item(item: Tag, cup: CupMeta) -> Match | None:
    date = _find_date_for(item)
    if not date:
        return None

    # Team names: grab all candidate team spans, keep first two.
    team_tags: list[Tag] = []
    for selector in TEAM_NAME_SELECTORS:
        team_tags = item.select(selector)
        if len(team_tags) >= 2:
            break
    if len(team_tags) < 2:
        return None
    home = _text(team_tags[0])
    away = _text(team_tags[1])
    if not home or not away:
        return None

    # Time / score — Sky displays one of:
    #    "15:00"                  (scheduled)
    #    "3 - 1"                  (finished)
    #    "AET"                    (finished after extra time)
    #    "Full time"
    all_text = item.get_text(" ", strip=True)

    time_local = parse_time(all_text)
    score_result = None

    # Score tends to live in dedicated class or near "teamscores"
    score_tag = item.select_one(
        "[class*='teamscores'], [class*='fixture__number'], "
        "[class*='score']"
    )
    if score_tag:
        score_text = _text(score_tag)
        parsed = parse_score(score_text)
        if parsed:
            score_result = parsed

    # Fallback: search full-row text for a "X - Y" pattern, but only
    # if the text looks finished (i.e. contains FT / Full time marker)
    if not score_result and re.search(r"\b(ft|full\s*time)\b", all_text, re.I):
        score_m = re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b", all_text)
        if score_m:
            score_result = ([int(score_m.group(1)), int(score_m.group(2))], "finished")

    status = "scheduled"
    score_ft = None
    if score_result:
        score_ft, status = score_result
        time_local = None  # don't show a kickoff time for finished matches
    elif re.search(r"postponed|cancel", all_text, re.I):
        status = "postponed"

    kickoff_utc = make_kickoff_utc(date, time_local) if status == "scheduled" else None

    return Match(
        competition_code=cup.code,
        competition_name=cup.name,
        country=cup.country,
        round_label=None,        # Sky doesn't label rounds in this view
        kickoff_utc=kickoff_utc,
        date=date,
        time_local=time_local,
        home=home,
        away=away,
        status=status,
        score_ft=score_ft,
        source="sky",
        raw={"html_snippet": str(item)[:400]},
    )


def _parse_cup_page(html: str, cup: CupMeta) -> list[Match]:
    soup = BeautifulSoup(html, "lxml")
    items = _find_fixture_items(soup)
    if not items:
        return []

    matches: list[Match] = []
    for item in items:
        m = _parse_fixture_item(item, cup)
        if m:
            matches.append(m)

    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_cup(
    cup: CupMeta,
    session: requests.Session | None = None,
) -> list[Match]:
    if not cup.sky_slug:
        return []
    s = session or _session()
    url = SKY_BASE_URL.format(slug=cup.sky_slug)
    log.info("sky_cups: fetching %s (%s)", cup.code, url)
    html = _fetch_html(s, url)
    if not html:
        return []

    matches = _parse_cup_page(html, cup)

    # If the page seems present but no fixtures parsed, try Playwright.
    # Heuristic: we expect at least the word "fixture" to appear in the HTML.
    if not matches and "fixture" in html.lower():
        log.info("sky_cups: static parse yielded 0; trying Playwright for %s", cup.code)
        html2 = _playwright_fetch_html(url)
        if html2:
            matches = _parse_cup_page(html2, cup)

    log.info("sky_cups: %s -> %d matches", cup.code, len(matches))
    return matches


def fetch_all(
    cups: Iterable[CupMeta] | None = None,
) -> list[Match]:
    cups = tuple(cups) if cups is not None else CUPS
    s = _session()
    all_matches: list[Match] = []
    for cup in cups:
        all_matches.extend(fetch_cup(cup, session=s))
    log.info("sky_cups: total %d matches across %d cups",
             len(all_matches), len(cups))
    return all_matches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Scrape Sky Sports for cup fixtures")
    ap.add_argument("--cup", help="One cup code (FAC/EFLC/SFAC/SLFC)")
    ap.add_argument("--html-file", help="Parse a local HTML file for offline testing")
    ap.add_argument("--out", help="Write matches as JSON")
    args = ap.parse_args()

    chosen = CUPS
    if args.cup:
        chosen = tuple(c for c in CUPS if c.code == args.cup)
        if not chosen:
            raise SystemExit(f"Unknown cup code {args.cup!r}")

    if args.html_file:
        cup = chosen[0] if chosen else CUPS[0]
        with open(args.html_file, "r", encoding="utf-8") as fh:
            html = fh.read()
        matches = _parse_cup_page(html, cup)
    else:
        matches = fetch_all(cups=chosen)

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
