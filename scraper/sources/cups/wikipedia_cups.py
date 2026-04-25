"""
wikipedia_cups.py
-----------------
Scrapes upcoming-round fixtures for the major British knockout cups from
Wikipedia season articles:

  - FA Cup                  -> en.wikipedia.org/wiki/{season}_FA_Cup
  - EFL Cup (Carabao)       -> en.wikipedia.org/wiki/{season}_EFL_Cup
  - Scottish Cup            -> en.wikipedia.org/wiki/{season}_Scottish_Cup
  - Scottish League Cup     -> en.wikipedia.org/wiki/{season}_Scottish_League_Cup

Why Wikipedia rather than the official cup sites?

  thefa.com / efl.com / scottishfa.co.uk publish TV-picked fixtures as
  bespoke news articles per round with no stable machine-readable format.
  A scraper aimed at the article for one round breaks when the next
  round's article uses a different layout. Wikipedia season articles, by
  contrast, use long-established wikitable conventions (one table per
  round) that have been stable for years and are updated within hours of
  a draw.

Parsing strategy
----------------

Wikipedia renders each round as an HTML table with `class="wikitable"`
near a heading whose text matches the round name (e.g. "Third round
proper"). Fixture rows take one of two shapes:

  (a) A "wikitable football-result" / "wikitable football-fixture" row
      with three relevant cells: home team, score/v-cell, away team.
      Score cells may hold a time (e.g. "20:00"), a result ("2-1"),
      "v" / "vs", or "Postponed".

  (b) A plain football-match template row of the form::

          | Team A | v | Team B | 15:00 | 10 January 2026 |

Both shapes are handled. We look for:

  * A `<th>` row with header labels OR, failing that, cells that look
    like team names flanking a center "score" cell.
  * Nearby `<caption>` / preceding `<h3>` / `<h4>` headings for the
    round name.
  * Any cell containing a parseable date in the vicinity of each row.

Where date and time are present on the same row they're combined into a
naive ISO-8601 kickoff string. Where only a date is given, `time_local`
stays None and merger.py is expected to enrich the time via TV listings
or EPG data.

This scraper is intentionally conservative: it logs and skips rows that
don't parse cleanly rather than guessing. merger.py already has a good
tolerance for missing fields; it's better for a row to be dropped than
to emit bogus fixtures.

Dependencies
------------

requests + beautifulsoup4 + lxml (plus optional Playwright fallback,
wired up but not used unless Wikipedia starts rendering fixture tables
client-side, which they don't today).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup, Tag

from ._common import (
    CUPS, CupMeta, Match,
    current_cup_season, find_cup_by_name,
    make_kickoff_utc, parse_date, parse_score, parse_time,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Round headings we'll accept (case-insensitive substring match). Order
# matters only for logging; we scan all rounds.
# ---------------------------------------------------------------------------

ROUND_HEADINGS: tuple[str, ...] = (
    "first round proper",
    "second round proper",
    "third round proper",
    "fourth round proper",
    "fifth round proper",
    "first round",
    "second round",
    "third round",
    "fourth round",
    "fifth round",
    "sixth round",
    "quarter-final",
    "quarter finals",
    "quarterfinal",
    "semi-final",
    "semi finals",
    "semifinal",
    "final",
    "round of 16",
    "round of 32",
    "round of 64",
    "group stage",
)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

WIKI_BASE = "https://en.wikipedia.org/wiki/"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        # Wikipedia asks for a descriptive UA with contact info.
        "User-Agent": "tvsport.live scraper (+https://tvsport.live)",
        "Accept": "text/html,application/xhtml+xml",
    })
    return s


def _fetch_html(session: requests.Session, url: str, timeout: float = 20.0) -> str | None:
    try:
        r = session.get(url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("wikipedia_cups: network error for %s -> %s", url, e)
        return None
    if r.status_code == 404:
        log.info("wikipedia_cups: page not found: %s", url)
        return None
    if r.status_code != 200:
        log.warning("wikipedia_cups: HTTP %s for %s", r.status_code, url)
        return None
    return r.text


def _playwright_fetch_html(url: str) -> str | None:
    """Fallback path. Not used today — Wikipedia serves fully rendered HTML.
    Left in place as a cheap safety net in case Wikipedia ever moves fixture
    tables into a JS-hydrated component. Only invoked if the main fetch
    returns content but the parser finds zero tables."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        log.info("wikipedia_cups: playwright not installed; skipping fallback")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.warning("wikipedia_cups: playwright fallback failed for %s -> %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Regex for cells whose text is literally "v"/"vs" (fixture not yet played).
_VS_CELL_PATTERN = re.compile(r"^\s*(v|vs|v\.|—|-)\s*$", re.I)

# Regex for final-score cells. Matches "3-1" / "3–1" / "3—1" but NOT
# "15:00" (colon-separated = kickoff time, handled elsewhere).
_SCORE_CELL_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*[\u2013\u2014\-]\s*(\d{1,2})\s*$"
)


def _clean_team(text: str) -> str:
    """Strip flag emojis, reference markers, trailing '(H)' annotations etc."""
    if not text:
        return ""
    # Kill footnote markers like "[a]" or "[1]"
    text = re.sub(r"\[[^\]]{1,5}\]", "", text)
    # Strip common Wikipedia team annotations.
    text = re.sub(r"\s*\((H|A|holders?|replay)\)\s*$", "", text, flags=re.I)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _nearest_round_heading(table: Tag) -> str | None:
    """Walk backwards from the table to find the closest section heading."""
    node = table
    for _ in range(30):  # safety bound
        node = node.find_previous(["h2", "h3", "h4"])
        if node is None:
            return None
        heading_text = node.get_text(" ", strip=True).lower()
        for candidate in ROUND_HEADINGS:
            if candidate in heading_text:
                # Normalise for display ("Third round proper" etc).
                return node.get_text(" ", strip=True)
        # Keep walking if this heading isn't a round.
    return None


def _row_to_match(
    row: Tag,
    cup: CupMeta,
    round_label: str | None,
    fallback_date: str | None,
) -> Match | None:
    cells = row.find_all(["td", "th"])
    if len(cells) < 3:
        return None

    texts = [c.get_text(" ", strip=True) for c in cells]

    # Find a "score/vs" cell — shortest cell between two longer team-name cells.
    # Most fixture rows have exactly {home, score_or_v, away, date, time}.
    home = away = None
    score_cell_idx = None

    for i, t in enumerate(texts):
        is_vs = bool(_VS_CELL_PATTERN.match(t))
        is_score = bool(_SCORE_CELL_PATTERN.match(t.strip()))
        # A centre cell can also be a pre-match kickoff time like "15:00".
        # We accept it only if it looks like HH:MM with nothing else around.
        is_time_only = bool(re.match(r"^\s*([01]?\d|2[0-3]):([0-5]\d)\s*$", t))
        if is_vs or is_score or is_time_only:
            # Need at least one cell either side
            if i >= 1 and i < len(texts) - 1:
                home_candidate = _clean_team(texts[i - 1])
                away_candidate = _clean_team(texts[i + 1])
                if home_candidate and away_candidate:
                    home = home_candidate
                    away = away_candidate
                    score_cell_idx = i
                    break

    if not home or not away or score_cell_idx is None:
        return None

    score_text = texts[score_cell_idx]
    score_result = parse_score(score_text)

    # Hunt for a date / time in any remaining cell.
    date = None
    time_local = None
    for i, t in enumerate(texts):
        if i in (score_cell_idx - 1, score_cell_idx, score_cell_idx + 1):
            continue  # skip team and score cells
        if not date:
            date = parse_date(t)
        if not time_local:
            time_local = parse_time(t)

    # Time can also hide in the score cell before a match is played.
    if not time_local:
        time_local = parse_time(score_text)
    if not date:
        date = fallback_date

    if not date:
        # Without a date we can't place the fixture on a schedule.
        return None

    if score_result:
        score_ft, status = score_result
        # Don't emit a stale kickoff time for a finished match.
        time_local_out = None
    else:
        score_ft, status = None, "scheduled"
        time_local_out = time_local

    kickoff_utc = make_kickoff_utc(date, time_local_out)

    return Match(
        competition_code=cup.code,
        competition_name=cup.name,
        country=cup.country,
        round_label=round_label,
        kickoff_utc=kickoff_utc,
        date=date,
        time_local=time_local_out,
        home=home,
        away=away,
        status=status,
        score_ft=score_ft,
        source="wikipedia",
        raw={"row_html": str(row)[:500]},
    )


def _parse_cup_page(html: str, cup: CupMeta) -> list[Match]:
    soup = BeautifulSoup(html, "lxml")

    # Find every wikitable. Wikipedia decorates fixture tables with
    # additional classes too ("football-box", "football-result") but the
    # base "wikitable" class is the most consistent anchor.
    tables = soup.select("table.wikitable")
    if not tables:
        log.warning("wikipedia_cups: no wikitable found in %s page", cup.competition_code)
        return []

    # Collect any page-level dates that could serve as a fallback — e.g.
    # the round's play dates are often stated in a preceding paragraph.
    all_matches: list[Match] = []

    for table in tables:
        round_label = _nearest_round_heading(table)
        if not round_label:
            # Skip navigation / summary tables with no round context.
            continue

        # A paragraph's date near the heading is a decent fallback.
        fallback_date: str | None = None
        prev = table.find_previous(["p", "h2", "h3", "h4"])
        if prev is not None:
            fallback_date = parse_date(prev.get_text(" ", strip=True))

        rows = table.find_all("tr")
        for row in rows:
            m = _row_to_match(row, cup, round_label, fallback_date)
            if m:
                all_matches.append(m)

    # De-duplicate — same fixture may appear in a per-round table and a
    # bracket summary. Use the shared dedupe key so the result agrees with
    # the other scrapers' view of which fixtures are identical.
    seen: set[tuple[str, str, str]] = set()
    unique: list[Match] = []
    for m in all_matches:
        key = m.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(m)

    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_cup(
    cup: CupMeta,
    season: str,
    session: requests.Session | None = None,
) -> list[Match]:
    if not cup.wiki_slug:
        return []
    s = session or _session()
    url = f"{WIKI_BASE}{quote(season)}_{cup.wiki_slug}"
    log.info("wikipedia_cups: fetching %s (%s)", cup.code, url)
    html = _fetch_html(s, url)
    if not html:
        return []

    matches = _parse_cup_page(html, cup)

    # Safety net: if the static fetch produced no matches but the page is
    # clearly there, try Playwright. In practice this should never fire.
    if not matches and "wikitable" not in html:
        log.info("wikipedia_cups: trying Playwright fallback for %s", cup.code)
        html2 = _playwright_fetch_html(url)
        if html2:
            matches = _parse_cup_page(html2, cup)

    log.info("wikipedia_cups: %s -> %d matches", cup.code, len(matches))
    return matches


def fetch_all_cups(
    season: str | None = None,
    cups: Iterable[CupMeta] | None = None,
) -> list[Match]:
    season = season or current_cup_season()
    cups = tuple(cups) if cups is not None else CUPS
    s = _session()
    out: list[Match] = []
    for cup in cups:
        out.extend(fetch_cup(cup, season, session=s))
    log.info("wikipedia_cups: total %d matches across %d cups",
             len(out), len(cups))
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Scrape British cup fixtures from Wikipedia")
    ap.add_argument("--season", help="Season slug e.g. 2025-26 (default: auto)")
    ap.add_argument("--cup", help="Only scrape one cup by code (FAC/EFLC/SFAC/SLFC)")
    ap.add_argument("--out", help="Write matches as JSON to this path")
    ap.add_argument("--html-file",
                    help="Parse a locally saved HTML file instead of fetching — "
                         "handy for offline testing")
    args = ap.parse_args()

    if args.html_file:
        # Offline mode for development / CI tests.
        cup_code = args.cup or "FAC"
        chosen = next((c for c in CUPS if c.code == cup_code), None)
        if not chosen:
            raise SystemExit(f"Unknown --cup code: {cup_code}")
        with open(args.html_file, "r", encoding="utf-8") as fh:
            html = fh.read()
        matches = _parse_cup_page(html, chosen)
    else:
        cups = CUPS
        if args.cup:
            cups = tuple(c for c in CUPS if c.code == args.cup)
            if not cups:
                raise SystemExit(
                    f"No cup with code {args.cup!r}. "
                    f"Known codes: {[c.code for c in CUPS]}"
                )
        matches = fetch_all_cups(season=args.season, cups=cups)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            _json.dump([m.to_dict() for m in matches], fh, indent=2, ensure_ascii=False)
        print(f"Wrote {len(matches)} matches to {args.out}")
    else:
        for m in matches[:30]:
            print(f"{m.date} {m.time_local or 'TBC':5s}  "
                  f"{m.competition_code:5s}  {m.round_label or '?':20s}  "
                  f"{m.home} vs {m.away}")
        if len(matches) > 30:
            print(f"... and {len(matches) - 30} more")
