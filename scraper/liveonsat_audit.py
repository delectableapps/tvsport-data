#!/usr/bin/env python3
"""
liveonsat_audit.py
------------------
VALIDATION report: compares output/fixtures.json (built from EPG, broadcaster
sites and static rights) against liveonsat.json (independent listings) and
reports where they disagree.

liveonsat is treated as a *check*, not a source. Nothing here changes the
site's data; it tells you where your primary sources have gaps or errors so
you can fix them at source (EPG mapping, rights_db, channel_normaliser).

Usage:
    python scraper/liveonsat_audit.py                       # defaults below
    python scraper/liveonsat_audit.py --fixtures output/fixtures.json \\
                                      --liveonsat output/liveonsat.json \\
                                      --out output/liveonsat_audit.md

Sections in the report:
  1. Coverage gaps     — matches liveonsat lists, in competitions we cover,
                         that are missing from fixtures.json
  2. Broadcaster diffs — per matched fixture, per key territory:
                         OVER-CLAIM  we list a broadcaster, liveonsat shows none
                         GAP         liveonsat shows one, we list nothing
                         MISMATCH    both list, but different broadcasters
  3. ROI 3pm picks     — which Saturday-3pm EPL match Premier Sports Ireland
                         has selected, vs what we publish
  4. Unknown channels  — liveonsat channel names our classifier can't place
                         (feed these into channel_normaliser / the rules table)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liveonsat_match import LiveOnSatIndex, classify_channel, normalise_team  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_FIXTURES = os.path.join(HERE, "..", "output", "fixtures.json")
DEF_LIVEONSAT = os.path.join(HERE, "..", "output", "liveonsat.json")
DEF_OUT = os.path.join(HERE, "..", "output", "liveonsat_audit.md")

# liveonsat competition name -> our canonical competition name.
# Only competitions we actually publish are mapped; the rest are reported as
# "not covered" so you can decide whether to add them.
COMP_MAP = {
    "English Premier League":  "Premier League",
    "English Championship":    "Championship",
    "English League One":      "League One",
    "English League Two":      "League Two",
    "English League Cup":      "EFL Cup",
    "English FA Cup":          "FA Cup",
    "English National League": "National League",
    "Scottish Premiership":    "Scottish Premiership",
    "Scottish Championship":   "Scottish Championship",
    "Scottish Cup":            "Scottish Cup",
    "Scottish League Cup":     "Scottish League Cup",
    "UEFA Champions League":   "UEFA Champions League",
    "German Bundesliga":       "Bundesliga",
    "Italian Serie A":         "Serie A",
    "French Ligue 1":          "Ligue 1",
    "Spanish La Liga":         "La Liga",
    "Spanish LaLiga":          "La Liga",
    "Dutch Eredivisie":        "Eredivisie",
    "Portuguese Primeira Liga":"Primeira Liga",
    "Portuguese Liga":         "Primeira Liga",
}

# Territories we audit broadcaster-by-broadcaster. Others are ignored here.
AUDIT_TERRITORIES = [
    "United Kingdom", "Republic of Ireland", "Germany", "Italy",
    "France", "Spain", "Netherlands", "Portugal",
]

# Broadcaster names that mean the same thing on both sides
BROADCASTER_ALIASES = {
    "sky deutschland": "sky", "sky bundesliga": "sky", "sky sports": "sky",
    "sky sport italia": "sky", "sky sport": "sky",
    "dazn gb": "dazn", "dazn ireland": "dazn", "dazn it": "dazn",
    "dazn pt": "dazn", "dazn france": "dazn", "dazn laliga": "dazn",
    "dazn / fubo": "dazn",
    "premier sports": "premier sports",
    "tnt sports": "tnt", "discovery+": "tnt",
    "canal+": "canal+", "canal+ sport fr": "canal+",
    "bein sports fr": "bein", "bein sports": "bein",
    "movistar laliga": "movistar", "movistar plus": "movistar",
    "espn nl": "espn", "espn nl eredivisie": "espn",
    "sport tv": "sport tv", "ligue 1+": "ligue 1+",
    "bbc": "bbc", "bbc ni": "bbc", "bbc alba": "bbc", "bbc scotland": "bbc",
    "itv": "itv", "sky sports+": "sky", "sky sports plus": "sky",
    "viaplay nl": "viaplay", "viaplay": "viaplay", "ziggo sport": "ziggo",
    "prime video": "prime", "prime video uk (ppv)": "prime",
    "wow": "sky",  # WOW is Sky's streaming brand
}


def _canon(b: str) -> str:
    b = (b or "").strip().lower()
    return BROADCASTER_ALIASES.get(b, b)


def _our_broadcasters(fixture: dict, territory: str) -> set:
    out = set()
    for b in fixture.get("broadcasters", []):
        if b.get("territory") == territory and b.get("coverage", "live") == "live":
            for part in str(b.get("broadcaster", "")).split(";"):
                if part.strip():
                    out.add(_canon(part))
    return out


# Broadcasters whose UK channels are carried identically in Ireland.
UK_AND_IRELAND = {"sky", "tnt"}


def _los_broadcasters(row: dict, territory: str) -> set:
    out = set()
    for ch in row.get("channels", []):
        t, b = classify_channel(ch["name"])
        if t == territory:
            out.add(_canon(b))
        elif territory == "Republic of Ireland" and t == "United Kingdom" \
                and _canon(b) in UK_AND_IRELAND:
            out.add(_canon(b))
    return out


# If liveonsat lists a territory on fewer than this share of a competition's
# matches, it is being treated as *sparse* there: "liveonsat lists nothing"
# is then no evidence of anything, so OVER-CLAIM is not reported.
SPARSE_THRESHOLD = 0.25


def _date_of(iso: str) -> str:
    return (iso or "")[:10]


def run(fixtures_path: str, liveonsat_path: str, out_path: str):
    fx_doc = json.load(open(fixtures_path, encoding="utf-8"))
    los_doc = json.load(open(liveonsat_path, encoding="utf-8"))
    fixtures = fx_doc.get("fixtures", [])
    los_rows = los_doc.get("fixtures", [])
    idx = LiveOnSatIndex(los_rows)

    lines = []
    P = lines.append
    P(f"# liveonsat validation report")
    P(f"")
    P(f"- fixtures.json: **{len(fixtures)}** fixtures "
      f"(generated {fx_doc.get('generated_at')})")
    P(f"- liveonsat.json: **{len(los_rows)}** listings "
      f"(fetched {los_doc.get('fetched_at')}, "
      f"pages: {', '.join(los_doc.get('pages', {}).keys())})")
    P("")

    # ---- Section 0: backfill — what liveonsat ADDED and what it SKIPPED ---
    backfilled = [f for f in fixtures if f.get("source") == "liveonsat"]
    mm_path = os.path.join(os.path.dirname(fixtures_path), "liveonsat_mismatches.json")
    mismatches = []
    if os.path.exists(mm_path):
        try:
            mismatches = json.load(open(mm_path, encoding="utf-8"))
        except Exception:
            mismatches = []

    P("## 0. Backfilled from liveonsat — needs review")
    P("")
    if backfilled:
        P(f"**{len(backfilled)} fixtures are on the site only because liveonsat "
          f"listed them.** Each one means a primary source missed a match. "
          f"They carry `needs_review: true` in fixtures.json.")
        P("")
        by_src = defaultdict(list)
        for f in backfilled:
            by_src[f.get("expected_source") or "unknown"].append(f)
        for src, fs in sorted(by_src.items()):
            P(f"**Should have come from {src}** — {len(fs)}")
            for f in sorted(fs, key=lambda x: x["kickoff"]):
                P(f"- {f['kickoff'][:16].replace('T', ' ')}  [{f['competition']}] "
                  f"{f['home_team']} v {f['away_team']}")
            P("")
    else:
        P("_None — primary sources covered everything liveonsat lists in this window._")
        P("")

    if mismatches:
        P(f"**{len(mismatches)} probable name mismatches (NOT added, to avoid "
          f"duplicates)** — add these pairs to the normaliser aliases:")
        P("")
        P("| Competition | Date | liveonsat says | we have |")
        P("|---|---|---|---|")
        for m in sorted(mismatches, key=lambda x: (x["competition"], x["date"])):
            P(f"| {m['competition']} | {m['date']} | {m['liveonsat']} | {m['ours']} |")
        P("")

    # ---- Section 1: coverage gaps -------------------------------------
    our_keys = {}
    for f in fixtures:
        k = (normalise_team(f["home_team"]), normalise_team(f["away_team"]),
             _date_of(f["kickoff"]))
        our_keys[k] = f
    our_dates = sorted(_date_of(f["kickoff"]) for f in fixtures)
    date_lo, date_hi = (our_dates[0], our_dates[-1]) if our_dates else ("", "")

    gaps = defaultdict(list)
    not_covered = Counter()
    for r in los_rows:
        comp = COMP_MAP.get(r["competition"])
        if not comp:
            not_covered[r["competition"]] += 1
            continue
        d = _date_of(r["kickoff_utc"])
        if not (date_lo <= d <= date_hi):
            continue   # outside the window we publish
        k = (normalise_team(r["home"]), normalise_team(r["away"]), d)
        if k not in our_keys:
            gaps[comp].append(r)
    # Anything backfilled or flagged as a name mismatch is not a "gap" any more
    mm_pairs = {(m["liveonsat"], m["date"]) for m in mismatches}
    for comp in list(gaps):
        gaps[comp] = [r for r in gaps[comp]
                      if (f"{r['home']} v {r['away']}", _date_of(r["kickoff_utc"])) not in mm_pairs]
        if not gaps[comp]:
            del gaps[comp]

    P("## 1. Remaining coverage gaps (not backfilled, not a name mismatch)")
    P("")
    if not gaps:
        P("_None within our date window._")
    for comp, rows in sorted(gaps.items()):
        P(f"**{comp}** — {len(rows)} missing")
        for r in sorted(rows, key=lambda x: x["kickoff_utc"])[:8]:
            P(f"- {r['kickoff_uk']}  {r['home']} v {r['away']}")
        if len(rows) > 8:
            P(f"- …and {len(rows) - 8} more")
        P("")
    if not_covered:
        P("**Competitions on liveonsat we don't publish at all** "
          "(listing counts):")
        P("")
        for comp, n in not_covered.most_common():
            P(f"- {comp}: {n}")
        P("")

    # ---- Section 2: broadcaster diffs ---------------------------------
    P("## 2. Broadcaster differences on matched fixtures")
    P("")
    matched = 0
    stats = {t: Counter() for t in AUDIT_TERRITORIES}
    detail = defaultdict(list)

    # Pass 1: how densely does liveonsat cover each territory per competition?
    cover = defaultdict(lambda: defaultdict(int))   # comp -> terr -> n
    comp_n = Counter()
    pairs = []
    for f in fixtures:
        row = idx.find(f["home_team"], f["away_team"], f["kickoff"])
        if not row:
            continue
        pairs.append((f, row))
        comp_n[f["competition"]] += 1
        for t in AUDIT_TERRITORIES:
            if _los_broadcasters(row, t):
                cover[f["competition"]][t] += 1
    sparse = {(c, t) for c in comp_n for t in AUDIT_TERRITORIES
              if cover[c][t] / comp_n[c] < SPARSE_THRESHOLD}

    # Pass 2: compare
    for f, row in pairs:
        matched += 1
        for t in AUDIT_TERRITORIES:
            ours = _our_broadcasters(f, t)
            theirs = _los_broadcasters(row, t)
            label = f"{f['home_team']} v {f['away_team']} ({f['kickoff'][:16]})"
            if ours and not theirs and (f["competition"], t) in sparse:
                stats[t]["unverifiable"] += 1
            elif ours and not theirs:
                stats[t]["over-claim"] += 1
                detail[t].append(f"OVER-CLAIM  {label}: we list "
                                 f"{sorted(ours)}, liveonsat lists nothing")
            elif theirs and not ours:
                stats[t]["gap"] += 1
                detail[t].append(f"GAP         {label}: liveonsat lists "
                                 f"{sorted(theirs)}, we list nothing")
            elif ours and theirs and not (ours & theirs):
                stats[t]["mismatch"] += 1
                detail[t].append(f"MISMATCH    {label}: we {sorted(ours)} "
                                 f"vs liveonsat {sorted(theirs)}")
            elif ours and theirs:
                stats[t]["agree"] += 1
            else:
                stats[t]["both-none"] += 1

    P(f"Matched **{matched}/{len(fixtures)}** fixtures to liveonsat.")
    P("")
    P("| Territory | agree | gap | over-claim | mismatch | unverifiable |")
    P("|---|---:|---:|---:|---:|---:|")
    for t in AUDIT_TERRITORIES:
        c = stats[t]
        P(f"| {t} | {c['agree']} | {c['gap']} | {c['over-claim']} | "
          f"{c['mismatch']} | {c['unverifiable']} |")
    P("")
    P("_unverifiable_ = liveonsat lists that territory on fewer than "
      f"{int(SPARSE_THRESHOLD*100)}% of the competition's matches, so its "
      "silence proves nothing. Fetch that territory's own liveonsat page "
      "to check it properly.")
    P("")
    if sparse:
        P("Sparse (competition → territories): " + "; ".join(
            f"{c} → {', '.join(t for (cc, t) in sorted(sparse) if cc == c)}"
            for c in sorted({c for c, _ in sparse})))
        P("")
    for t in AUDIT_TERRITORIES:
        if not detail[t]:
            continue
        P(f"<details><summary><b>{t}</b> — {len(detail[t])} issues</summary>")
        P("")
        P("```")
        for line in detail[t][:40]:
            P(line)
        if len(detail[t]) > 40:
            P(f"…and {len(detail[t]) - 40} more")
        P("```")
        P("</details>")
        P("")

    # ---- Section 3: ROI 3pm picks ------------------------------------
    P("## 3. Premier Sports Ireland — Saturday 3pm picks")
    P("")
    slots = defaultdict(list)
    for f in fixtures:
        if f.get("is_blackout"):
            slots[f["kickoff"]].append(f)
    if not slots:
        P("_No blackout-slot fixtures in fixtures.json._")
    for slot, fs in sorted(slots.items()):
        picks = idx.ireland_pick_for_slot(fs, slot)
        pick_names = [f"{p['home_team']} v {p['away_team']}" for p in picks]
        P(f"**{slot[:10]} 15:00 UK** — liveonsat says: "
          f"{', '.join(pick_names) if pick_names else '_(none listed yet)_'}")
        for f in fs:
            ours = [b for b in f["broadcasters"]
                    if b["territory"] == "Republic of Ireland"]
            ours_txt = (f"{ours[0]['broadcaster']} "
                        f"[{ours[0].get('source', '?')}]" if ours else "—")
            is_pick = any(f is p for p in picks)
            flag = ""
            if is_pick and not ours:
                flag = "  ⚠️ we publish nothing"
            elif not is_pick and ours:
                flag = "  ⚠️ we publish a broadcaster liveonsat doesn't"
            P(f"- {f['home_team']} v {f['away_team']}: {ours_txt}{flag}")
        P("")

    # ---- Section 4: unknown channels ----------------------------------
    P("## 4. liveonsat channels our classifier can't place")
    P("")
    unknown = Counter()
    for r in los_rows:
        for ch in r.get("channels", []):
            t, _ = classify_channel(ch["name"])
            if not t:
                unknown[re.sub(r"\s+HD$", "", ch["name"])] += 1
    P("Most frequent first — add rules to `CHANNEL_TERRITORY_RULES` in "
      "`liveonsat_match.py` for any that matter:")
    P("")
    for name, n in unknown.most_common(40):
        P(f"- {name} ({n})")
    P("")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=DEF_FIXTURES)
    ap.add_argument("--liveonsat", default=DEF_LIVEONSAT)
    ap.add_argument("--out", default=DEF_OUT)
    a = ap.parse_args()
    if not os.path.exists(a.liveonsat):
        print(f"liveonsat_audit: {a.liveonsat} not found — nothing to compare")
        return
    run(a.fixtures, a.liveonsat, a.out)


if __name__ == "__main__":
    main()
