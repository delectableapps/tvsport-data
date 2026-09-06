#!/usr/bin/env python3
"""
rugby_liveonsat_audit.py
------------------------
Sanity-check report for the RUGBY pipeline: compares what liveonsat's
rugby page (x-rugby-union.php) lists against (a) the fixtures we publish
in output/rugby_fixtures.json and (b) the static rights tables in
rugby_rights_db.py. Nothing here changes site data.

Usage:
    python scraper/rugby_liveonsat_audit.py
    python scraper/rugby_liveonsat_audit.py --fixtures output/rugby_fixtures.json \
        --liveonsat output/liveonsat.json --out output/rugby_liveonsat_audit.md

Sections:
  1. Primary-source gaps   — fixtures only liveonsat had (TheSportsDB missed
                             them; they were backfilled with needs_review)
  2. Not on liveonsat      — fixtures we publish that liveonsat doesn't list
                             (fine before liveonsat adds them; suspicious if
                             the match is within 7 days)
  3. Rights vs liveonsat   — per matched fixture, per key territory:
                             MISMATCH  rights table says X, liveonsat shows Y
                             GAP       liveonsat shows a territory we have no
                                       rights row for
                             OVER-CLAIM rights table lists a broadcaster but
                                       liveonsat (which is dense for that
                                       territory/competition) shows none
  4. Unknown channels      — liveonsat channel names our classifier can't
                             place (add to RUGBY_CHANNEL_RULES)
  5. Out-of-scope          — competitions on the page we don't publish
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rugby_merger import (los_comp_code, classify_rugby_channel, rugby_norm,   # noqa: E402
                          RugbyLosIndex)
from rugby_rights_db import RUGBY_COMPETITIONS, get_rights_map              # noqa: E402

DEF_FIXTURES = os.path.join(HERE, "..", "output", "rugby_fixtures.json")
DEF_LIVEONSAT = os.path.join(HERE, "..", "output", "liveonsat.json")
DEF_OUT = os.path.join(HERE, "..", "output", "rugby_liveonsat_audit.md")

KEY_TERRITORIES = ["United Kingdom", "Republic of Ireland", "France", "Italy",
                   "South Africa", "Australia", "New Zealand", "United States", "Japan"]
SPARSE_THRESHOLD = 0.25   # liveonsat lists territory on < 25% of comp's matches → no OVER-CLAIM

ALIASES = {
    "premier sports ireland": "premier sports", "sky sport italia": "sky italia",
    "nbc sports / peacock": "peacock", "florugby (flosports)": "florugby",
    "channel 9": "nine network", "rugbypass": "rugbypass tv",
}


def canon(b: str) -> str:
    b = (b or "").strip().lower()
    return ALIASES.get(b, b)


def rights_broadcasters(code: str, territory: str) -> set:
    row = get_rights_map(code).get(territory)
    if not row:
        return set()
    return {canon(x) for x in row["broadcaster"].split(";") if x.strip()}


def los_broadcasters(row: dict, territory: str) -> set:
    out = set()
    for ch in row.get("channels", []):
        t, b = classify_rugby_channel(ch["name"])
        if t == territory:
            out.add(canon(b))
    return out


def run(fixtures_path, liveonsat_path, out_path):
    lines = []
    P = lines.append
    now = datetime.now(timezone.utc)
    P("# Rugby Union — liveonsat sanity check")
    P(f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')}_\n")

    try:
        los = json.load(open(liveonsat_path, encoding="utf-8"))
    except Exception as e:
        P(f"**liveonsat.json not available** ({e}) — nothing to audit.")
        open(out_path, "w", encoding="utf-8").write("\n".join(lines))
        return
    rows = [r for r in los.get("fixtures", []) if r.get("source_page") == "rugby"]
    P(f"liveonsat rugby page fetched {los.get('fetched_at','?')} — {len(rows)} rows "
      f"(page offset {los.get('pages',{}).get('rugby',{}).get('page_offset','?')})\n")
    if not rows:
        P("**No rugby rows in liveonsat.json** — add `rugby` to the `--pages` list in run_liveonsat.bat.")
        open(out_path, "w", encoding="utf-8").write("\n".join(lines))
        return

    try:
        ours = json.load(open(fixtures_path, encoding="utf-8")).get("fixtures", [])
    except Exception:
        ours = []

    in_scope = [(los_comp_code(r.get("competition", ""), r.get("home", ""), r.get("away", "")), r) for r in rows]
    scoped = [(c, r) for c, r in in_scope if c]
    out_of_scope = Counter(r.get("competition", "?") for c, r in in_scope if not c)
    idx = RugbyLosIndex([r for c, r in scoped])

    # 1. primary-source gaps
    P("## 1. Fixtures only liveonsat had (TheSportsDB gaps — backfilled, needs_review)")
    gaps = [f for f in ours if f.get("source") == "liveonsat"]
    if gaps:
        by = Counter(f["competition"] for f in gaps)
        P("| Competition | Count |\n|---|---|")
        for c, n in sorted(by.items()):
            P(f"| {c} | {n} |")
        P("")
        for f in gaps[:40]:
            P(f"- {f['competition']}: **{f['home_team']} v {f['away_team']}** {f['kickoff'][:16]}Z")
        if len(gaps) > 40:
            P(f"- … and {len(gaps)-40} more")
    else:
        P("None — every in-scope liveonsat fixture was already in TheSportsDB.")
    P("")

    # 2. ours not on liveonsat
    P("## 2. Fixtures we publish that liveonsat does not list")
    missing = []
    for f in ours:
        if f.get("source") == "liveonsat":
            continue
        if not idx.find(f["home_team"], f["away_team"], f["kickoff"]):
            missing.append(f)
    if missing:
        by = Counter(f["competition"] for f in missing)
        P("| Competition | Count | Note |\n|---|---|---|")
        for c, n in sorted(by.items()):
            P(f"| {c} | {n} | liveonsat usually lists a competition 1–3 weeks out |")
        soon = [f for f in missing if (datetime.fromisoformat(f["kickoff"].replace("Z", "+00:00")) - now).days <= 7]
        if soon:
            P("\n**Within 7 days and still not on liveonsat — check team names / kick-off:**")
            for f in soon:
                P(f"- {f['competition']}: {f['home_team']} v {f['away_team']} {f['kickoff'][:16]}Z")
    else:
        P("None.")
    P("")

    # 3. rights vs liveonsat
    P("## 3. Static rights tables vs liveonsat channels (key territories)")
    density = defaultdict(lambda: defaultdict(int))
    comp_n = Counter()
    for c, r in scoped:
        comp_n[c] += 1
        seen = set()
        for ch in r.get("channels", []):
            t, _ = classify_rugby_channel(ch["name"])
            if t and t not in seen:
                density[c][t] += 1
                seen.add(t)
    issues = defaultdict(list)
    for c, r in scoped:
        for terr in KEY_TERRITORIES:
            ours_set = rights_broadcasters(c, terr)
            los_set = los_broadcasters(r, terr)
            dense = comp_n[c] and density[c][terr] / comp_n[c] >= SPARSE_THRESHOLD
            label = f"{r['home']} v {r['away']} {r['kickoff_utc'][:10]}"
            if los_set and not ours_set:
                issues[(c, terr, "GAP")].append(f"{label}: liveonsat {sorted(los_set)}")
            elif los_set and ours_set and not (los_set & ours_set):
                issues[(c, terr, "MISMATCH")].append(f"{label}: rights {sorted(ours_set)} vs liveonsat {sorted(los_set)}")
            elif ours_set and not los_set and dense:
                issues[(c, terr, "OVER-CLAIM")].append(f"{label}: rights {sorted(ours_set)}, liveonsat none")
    if issues:
        for (c, terr, kind), items in sorted(issues.items()):
            P(f"### {RUGBY_COMPETITIONS[c]['display']} — {terr} — {kind} ({len(items)})")
            for it in items[:6]:
                P(f"- {it}")
            if len(items) > 6:
                P(f"- … {len(items)-6} more")
            P("")
    else:
        P("No disagreements in key territories.\n")
    P("### liveonsat territory density per competition (share of matches with a listed channel)")
    P("| Competition | " + " | ".join(KEY_TERRITORIES) + " |")
    P("|---|" + "---|" * len(KEY_TERRITORIES))
    for c in sorted(comp_n):
        P(f"| {RUGBY_COMPETITIONS[c]['display']} ({comp_n[c]}) | " +
          " | ".join(f"{100*density[c][t]/comp_n[c]:.0f}%" for t in KEY_TERRITORIES) + " |")
    P("")

    # 4. unknown channels
    P("## 4. liveonsat channel names our classifier cannot place")
    unknown = Counter()
    for c, r in scoped:
        for ch in r.get("channels", []):
            t, _ = classify_rugby_channel(ch["name"])
            if not t:
                unknown[ch["name"]] += 1
    if unknown:
        P("| Channel | Seen |\n|---|---|")
        for n, k in unknown.most_common():
            P(f"| {n} | {k} |")
    else:
        P("None — every channel on in-scope fixtures was classified.")
    P("")

    # 5. out of scope
    P("## 5. Competitions on the page we do not publish")
    if out_of_scope:
        P("| Competition | Fixtures |\n|---|---|")
        for n, k in out_of_scope.most_common():
            P(f"| {n} | {k} |")
    else:
        P("None.")
    P("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=DEF_FIXTURES)
    ap.add_argument("--liveonsat", default=DEF_LIVEONSAT)
    ap.add_argument("--out", default=DEF_OUT)
    a = ap.parse_args()
    run(a.fixtures, a.liveonsat, a.out)


if __name__ == "__main__":
    main()
