"""
liveonsat_fetcher.py
--------------------
Scrapes liveonsat.com listings pages (static HTML, plain GET) and produces
per-match, per-channel broadcast data for TVsport.live.

CRITICAL QUIRK handled here: for cookie-less requests liveonsat renders all
kick-off times in an arbitrary server-default timezone (observed: GMT-4).
The offset is declared ONLY in the page header text:
    "Website Last updated on Thu 27/08/2026 2:43 AM (GMT -04:00)"
This module parses that offset and converts every kick-off to UTC and to
UK wall-clock time. NEVER assume the times on the page are UK times.

Usage:
    python liveonsat_fetcher.py                          # UK page only
    python liveonsat_fetcher.py --pages uk germany italy france
    python liveonsat_fetcher.py --out liveonsat.json --debug

Output JSON shape:
{
  "fetched_at": "...", 
  "pages": {"uk": {"page_offset": "-04:00", "page_updated": "..."}},
  "fixtures": [
    {
      "source_page": "uk",
      "competition": "English Premier League",
      "round": "Week 2",
      "home": "Bournemouth",
      "away": "Everton",
      "kickoff_utc": "2026-08-29T14:00:00Z",
      "kickoff_uk": "2026-08-29 15:00",
      "status": null | "POSTPONED",
      "channels": [
        {"name": "Premier Sports 1 Ireland HD", "pay": false, "geo": false, "app": false},
        ...
      ]
    }, ...
  ]
}

Integration notes for merger.py:
  * Use match_key() to align with fixtures.json entries (normalised team
    names + kickoff_utc within +/- 15 min).
  * premier_sports_ireland_picks() returns which 3pm-slot matches Premier
    Sports Ireland has selected -- resolves the ROI blackout-slot question.
  * Channel names feed straight into channel_normaliser.canonical().

No third-party deps beyond requests + beautifulsoup4 (both already used by
the pipeline). Python 3.9+ (zoneinfo).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://liveonsat.com/"

PAGES = {
    "uk":      "uk-britain-ireland-all-football.php",
    "germany": "europe-germany-all-football.php",
    "italy":   "europe-italy-all-football.php",
    "france":  "europe-france-all-football.php",
    "spain":   "europe-spain-all-football.php",
    "netherlands": "europe-netherlands-eredivisie.php",
    "portugal":    "europe-portugal-primeira-liga.php",
    "ucl":     "club-uefa-champions-league.php",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 TVsportLive/1.0")

UK_TZ = ZoneInfo("Europe/London")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}

DAY_HEADER_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,\s*"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(" + "|".join(MONTHS) + r")\s*$")

# "Website Last updated on Thu 27/08/2026 2:43 AM (GMT -04:00)"
UPDATED_RE = re.compile(
    r"Last\s+updated\s+on\s+\w{3}\s+(\d{2})/(\d{2})/(\d{4}).{0,20}?"
    r"\(GMT\s*([+-])(\d{2}):(\d{2})\)", re.S)

ST_RE = re.compile(r"^ST:\s*(\d{1,2}):(\d{2})\s*$")
TEAMS_RE = re.compile(r"^(.{1,60}?)\s+v\s+(.{1,60})$")
POSTPONED_RE = re.compile(r"P[\s\-\*]*O[\s\-\*]*S[\s\-\*]*T[\s\-\*]*P", re.I)

# channel-name flag markers, stripped and recorded
FLAG_PATTERNS = [
    (re.compile(r"\(\$/geo/R\)"), ("pay", "geo")),
    (re.compile(r"\(geo/R\)"), ("geo",)),
    (re.compile(r"\[\$\]"), ("pay",)),
    (re.compile(r"\[\$/geo/R\]"), ("pay", "geo")),
    (re.compile(r"\[via APP\]", re.I), ("app",)),
    (re.compile(r"\[online\]", re.I), ("app",)),
    (re.compile(r"\[app\]", re.I), ("app",)),
]
TV_EMOJI = "\U0001F4FA"  # 📺


def fetch_page(slug: str, session: requests.Session, retries: int = 3) -> str:
    url = BASE + PAGES[slug]
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:  # pragma: no cover
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"liveonsat fetch failed for {url}: {last_err}")


def parse_page_offset(text: str):
    """Return (updated_date, tz_offset) parsed from the page header.
    Falls back to GMT-4 (the observed cookie-less default) with a warning."""
    m = UPDATED_RE.search(text)
    if not m:
        sys.stderr.write("[liveonsat] WARNING: could not find page offset "
                         "header; assuming GMT-04:00\n")
        return None, timezone(timedelta(hours=-4))
    dd, mm, yyyy, sign, oh, om = m.groups()
    delta = timedelta(hours=int(oh), minutes=int(om))
    if sign == "-":
        delta = -delta
    updated = datetime(int(yyyy), int(mm), int(dd))
    return updated, timezone(delta)


def infer_year(month: int, updated: datetime | None) -> int:
    """Page dates carry no year. Anchor to the 'Last updated' year and roll
    over into next year for months far behind the update month."""
    now = updated or datetime.now(timezone.utc).replace(tzinfo=None)
    year = now.year
    if month < now.month - 6:      # e.g. page updated in Nov listing Jan
        year += 1
    elif month > now.month + 6:    # defensive: page updated Jan listing Dec
        year -= 1
    return year


def clean_channel(raw: str):
    name = raw.replace(TV_EMOJI, "").strip()
    flags = {"pay": False, "geo": False, "app": False}
    for pat, keys in FLAG_PATTERNS:
        if pat.search(name):
            for k in keys:
                flags[k] = True
            name = pat.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" -\u00a0").strip()
    return {"name": name, **flags} if name else None


def _looks_like_competition(line: str) -> bool:
    """Competition headers look like 'English Premier League - Week 2'.
    Channel names never contain ' - ' with surrounding spaces AND a
    following teams line, which the state machine checks via lookahead."""
    return " - " in line


def parse_text_lines(lines, updated: datetime | None, page_tz: timezone,
                     source_page: str, debug: bool = False):
    """Line-oriented state machine over the tag-stripped page text.

    Layout emitted by liveonsat's table markup when flattened one element
    per line:
        Friday, 28th August          <- day header
        English Premier League - Week 2
        Crystal Palace v Manchester City
        ST: 15:00                    <- in the PAGE's timezone!
        Sky Sports Main Event HD     <- channel lines ...
        ...
        (next competition header / day header)
    """
    lines = [l.strip() for l in lines if l.strip()]   # drop blanks so
    # lookaheads see the next real elements, not whitespace rows
    fixtures = []
    cur_date = None            # (year, month, day)
    pending_comp = None
    pending_teams = None
    current = None             # fixture dict currently collecting channels

    def finalise():
        nonlocal current
        if current and current["channels"]:
            fixtures.append(current)
        elif current and debug:
            sys.stderr.write(f"[liveonsat] dropped channel-less fixture: "
                             f"{current['home']} v {current['away']}\n")
        current = None

    n = len(lines)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        dh = DAY_HEADER_RE.match(line)
        if dh:
            finalise()
            day = int(dh.group(2)); month = MONTHS[dh.group(3)]
            cur_date = (infer_year(month, updated), month, day)
            pending_comp = pending_teams = None
            continue

        st = ST_RE.match(line)
        if st and pending_teams and cur_date:
            finalise()
            hh, mm = int(st.group(1)), int(st.group(2))
            local = datetime(*cur_date, hh, mm, tzinfo=page_tz)
            utc = local.astimezone(timezone.utc)
            uk = utc.astimezone(UK_TZ)
            comp, rnd = (pending_comp.split(" - ", 1) + [""])[:2] \
                if pending_comp else ("", "")
            current = {
                "source_page": source_page,
                "competition": comp.strip(),
                "round": rnd.strip(),
                "home": pending_teams[0].strip(),
                "away": pending_teams[1].strip(),
                "kickoff_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kickoff_uk": uk.strftime("%Y-%m-%d %H:%M"),
                "status": None,
                "channels": [],
            }
            pending_teams = None
            continue

        if POSTPONED_RE.search(line) and current:
            current["status"] = "POSTPONED"
            continue

        tm = TEAMS_RE.match(line)
        # A teams line is only accepted if an ST: line follows soon after —
        # guards against channel names that could contain ' v '.
        if tm:
            lookahead = [lines[j].strip() for j in range(i + 1, min(i + 3, n))]
            if any(ST_RE.match(x) for x in lookahead):
                finalise()
                pending_teams = (tm.group(1), tm.group(2))
                # competition header is the nearest previous ' - ' line
                continue

        if _looks_like_competition(line):
            # Might be a competition header for the NEXT fixture; check that
            # a teams+ST pair follows within a few lines before believing it.
            lookahead = [lines[j].strip() for j in range(i + 1, min(i + 5, n))]
            has_teams = any(TEAMS_RE.match(x) for x in lookahead)
            has_st = any(ST_RE.match(x) for x in lookahead)
            if has_teams and has_st:
                finalise()
                pending_comp = line
                continue

        if current is not None:
            ch = clean_channel(line)
            if ch:
                current["channels"].append(ch)

    finalise()
    return fixtures


def parse_page(html: str, source_page: str, debug: bool = False):
    updated, page_tz = parse_page_offset(html)
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "select", "option"]):
        bad.decompose()   # drops the giant timezone <select> menu
    text = soup.get_text("\n")
    lines = text.split("\n")
    fixtures = parse_text_lines(lines, updated, page_tz, source_page, debug)
    off = page_tz.utcoffset(None)
    total_min = int(off.total_seconds() // 60)
    sign = "-" if total_min < 0 else "+"
    off_str = f"{sign}{abs(total_min) // 60:02d}:{abs(total_min) % 60:02d}"
    meta = {
        "page_updated": updated.strftime("%Y-%m-%d") if updated else None,
        "page_offset": off_str,
        "fixture_count": len(fixtures),
    }
    if debug:
        sys.stderr.write(f"[liveonsat] {source_page}: {len(fixtures)} "
                         f"fixtures, offset {meta['page_offset']}\n")
    return fixtures, meta


# ---------------------------------------------------------------- helpers

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    for junk in (" fc", " afc", " cf", " ac", " hotspur", "&", "."):
        s = s.replace(junk, " ")
    return re.sub(r"\s+", " ", s).strip()


def match_key(home: str, away: str) -> str:
    return f"{_norm(home)}|{_norm(away)}"


def premier_sports_ireland_picks(fixtures):
    """Return liveonsat fixtures that Premier Sports Ireland is showing.
    Use this in merger.py to resolve which single 3pm-BST Saturday EPL match
    Premier Sports Ireland selected (the thing static rights can't tell us).
    """
    out = []
    for f in fixtures:
        for ch in f["channels"]:
            if re.search(r"premier sports.*ireland", ch["name"], re.I):
                out.append(f)
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", nargs="+", default=["uk"],
                    choices=sorted(PAGES))
    ap.add_argument("--out", default="liveonsat.json")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    session = requests.Session()
    all_fixtures, meta = [], {}
    for slug in args.pages:
        html = fetch_page(slug, session)
        fx, m = parse_page(html, slug, args.debug)
        all_fixtures.extend(fx)
        meta[slug] = m
        time.sleep(1.5)   # be polite: one page every ~1.5s

    payload = {
        "fetched_at": datetime.now(timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages": meta,
        "fixtures": all_fixtures,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    total = len(all_fixtures)
    ps = len(premier_sports_ireland_picks(all_fixtures))
    print(f"liveonsat: wrote {total} fixtures from {len(meta)} page(s) "
          f"to {args.out} ({ps} Premier Sports Ireland picks)")
    if total == 0:
        sys.exit("ERROR: 0 fixtures parsed - page structure may have "
                 "changed. Re-run with --debug and inspect.")


if __name__ == "__main__":
    main()
