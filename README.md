# TVsport.live — openfootball + three-way cup scraper

Extends your existing `merger.py` pipeline to cover English lower
leagues, Scottish football, top-5 European leagues, and the four major
British knockout cups. Cup fixtures are fetched from **BBC Sport, Sky
Sports, and Wikipedia in parallel** and merged with source precedence,
so no single site going down breaks your cup coverage. Still £0/month.

## What's in the zip

    scraper/sources/openfootball_fetcher.py       # 18 leagues
    scraper/sources/cups/_common.py               # shared types + team aliases
    scraper/sources/cups/bbc_cups.py              # BBC Sport (primary)
    scraper/sources/cups/sky_cups.py              # Sky Sports (secondary)
    scraper/sources/cups/wikipedia_cups.py        # Wikipedia (backup)
    scraper/sources/cups/cup_fetcher.py           # orchestrator
    scraper/sources/cups/__init__.py
    scraper/sources/__init__.py
    MERGER_INTEGRATION_PATCH.md                   # step-by-step guide
    README.md

## Quick start

1. Unzip into your `tvsport_clean/` folder — paths are pre-aligned
2. Read `MERGER_INTEGRATION_PATCH.md` — two import lines plus two
   fetcher calls in `merger.py` is the whole code change
3. Install `lxml` if not already present: `pip install lxml`
4. Test locally:

       cd scraper
       python -m sources.openfootball_fetcher --competition EPL
       python -m sources.cups.cup_fetcher

5. Commit and push — your existing GitHub Actions workflow picks it up
   on the next nightly run

## What you get

**New league coverage:**
EFL Championship, League One, League Two, National League,
Scottish Premiership, Bundesliga 1/2/3, La Liga 1/2, Serie A/B,
Ligue 1/2, Eredivisie, Primeira Liga, Brasileirão.

**New cup coverage:**
FA Cup, EFL Cup (Carabao), Scottish Cup, Scottish League Cup — all
rounds from first proper through final, pulled from BBC + Sky +
Wikipedia and reconciled.

**Zero single points of failure** on the cup side. If BBC redesigns
their HTML, Sky + Wikipedia carry the load. If Wikipedia changes its
wikitable conventions, BBC + Sky carry the load. All three would have
to break simultaneously for cup coverage to go dark.

**Still £0/month.**

## How the orchestrator decides

Source precedence is **BBC > Sky > Wikipedia** because that matches
the "quality for kickoff times" order.

For each fixture (identified by a normalised team-alias-aware dedupe
key), the orchestrator:

1. Starts with the highest-priority source that has it
2. Enriches empty fields from lower-priority sources (BBC time + Wikipedia
   round label)
3. Never overwrites a non-empty field with a lower-priority source
4. Never paints a pre-kickoff time onto a played match
5. Resolves date-slip cases (broadcaster moves a game 1-2 days) by
   preferring the BBC/Sky date when present

Tested against synthetic HTML for all three sources; see the "What the
orchestrator's output looks like" section of the integration patch for
example log output.

## Design notes

All fetchers return the same `Match` dataclass shape (defined in
`_common.py` on the cup side, mirrored in `openfootball_fetcher.py`).
merger.py can treat them identically.

Both fetchers fail open — if openfootball hasn't published a season
yet, or one of the cup sources changes its HTML, the affected fetcher
returns an empty list instead of crashing, and the rest of your
pipeline keeps working.

openfootball times are local to the competition. Cup scrapers emit
local times too. If you need strict UTC, enrich downstream with EPG
data as you already do.
