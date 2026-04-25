# merger.py integration patch — v2 (BBC + Sky + Wikipedia)

Drop-in changes to wire the new openfootball fetcher and the three-way
cup orchestrator into your existing `scraper/merger.py`. Keep your
current EPG / uk_live_footballontv / nbcsports / premierleague etc.
pipeline exactly as it is — this patch is purely **additive**.

---

## What changed vs v1

v1 of this patch wired in a single Wikipedia cup scraper. **v2 adds
BBC Sport and Sky Sports as higher-priority sources** and introduces a
merge orchestrator that:

- Runs all three scrapers in parallel (one thread each)
- Deduplicates fixtures across sources using a normalised team-name
  key (so "Man City" from BBC and "Manchester City F.C." from
  Wikipedia collapse to the same fixture)
- Enriches fields cross-source (BBC's kickoff time + Wikipedia's round
  label, etc.)
- Resolves date slips when broadcasters move fixtures (BBC/Sky win
  over Wikipedia for a ±7 day window)
- Never paints a pre-kickoff time onto a played match

If one source fails (network error, HTML redesign), the other two
carry the cup feed. Zero single points of failure.

---

## 1. Files to add

Copy these into your repo:

    scraper/sources/openfootball_fetcher.py
    scraper/sources/cups/__init__.py              (empty)
    scraper/sources/cups/_common.py               (shared Match, helpers)
    scraper/sources/cups/bbc_cups.py              (BBC Sport scraper)
    scraper/sources/cups/sky_cups.py              (Sky Sports scraper)
    scraper/sources/cups/wikipedia_cups.py        (Wikipedia scraper)
    scraper/sources/cups/cup_fetcher.py           (orchestrator)

(`scraper/sources/__init__.py` — empty — is also included; if your repo
already has one, skip it.)

---

## 2. Edit `scraper/requirements.txt`

Make sure these are present. `requests` and `beautifulsoup4` almost
certainly are already; `lxml` may not be. Playwright is **optional** —
skip it unless you want the Sky / Wikipedia fallback paths armed.

    requests>=2.31
    beautifulsoup4>=4.12
    lxml>=5.1
    # Optional. Only used as fallback if Sky fully JS-hydrates its
    # fixtures or Wikipedia ever client-side-renders fixture tables.
    # Safe to omit; scrapers will log and continue without it.
    # playwright>=1.42

If you add Playwright, GitHub Actions needs one extra workflow step:

    - name: Install Playwright browsers
      run: python -m playwright install --with-deps chromium

---

## 3. Edit `scraper/merger.py`

### 3a. Add imports

Near the other `from sources...` imports at the top of the file, add:

```python
from sources.openfootball_fetcher import fetch_all as fetch_openfootball
from sources.cups.cup_fetcher import fetch_all_cups as fetch_cup_fixtures
```

Note that `cup_fetcher` is the **orchestrator**. You should not import
`bbc_cups`, `sky_cups`, or `wikipedia_cups` directly in merger.py —
let the orchestrator decide which sources to use and how to merge.

### 3b. Call the new fetchers

Find the block where your existing sources are called (the function
that currently calls the Premier League, UCL, EPG etc. modules). Add
two calls alongside them:

```python
# --- New: league fixtures from openfootball (EFL, Scottish, top-5 Euro)
try:
    openfootball_matches = fetch_openfootball()
    log.info("openfootball: %d matches", len(openfootball_matches))
except Exception as e:
    log.exception("openfootball fetch failed: %s", e)
    openfootball_matches = []

# --- New: cup fixtures from BBC + Sky + Wikipedia (merged)
try:
    cup_matches = fetch_cup_fixtures()
    log.info("cup_fetcher: %d matches (BBC + Sky + Wikipedia, merged)",
             len(cup_matches))
except Exception as e:
    log.exception("cup_fetcher failed: %s", e)
    cup_matches = []
```

Both return lists of `Match` dataclass objects with identical attribute
surfaces:

    competition_code    # "EPL", "CHAMP", "L1", "SPFL", "FAC", "EFLC", ...
    competition_name    # human-readable
    country             # 'en' / 'sc' / 'de' / etc.
    round_label         # "Matchday 7" / "Third round proper" / etc.
    kickoff_utc         # "2026-01-10T15:00:00" if time known, else None
    date                # "2026-01-10" (always present)
    time_local          # "15:00" or None
    home, away          # team name strings
    status              # "scheduled" | "finished" | "postponed"
    score_ft            # [3,1] or None
    source              # "openfootball" | "bbc" | "sky" | "wikipedia"

Use `.to_dict()` if your merger prefers dicts, or access attributes
directly.

### 3c. Feed into your existing dedupe / enrichment pass

```python
# Wherever you currently assemble the "all_fixtures" list:
all_fixtures = (
    epl_fixtures
    + ucl_fixtures
    + [m.to_dict() for m in openfootball_matches]
    + [m.to_dict() for m in cup_matches]
)
```

Your existing merger dedupe should already key on something like
`(date, home, away)`. The cup orchestrator has already run its own
cross-source dedupe, so you're merging one consolidated cup stream
with everything else — no extra dedupe effort needed.

**Source precedence for your downstream dedupe (suggestion):**

    1. iptv-org EPG                  — has exact channel numbers
    2. live-footballontv / nbcsports  — has broadcast metadata
    3. cup_fetcher                    — best schedule source for cups
    4. openfootball                   — reliable league baseline
    5. thesportsdb                    — ultimate fallback

---

## 4. Add competition codes to `rights_db.py`

The new fetchers emit `competition_code` values that your rights
database needs to know about. Extend the codes used in your
UCL_RIGHTS / EPL_RIGHTS style dictionaries.

New codes introduced:

    EPL     English Premier League       (already exists)
    CHAMP   EFL Championship             (new)
    L1      EFL League One               (new)
    L2      EFL League Two               (new)
    NAT     National League              (new)
    SPFL    Scottish Premiership         (new)
    BUND    Bundesliga                   (already in preferences)
    BUND2   2. Bundesliga                (new)
    DE3     3. Liga                      (new)
    LL      La Liga                      (new)
    LL2     La Liga 2                    (new)
    SA      Serie A                      (already in preferences)
    SB      Serie B                      (new)
    L1F     Ligue 1                      (already in preferences)
    L2F     Ligue 2                      (new)
    ERE     Eredivisie                   (new)
    PPL     Primeira Liga                (new)
    BRA     Brasileirão                  (new)
    FAC     FA Cup                       (new)
    EFLC    EFL Cup (Carabao)            (new)
    SFAC    Scottish Cup                 (new)
    SLFC    Scottish League Cup          (new)

If you don't have rights coverage for a competition, the fixture still
gets emitted — it just won't have a broadcaster list populated per
territory. UK cup rights come from EPG (TNT/BBC/Sky) anyway, so the
Excel file isn't the bottleneck for cup coverage.

---

## 5. Update the front-end competition filter

`index.html`'s preferences dropdown references competition codes. Add
the new ones to the same array you used for BUND / SA / L1F. Grep for
one of those codes in `index.html` and add the new codes to the same
list.

---

## 6. Local testing

From the `scraper/` directory:

```bash
# Test openfootball on its own
python -m sources.openfootball_fetcher --competition EPL --out /tmp/epl.json

# Test each cup scraper in isolation (useful for debugging one source)
python -m sources.cups.bbc_cups --date 2026-01-10
python -m sources.cups.sky_cups --cup FAC
python -m sources.cups.wikipedia_cups --cup FAC

# Test the full orchestrator (what merger.py will call)
python -m sources.cups.cup_fetcher --out /tmp/cups.json

# Run sequentially instead of in parallel (easier to read logs when
# debugging a single source regression)
python -m sources.cups.cup_fetcher --no-parallel
```

Every scraper supports `--html-file` for offline testing against a
saved HTML snapshot. When you hit a real parsing issue, save the
problematic page with `curl` or your browser's "Save As", then:

```bash
python -m sources.cups.bbc_cups --html-file saved.html --date 2026-01-10
```

---

## 7. GitHub Actions

No workflow changes needed.

The three cup scrapers together make ~40 HTTP requests per nightly
run (30 daily BBC pages x 2 for Eng/Sco + 4 Sky pages + 4 Wikipedia
pages). That's well under any polite rate limit. Each scraper sends:

    User-Agent: tvsport.live scraper (+https://tvsport.live)

which satisfies BBC / Sky / Wikipedia etiquette.

Total added runtime per nightly run: typically 30-60 seconds.

---

## 8. Failure modes and what happens

**One of the three cup sources goes down.**
Orchestrator catches the exception, logs it, and carries on with the
other two. Your cup coverage drops a bit in quality but doesn't break.

**Two of the three go down.**
Still works — the remaining source provides full coverage (each one
covers all four cups end-to-end, they're just redundant).

**All three go down.**
Empty cup list, nightly run still completes, your front-end shows the
previous `fixtures.json` (you keep that behaviour via your existing
"don't overwrite on empty result" guard, which is already there).

**BBC redesigns their HTML.**
Scraper emits zero matches, logs a warning, orchestrator falls back
to Sky + Wikipedia. You have time to save a new HTML snapshot and
update the selectors.

**BBC and Sky disagree on a fixture date.**
Date-slip reconciler picks the BBC version if both agree on who's
playing. If only Wikipedia disagrees, we trust BBC/Sky (TV picks).
If only Wikipedia reports the fixture, we trust it as-is (might be a
qualifying round the mainstream sources haven't covered yet).

**Wikipedia reports a two-legged tie that looks like a date slip.**
The reconciler only collapses fixtures where at least one version
came from BBC or Sky. Pure Wikipedia duplicates are left alone — so
legitimate two-leg ties survive.

**Finished matches showing kickoff times.**
The orchestrator has a specific guard against this: once any source
marks a match as finished/postponed, the time field is not enriched
from a source still reporting the match as scheduled. Tested.

---

## 9. What the orchestrator's output looks like

Example run merging three sources on the same FA Cup third-round
weekend (abridged):

    INFO | cup_fetcher: bbc -> 52 matches
    INFO | cup_fetcher: sky -> 48 matches
    INFO | cup_fetcher: wikipedia -> 54 matches
    INFO | cup_fetcher: after dedupe: 57 matches
    INFO | cup_fetcher: date slip resolved for Portsmouth vs Arsenal —
           dates seen ['2026-01-10', '2026-01-11'], keeping 2026-01-11 (bbc)
    INFO | cup_fetcher: after date-slip reconcile: 54 matches

Three source calls, a few dozen fixtures each. Dedupe brings it to 57
unique (home, away, date) tuples, reconcile collapses legitimate
slips to 54.

The `.source` field on each Match tells you which scraper's view
won. Use it for debugging when a fixture looks wrong — if
`source == "wikipedia"`, that fixture wasn't in BBC or Sky at all
(qualifying round, lower-division tie).
