#!/usr/bin/env python3
"""
audit_fixtures.py
-----------------
Post-build QA on output/fixtures.json. Catches the data-quality regressions
that have bitten this project before, so they surface in the GitHub Actions
log instead of on the live site.

Run at the end of the nightly workflow:
    python scraper/audit_fixtures.py                 # warn only (exit 0)
    python scraper/audit_fixtures.py --strict        # exit 1 on any ERROR

Checks:
  1. Foreign fixtures mis-tagged into UK/Scottish cup competitions
     (the Groningen-as-Scottish-Cup / Rio Ave-as-FA-Cup class of bug)
  2. "Leakage" competitions with implausibly few fixtures
  3. Cup qualifying rounds carrying full national-broadcaster sets
  4. Duplicate fixtures across competitions (same teams, same day)
  5. Territories appearing with a broadcaster from the wrong country
     (the Sky Deutschland-on-Ireland class of bug)
  6. Blackout sanity: no UK live broadcaster on a 3pm Saturday EPL match
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "output",
                            "fixtures.json")

# Competitions that should only ever contain clubs from these countries.
DOMESTIC_COMPS = {
    "FA Cup":              "england",
    "EFL Cup":             "england",
    "Championship":        "england",
    "League One":          "england",
    "League Two":          "england",
    "National League":     "england",
    "Premier League":      "england",
    "Scottish Cup":        "scotland",
    "Scottish Premiership":"scotland",
    "Scottish Championship":"scotland",
    "Scottish League Cup": "scotland",
}

# Tokens that betray a non-British club sitting in a British competition.
FOREIGN_TOKENS = re.compile(
    r"\b(groningen|fortuna|sittard|ajax|psv|feyenoord|utrecht|twente|"
    r"heerenveen|zwolle|excelsior|sparta rotterdam|willem|telstar|nec|az\b|"
    r"genk|beveren|anderlecht|brugge|gent|standard|"
    r"rio ave|sporting cp|sporting clube|sporting braga|sporting lisbon|"
    r"fc porto|benfica|sc braga|guimaraes|vitoria sc|casa pia|"
    r"famalicao|arouca|estoril|moreirense|nacional|santa clara|alverca|"
    r"maritimo|gil vicente|estrela|"
    r"barcelona|madrid|sevilla|betis|valencia|villarreal|osasuna|celta|"
    r"alaves|espanyol|getafe|levante|elche|malaga|racing santander|"
    r"deportivo la coruna|rayo vallecano|"
    r"bayern|dortmund|leipzig|leverkusen|schalke|hamburger|stuttgart|"
    r"frankfurt|hoffenheim|freiburg|werder|augsburg|mainz|paderborn|"
    r"union berlin|elversberg|monchengladbach|koln|"
    r"juventus|milan|inter|napoli|roma|lazio|atalanta|fiorentina|torino|"
    r"udinese|sassuolo|bologna|cagliari|genoa|lecce|monza|parma|venezia|"
    r"frosinone|como|"
    r"psg|paris saint|marseille|monaco|lyon|lille|lens|rennes|nice|brest|"
    r"toulouse|auxerre|angers|lorient|troyes|strasbourg|le havre|le mans)\b",
    re.I)

# Broadcaster → the territory it legitimately belongs to. Anything appearing
# under a different territory is a normaliser/rendering bug.
# broadcaster -> (home territory, additional territories it legitimately serves)
BROADCASTER_EXTRA_TERRITORIES = {
    "Sky Deutschland": {"Austria", "Switzerland"},
    "Canal+":          {"Belgium", "Switzerland", "Luxembourg"},
    "Movistar LaLiga": {"Andorra"},
    "Sport TV":        {"Angola", "Mozambique"},
}

BROADCASTER_HOME = {
    "Sky Deutschland": "Germany",
    "WOW": "Germany",
    "Magenta Sport": "Germany",
    "Sky Sport Italia": "Italy",
    "DAZN IT": "Italy",
    "Ligue 1+": "France",
    "Canal+": "France",
    "Movistar LaLiga": "Spain",
    "DAZN LaLiga": "Spain",
    "ESPN NL": "Netherlands",
    "Ziggo Sport": "Netherlands",
    "Sport TV": "Portugal",
    "DAZN PT": "Portugal",
    "Virgin Media": "Republic of Ireland",
    "LOI TV": "Republic of Ireland",
    "TNT Sports": None,   # legitimately multi-territory (UK + ROI)
    "Sky Sports": None,
    "Premier Sports": None,
    "BBC": None,
    "ITV": None,
}

# Cup rounds that are NOT nationally televised — full broadcaster sets here
# mean rights are being applied without a stage filter.
UNTELEVISED_ROUND = re.compile(
    r"qualifying|preliminary|extra preliminary|first round qualifying|"
    r"1st qualifying|2nd qualifying|3rd qualifying|4th qualifying|"
    r"first round|preliminary round", re.I)

MAJOR_UK_BROADCASTERS = {"BBC", "ITV", "TNT Sports", "Sky Sports",
                         "Premier Sports"}

errors: list[str] = []
warnings: list[str] = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def check_foreign_in_domestic(fixtures):
    hits = []
    for f in fixtures:
        comp = f.get("competition", "")
        if comp not in DOMESTIC_COMPS:
            continue
        for side in ("home_team", "away_team"):
            name = f.get(side, "")
            if FOREIGN_TOKENS.search(name):
                hits.append((comp, f.get("home_team"), f.get("away_team"),
                             f.get("kickoff", "")[:10]))
                break
    for comp, h, a, d in hits:
        err(f"FOREIGN CLUB in {comp}: {h} v {a} ({d}) — "
            f"likely cup-scraper leakage")
    return hits


def check_leakage_comps(fixtures, threshold=3):
    counts = Counter(f.get("competition", "") for f in fixtures)
    for comp, n in sorted(counts.items()):
        if n <= threshold:
            warn(f"THIN COMPETITION '{comp}': only {n} fixture(s) — "
                 f"either not being scraped systematically, or leakage")


def check_cup_round_rights(fixtures):
    flagged = 0
    for f in fixtures:
        stage = f"{f.get('stage','')} {f.get('group','') or ''} " \
                f"{f.get('round','') or ''}"
        if not UNTELEVISED_ROUND.search(stage):
            continue
        majors = {b.get("broadcaster") for b in f.get("broadcasters", [])
                  if b.get("territory") == "United Kingdom"}
        overlap = majors & MAJOR_UK_BROADCASTERS
        if overlap:
            flagged += 1
            if flagged <= 5:
                err(f"UNTELEVISED ROUND with national rights: "
                    f"{f.get('home_team')} v {f.get('away_team')} "
                    f"[{f.get('competition')} / {stage.strip()}] "
                    f"-> {sorted(overlap)}")
    if flagged > 5:
        err(f"...and {flagged - 5} more fixtures in untelevised rounds "
            f"carrying national broadcaster rights")


def check_duplicates(fixtures):
    by_pair = defaultdict(list)
    for f in fixtures:
        key = (f.get("home_team", "").lower(),
               f.get("away_team", "").lower(),
               f.get("kickoff", "")[:10])
        by_pair[key].append(f.get("competition", ""))
    for (h, a, d), comps in by_pair.items():
        if len(comps) > 1:
            err(f"DUPLICATE FIXTURE: {h} v {a} ({d}) appears in "
                f"{sorted(set(comps))}")


def check_territory_broadcaster_mismatch(fixtures):
    seen = set()
    for f in fixtures:
        for b in f.get("broadcasters", []):
            bc = b.get("broadcaster", "")
            terr = b.get("territory", "")
            home = BROADCASTER_HOME.get(bc)
            allowed = BROADCASTER_EXTRA_TERRITORIES.get(bc, set())
            if home and terr != home and terr not in allowed:
                key = (bc, terr)
                if key in seen:
                    continue
                seen.add(key)
                err(f"BROADCASTER/TERRITORY MISMATCH: '{bc}' listed under "
                    f"'{terr}' (belongs to {home}) — e.g. "
                    f"{f.get('home_team')} v {f.get('away_team')}")


def check_blackout_sanity(fixtures):
    for f in fixtures:
        if not f.get("is_blackout"):
            continue
        live_uk = [b for b in f.get("broadcasters", [])
                   if b.get("territory") == "United Kingdom"
                   and b.get("coverage") == "live"]
        if live_uk:
            err(f"BLACKOUT VIOLATION: {f.get('home_team')} v "
                f"{f.get('away_team')} is a 3pm blackout but lists live UK "
                f"broadcaster(s) {[b['broadcaster'] for b in live_uk]}")


def check_ireland_coverage(fixtures):
    """3pm blackout EPL matches: Ireland should be either liveonsat-confirmed
    or absent — never rights-guessed."""
    guessed = 0
    for f in fixtures:
        if not f.get("is_blackout"):
            continue
        for b in f.get("broadcasters", []):
            if b.get("territory") == "Republic of Ireland" \
                    and b.get("source") == "rights":
                guessed += 1
                break
    if guessed:
        err(f"ROI GUESSWORK: {guessed} blackout-slot fixtures assign an Irish "
            f"broadcaster from static rights (should be liveonsat/EPG "
            f"confirmed, or omitted)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any ERROR is raised")
    args = ap.parse_args()

    with open(args.path, encoding="utf-8") as fh:
        data = json.load(fh)
    fixtures = data.get("fixtures", [])

    print("=" * 66)
    print(f"FIXTURE AUDIT — {len(fixtures)} fixtures "
          f"(generated {data.get('generated_at')})")
    print("=" * 66)

    check_foreign_in_domestic(fixtures)
    check_leakage_comps(fixtures)
    check_cup_round_rights(fixtures)
    check_duplicates(fixtures)
    check_territory_broadcaster_mismatch(fixtures)
    check_blackout_sanity(fixtures)
    check_ireland_coverage(fixtures)

    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\n{len(warnings)} WARNING(S):")
        for w in warnings:
            print(f"  ! {w}")
    if not errors and not warnings:
        print("\n✓ All checks passed.")

    print("\n" + "=" * 66)
    comps = Counter(f.get("competition", "") for f in fixtures)
    print("Competition breakdown:")
    for comp, n in comps.most_common():
        print(f"  {n:4}  {comp}")
    print("=" * 66)

    if errors and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
