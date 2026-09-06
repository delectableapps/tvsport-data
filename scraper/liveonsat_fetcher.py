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
    # Rugby Union (all competitions on one page). Rows carry
    # source_page="rugby" so the football merger can ignore them and
    # rugby_merger.py can select them. Add "rugby" to the --pages list in
    # run_liveonsat.bat on the home PC.
    "rugby":   "x-rugby-union.php",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Full browser-like header set. Some hosts 403 on a bare User-Agent.
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",   # NOT "br": requests cannot unpack Brotli
    "Referer": "https://liveonsat.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Cache-Control": "max-age=0",
}

# Optional: curl_cffi impersonates Chrome's TLS fingerprint, which defeats
# bot detection that 403s plain `requests` even with browser headers.
# `pip install curl_cffi`. Falls back to requests if not installed.
try:
    from curl_cffi import requests as _cffi_requests  # type: ignore
    _HAVE_CFFI = True
except Exception:  # pragma: no cover
    _HAVE_CFFI = False

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

# Rugby page headings that carry no " - Round" suffix. Kept deliberately
# narrow so a channel name can never be mistaken for a heading.
RUGBY_BARE_HEADING_RE = re.compile(
    r"^(rugby union (friendly|friendlies|international|internationals|test)"
    r"|autumn nations series|summer (tour|series|internationals)"
    r"|international (friendly|match|test)|test match(es)?)\s*$", re.I)


def _get_cffi(url: str) -> str:
    r = _cffi_requests.get(url, headers=HEADERS, impersonate="chrome",
                           timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} (curl_cffi)")
    if not _looks_like_html(r.text):
        raise RuntimeError("response is not HTML (curl_cffi)")
    return r.text


def _looks_like_html(text: str) -> bool:
    head = text[:4000].lower()
    return "<html" in head or "<!doctype" in head or "<body" in head


def _get_requests(url: str, session: requests.Session) -> str:
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if not _looks_like_html(r.text):
        raise RuntimeError(
            f"response is not HTML (Content-Encoding="
            f"{r.headers.get('Content-Encoding')!r}, {len(r.content)} bytes) "
            f"- probably an undecoded compression scheme")
    return r.text


def fetch_page(slug: str, session: requests.Session, retries: int = 2) -> str:
    """Fetch one liveonsat page. Tries curl_cffi (Chrome TLS impersonation)
    first if installed, then plain requests. A 403 is treated as a hard
    block and is NOT retried — retrying a block just wastes minutes."""
    url = BASE + PAGES[slug]
    errors = []
    clients = ([("curl_cffi", lambda: _get_cffi(url))] if _HAVE_CFFI else []) \
              + [("requests", lambda: _get_requests(url, session))]
    for name, call in clients:
        for attempt in range(retries):
            try:
                return call()
            except Exception as e:
                msg = str(e)
                errors.append(f"{name}: {msg}")
                if "403" in msg:
                    break              # blocked — no point retrying this client
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"liveonsat fetch failed for {url}: "
                       + " | ".join(errors))


# liveonsat renders times in a *DST-aware* zone chosen from the viewer's IP
# (UK viewers see Europe/London, US-hosted fetches see America/New_York), but
# its header only prints the offset in force *today*. Fixtures on the other
# side of a clock change would be an hour out if we applied that fixed
# offset, so map the header offset to the zone it implies.
_OFFSET_TO_ZONE = {
    "+00:00": "Europe/London", "+01:00": "Europe/London",
    "-04:00": "America/New_York", "-05:00": "America/New_York",
}


def _tz_from_offset(sign: str, oh: str, om: str):
    key = f"{sign}{int(oh):02d}:{int(om):02d}"
    zone = _OFFSET_TO_ZONE.get(key)
    if zone:
        try:
            return ZoneInfo(zone)
        except Exception:
            pass
    delta = timedelta(hours=int(oh), minutes=int(om))
    return timezone(-delta if sign == "-" else delta)


def parse_page_offset(text: str, fallback_tz=None):
    """Return (updated_date, tz, found) parsed from the page header.

    Some pages (the rugby union page, Sept 2026) print a broken header —
    "... 07:04:14 PM GMT +" with no offset — so when the header can't be
    parsed we use `fallback_tz` (the offset found on an earlier page in the
    same run; the site renders every page in the same zone for one client)
    and only as a last resort the historical cookie-less default, GMT-4."""
    m = UPDATED_RE.search(text)
    if not m:
        if fallback_tz is not None:
            sys.stderr.write("[liveonsat] WARNING: no page offset header; "
                             f"using offset from an earlier page ({fallback_tz})\n")
            return None, fallback_tz, False
        sys.stderr.write("[liveonsat] WARNING: could not find page offset "
                         "header; assuming GMT-04:00\n")
        return None, timezone(timedelta(hours=-4)), False
    dd, mm, yyyy, sign, oh, om = m.groups()
    updated = datetime(int(yyyy), int(mm), int(dd))
    return updated, _tz_from_offset(sign, oh, om), True


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

        if source_page == "rugby" and RUGBY_BARE_HEADING_RE.match(line) \
                and not _looks_like_competition(line):
            # e.g. "Rugby Union Friendly" — no " - Round N" part, so the
            # generic rule below never sees it and the fixture would inherit
            # the previous competition (Scotland v Canada filed as Top 14).
            lookahead = [lines[j].strip() for j in range(i + 1, min(i + 5, n))]
            if any(TEAMS_RE.match(x) for x in lookahead) and any(ST_RE.match(x) for x in lookahead):
                finalise()
                pending_comp = line
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


def parse_page(html: str, source_page: str, debug: bool = False,
               fallback_tz=None):
    updated, page_tz, offset_found = parse_page_offset(html, fallback_tz)
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "select", "option"]):
        bad.decompose()   # drops the giant timezone <select> menu
    text = soup.get_text("\n")
    lines = text.split("\n")
    fixtures = parse_text_lines(lines, updated, page_tz, source_page, debug)
    off = datetime.now(page_tz).utcoffset() or timedelta(0)
    total_min = int(off.total_seconds() // 60)
    sign = "-" if total_min < 0 else "+"
    off_str = f"{sign}{abs(total_min) // 60:02d}:{abs(total_min) % 60:02d}"
    meta = {
        "page_updated": updated.strftime("%Y-%m-%d") if updated else None,
        "page_offset": off_str,
        "page_zone": getattr(page_tz, "key", None),
        "offset_found": offset_found,
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
    print(f"liveonsat: HTTP client = "
          f"{'curl_cffi (Chrome impersonation)' if _HAVE_CFFI else 'requests'}")
    all_fixtures, meta = [], {}
    session_tz = None          # offset from the first page with a good header
    for slug in args.pages:
        html = fetch_page(slug, session)
        fx, m = parse_page(html, slug, args.debug, fallback_tz=session_tz)
        if m.get("offset_found") and session_tz is None:
            _, session_tz, _ = parse_page_offset(html)
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
