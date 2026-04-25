"""
_common.py
----------
Shared types and helpers for the cup scrapers (BBC, Sky, Wikipedia) and
the cup orchestrator. Kept separate from the league-side openfootball
fetcher so neither imports the other.

The `Match` dataclass here is structurally identical to the one in
openfootball_fetcher — same field names, same meanings — so merger.py
can treat both outputs the same way. We keep two copies rather than
creating a cross-import dependency because each module was written to
stand alone.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Competition codes — same codes used across BBC/Sky/Wikipedia scrapers so
# the orchestrator can dedupe across sources.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CupMeta:
    code: str
    name: str
    country: str

    # Identifiers each scraper uses to target its own URL/filter.
    bbc_slug: str | None = None          # e.g. "fa-cup"
    sky_slug: str | None = None          # e.g. "fa-cup"
    wiki_slug: str | None = None         # e.g. "FA_Cup"

    # Names the BBC/Sky scrapers will see on their per-day pages, used to
    # filter fixtures belonging to this competition out of a day feed that
    # also contains Premier League, EFL, etc. Case-insensitive substring
    # match. First entry is canonical; others are known aliases.
    match_names: tuple[str, ...] = ()


CUPS: tuple[CupMeta, ...] = (
    CupMeta(
        code="FAC", name="FA Cup", country="en",
        bbc_slug="fa-cup", sky_slug="fa-cup", wiki_slug="FA_Cup",
        match_names=("FA Cup", "Emirates FA Cup"),
    ),
    CupMeta(
        code="EFLC", name="EFL Cup", country="en",
        bbc_slug="league-cup", sky_slug="carabao-cup", wiki_slug="EFL_Cup",
        match_names=("EFL Cup", "Carabao Cup", "League Cup"),
    ),
    CupMeta(
        code="SFAC", name="Scottish Cup", country="sc",
        bbc_slug="scottish-cup", sky_slug="scottish-cup", wiki_slug="Scottish_Cup",
        match_names=("Scottish Cup", "Scottish Gas Scottish Cup", "Scottish FA Cup"),
    ),
    CupMeta(
        code="SLFC", name="Scottish League Cup", country="sc",
        bbc_slug="scottish-league-cup", sky_slug="scottish-league-cup",
        wiki_slug="Scottish_League_Cup",
        match_names=("Scottish League Cup", "Premier Sports Cup",
                     "Betfred Cup", "SPFL Premier Sports Cup"),
    ),
)


def find_cup_by_name(competition_text: str) -> CupMeta | None:
    """Given a 'competition name' string scraped from BBC/Sky, return the
    matching CupMeta or None if it's not one of our tracked cups."""
    if not competition_text:
        return None
    t = competition_text.strip().lower()
    for cup in CUPS:
        for alias in cup.match_names:
            if alias.lower() in t:
                return cup
    return None


# ---------------------------------------------------------------------------
# Match dataclass — identical shape to openfootball_fetcher.Match
# ---------------------------------------------------------------------------

@dataclass
class Match:
    competition_code: str
    competition_name: str
    country: str
    round_label: str | None
    kickoff_utc: str | None
    date: str                           # YYYY-MM-DD
    time_local: str | None              # HH:MM or None
    home: str
    away: str
    status: str                         # "scheduled" | "finished" | "postponed"
    score_ft: list[int] | None
    source: str                         # "bbc" | "sky" | "wikipedia"
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d.pop("raw", None)
        return d

    def dedupe_key(self) -> tuple[str, str, str]:
        """Key used by the orchestrator to match fixtures across sources.
        Team names are lowercased and aggressively normalised so 'Man City'
        and 'Manchester City' collapse to the same key."""
        return (self.date, _normalise_team(self.home), _normalise_team(self.away))


# ---------------------------------------------------------------------------
# Team name normalisation — we need this to dedupe across BBC/Sky/Wikipedia
# because each uses slightly different team name conventions:
#
#   BBC:       "Man City"           /  "Spurs"       /  "Brighton"
#   Sky:       "Manchester City"    /  "Tottenham Hotspur"  /  "Brighton and Hove Albion"
#   Wikipedia: "Manchester City F.C."  /  "Tottenham Hotspur F.C."
#
# This table covers the bulk of top-flight English clubs. Lower-league and
# non-league teams are less prone to abbreviation differences and usually
# match after the generic _normalise_team() scrubs.
# ---------------------------------------------------------------------------

TEAM_ALIASES = {
    # short -> canonical long form
    "man city":            "manchester city",
    "man utd":             "manchester united",
    "man united":          "manchester united",
    "spurs":               "tottenham hotspur",
    "tottenham":           "tottenham hotspur",
    "brighton":            "brighton and hove albion",
    "brighton & hove albion": "brighton and hove albion",
    "wolves":              "wolverhampton wanderers",
    "wolverhampton":       "wolverhampton wanderers",
    "leeds":               "leeds united",
    "newcastle":           "newcastle united",
    "west ham":            "west ham united",
    "nottingham forest":   "nottingham forest",
    "forest":              "nottingham forest",
    "west brom":           "west bromwich albion",
    "west bromwich":       "west bromwich albion",
    "qpr":                 "queens park rangers",
    "queen's park rangers": "queens park rangers",
    "mk dons":             "milton keynes dons",
    "afc bournemouth":     "bournemouth",
    "bournemouth":         "bournemouth",
    # Scottish
    "hearts":              "heart of midlothian",
    "hibs":                "hibernian",
    "killie":              "kilmarnock",
    "st johnstone":        "st johnstone",
    "st mirren":           "st mirren",
    "dundee utd":          "dundee united",
    "ross co":             "ross county",
    "motherwell":          "motherwell",
    "rangers":             "rangers",
    "celtic":              "celtic",
}

# Strip only the "FC" / "AFC" / "F.C." corporate suffix. We deliberately do
# NOT strip semantic suffixes like "United", "City", "Rovers" — those
# disambiguate clubs (Manchester United vs Manchester City) and removing
# them would create false duplicates. Semantic-suffix differences are
# handled by the TEAM_ALIASES table, which is exhaustive for the clubs
# that actually need aliasing.
_FC_SUFFIX_PATTERN = re.compile(
    r"\s+(f\s*c|a\s*f\s*c)\s*$",
    re.I,
)


def _normalise_team(name: str) -> str:
    """Aggressively normalise a team name for deduplication. Must be a
    pure function so the same input always collapses to the same output
    regardless of which source produced it."""
    if not name:
        return ""
    # Lowercase, strip, collapse whitespace
    n = re.sub(r"\s+", " ", name.lower().strip())
    # Kill common Wikipedia decorations
    n = re.sub(r"\(\s*[ah]\s*\)\s*$", "", n).strip()
    n = re.sub(r"\s*\[\w+\]\s*$", "", n).strip()
    # Remove common punctuation. Must happen BEFORE the FC-suffix strip so
    # that "F.C." becomes "fc" / "f c" before the regex runs.
    n = n.replace(".", "").replace(",", "")
    n = re.sub(r"\s+", " ", n).strip()
    # Strip the FC / AFC corporate suffix so "Manchester United FC" and
    # "Manchester United" collapse together.
    n = _FC_SUFFIX_PATTERN.sub("", n).strip()
    # Now the alias lookup. If the short/alternative form is in the table,
    # return its canonical expansion.
    if n in TEAM_ALIASES:
        return TEAM_ALIASES[n]
    return n


# ---------------------------------------------------------------------------
# Date / time parsing (shared with wikipedia_cups)
# ---------------------------------------------------------------------------

_MONTH_LOOKUP = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"],
    start=1,
)}

_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b"),      # 10 January 2026
    re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b"),    # January 10, 2026
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                   # 2026-01-10
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),               # 10/01/2026 (DD/MM)
)

_TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")

_SCORE_PATTERN = re.compile(r"^\s*(\d{1,2})\s*[\u2013\u2014\-]\s*(\d{1,2})\s*$")
# Note: we intentionally DO NOT accept a colon separator here. Scores use
# en-dashes, em-dashes, or hyphens ("3-1", "3–1"). Colon-separated tokens
# like "15:00" are kickoff times and must be parsed by parse_time() instead.


_ORDINAL_PATTERN = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.I)


def parse_date(text: str) -> str | None:
    if not text:
        return None
    # Strip English ordinal suffixes ("10th" -> "10") before pattern matching.
    # Sky uses "Saturday 10th January 2026"; BBC sometimes does the same.
    text = _ORDINAL_PATTERN.sub(r"\1", text)
    m = _DATE_PATTERNS[2].search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_PATTERNS[0].search(text)
    if m:
        day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
        month = _MONTH_LOOKUP.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    m = _DATE_PATTERNS[1].search(text)
    if m:
        month_name, day, year = m.group(1).lower(), m.group(2), m.group(3)
        month = _MONTH_LOOKUP.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    m = _DATE_PATTERNS[3].search(text)
    if m:
        # Assume DD/MM/YYYY — British convention, fine for BBC/Sky
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{year}-{month:02d}-{day:02d}"
    return None


def parse_time(text: str) -> str | None:
    if not text:
        return None
    m = _TIME_PATTERN.search(text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def parse_score(text: str) -> tuple[list[int], str] | None:
    """Return (score_ft, status) if the cell is a final score, else None."""
    if not text:
        return None
    m = _SCORE_PATTERN.match(text.strip())
    if m:
        return ([int(m.group(1)), int(m.group(2))], "finished")
    return None


def make_kickoff_utc(date: str, time_local: str | None) -> str | None:
    """Return a naive ISO-8601 kickoff timestamp if time is known.
    We intentionally don't append 'Z' or a timezone offset because the
    upstream time is local, not UTC. merger.py / EPG enrichment resolves
    the true UTC timestamp downstream."""
    if not time_local:
        return None
    return f"{date}T{time_local}:00"


# ---------------------------------------------------------------------------
# Date window helper — used by BBC and Sky scrapers to pick which daily
# pages to fetch. We honour the same 30-day rolling window used elsewhere
# in the project.
# ---------------------------------------------------------------------------

def date_window(days_ahead: int = 30, today: datetime | None = None) -> list[str]:
    """Return a list of YYYY-MM-DD date strings covering today through
    today+days_ahead inclusive."""
    from datetime import timedelta
    t = (today or datetime.now(timezone.utc)).date()
    return [(t + timedelta(days=d)).isoformat() for d in range(days_ahead + 1)]


def current_cup_season(today: datetime | None = None) -> str:
    """Return 'YYYY-YY' season slug. Same rollover as openfootball."""
    t = today or datetime.now(timezone.utc)
    year = t.year
    if t.month < 7:
        start = year - 1
    else:
        start = year
    return f"{start}-{str(start + 1)[-2:]}"
