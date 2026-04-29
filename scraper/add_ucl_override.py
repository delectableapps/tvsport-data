#!/usr/bin/env python3
"""
add_ucl_override.py — add a per-fixture UCL broadcaster override

Adds an entry to UCL_MATCH_OVERRIDES inside rights_db.py. Use this for
UCL knockout matches where the UK / Ireland / France rotation differs
from the default rights map.

Usage examples
──────────────

  # Tuesday top pick — Amazon UK, Premier Sports IRE
  ./add_ucl_override.py --date 2026-12-08 \\
                        --home "Liverpool"  --away "Real Madrid" \\
                        --uk amazon --ireland premier-only

  # Wednesday tie — TNT UK, RTÉ + Virgin + Premier IRE
  ./add_ucl_override.py --date 2026-12-09 \\
                        --home "PSG"  --away "Bayern Munich" \\
                        --uk tnt --ireland rotated

  # The final — wildcard teams, M6 returns to FTA in France
  ./add_ucl_override.py --date 2027-05-29 --final

  # Preview without writing (always do this first if you are nervous)
  ./add_ucl_override.py --date 2026-12-08 --home "Liverpool" --away "Real Madrid" \\
                        --uk amazon --ireland premier-only --dry-run

  # Replace an existing entry without complaining (re-runs are otherwise rejected)
  ./add_ucl_override.py --date 2026-12-08 --home "Liverpool" --away "Real Madrid" \\
                        --uk amazon --ireland premier-only --force

Where to find the right values for --uk / --ireland
────────────────────────────────────────────────────

  --uk amazon       Amazon Prime takes the top-pick Tuesday match
                    (17 per season). Check Amazon's UEFA page for the
                    week's pick:
                      https://www.amazon.co.uk/gp/video/storefront/uefa
                    The non-pick Tuesday tie and ALL Wednesday ties go
                    to TNT — use --uk tnt for those.

  --uk tnt          TNT Sports has every UCL match except Amazon's
                    17 Tuesday picks. Default for Wednesday matches
                    and the final.

  --ireland rotated RTÉ + Virgin Media + Premier Sports each pick one
                    midweek match. Use this for Wednesday ties (where
                    rotation is most common) and any Tuesday tie that
                    RTÉ or Virgin have selected. Their schedules:
                      https://www.rte.ie/sport/soccer/
                      https://www.virginmediasport.ie/

  --ireland premier-only
                    Premier Sports only. Use for Tuesday top-picks and
                    any midweek match RTÉ/Virgin haven't selected. Safe
                    default if you can't find a public schedule.

When in doubt, use --uk tnt --ireland rotated. Over-listing broadcasters
is never wrong, just slightly less precise.
"""

import argparse
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

BEGIN_MARKER = "# ── BEGIN_AUTO_OVERRIDES ──"
END_MARKER   = "# ── END_AUTO_OVERRIDES ──"

UK_PRESETS = {
    "amazon": '"Prime Video; BBC"',
    "tnt":    '"TNT Sports; BBC"',
}

IRELAND_PRESETS = {
    "rotated":       '"RTÉ; Virgin Media; Premier Sports"',
    "premier-only":  '"Premier Sports"',
}


def normalise_for_key(name: str) -> str:
    """Match the normalisation used by rights_db._normalise_team_name.

    Imports rights_db._normalise_team_name dynamically so the two stay
    in sync — if you change one, the other is updated automatically.
    Falls back to a local copy if rights_db can't be imported (e.g. when
    running the script before deployment).
    """
    try:
        # Lazy import — avoid hard dependency at module-load time so
        # syntax errors in rights_db don't break the script's --help
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import rights_db
        return rights_db._normalise_team_name(name)
    except Exception:
        pass
    # Fallback (kept in case rights_db is unavailable). Should match
    # rights_db._normalise_team_name byte-for-byte.
    if not name:
        return ""
    nfd = unicodedata.normalize("NFD", name)
    s = "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()
    short_forms = {
        "psg": "paris saint-germain", "psv": "psv eindhoven",
        "man utd": "manchester united", "man united": "manchester united",
        "man city": "manchester city", "spurs": "tottenham hotspur",
    }
    if s in short_forms:
        s = short_forms[s]
    aliases = {
        "munchen": "munich", "muenchen": "munich", "moskva": "moscow",
        "koln": "cologne", "koeln": "cologne", "wien": "vienna",
        "praha": "prague", "warszawa": "warsaw", "athina": "athens",
        "athinai": "athens",
    }
    for de, en in aliases.items():
        s = s.replace(de, en)
    for prefix in ("club ", "fc ", "afc ", "ac ", "as ", "ss ", "us ", "sk ", "rb "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    for suffix in (" fc", " afc", " cf", " cp", " sc", " bc", " sad"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    s = s.replace(" de ", " ").replace(" del ", " ").replace(" e ", " ")
    s = " ".join(s.split())
    return s.strip()


def validate_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        sys.exit(f"ERROR: --date must be YYYY-MM-DD, got {date_str!r}")
    weekday = dt.strftime("%A")
    # Knockout midweeks are Tue/Wed; finals are Saturdays. Anything else
    # is suspicious enough to flag but not block (Super Cup, replays etc.).
    if weekday not in ("Tuesday", "Wednesday", "Saturday"):
        print(f"WARNING: {date_str} is a {weekday}. UCL knockouts are usually "
              f"Tue/Wed and finals are Saturdays. Continuing anyway.",
              file=sys.stderr)
    return date_str


def render_entry(home: str, away: str, date: str,
                 uk: str | None, ireland: str | None,
                 france: str | None,
                 is_final: bool) -> str:
    """Build the dict-entry text to splice into UCL_MATCH_OVERRIDES."""
    home_key = "*" if is_final else normalise_for_key(home)
    away_key = "*" if is_final else normalise_for_key(away)

    rows = []
    if uk:
        rows.append(f'        "United Kingdom": {{"broadcaster": {uk + ",":36s}'
                    f'"region": "Europe"}},')
    if ireland:
        rows.append(f'        "Ireland":        {{"broadcaster": {ireland + ",":36s}'
                    f'"region": "Europe"}},')
    if france:
        rows.append(f'        "France":         {{"broadcaster": {france + ",":36s}'
                    f'"region": "Europe"}},')

    if is_final:
        comment = (f"    # FINAL — Sat {date} (wildcard: any UCL fixture this date)")
    else:
        # Tag whether this is a Tue/Wed slot for human readers
        weekday = datetime.strptime(date, "%Y-%m-%d").strftime("%a")
        descr = "Tuesday top-pick" if weekday == "Tue" and uk == UK_PRESETS["amazon"] \
                else f"{weekday} match"
        comment = (f"    # {descr} {date} — {home} v {away}")

    body = "\n".join(rows)
    return (
        f"{comment}\n"
        f'    ("{home_key}", "{away_key}", "{date}"): {{\n'
        f"{body}\n"
        f"    }},"
    )


def find_marker_block(content: str) -> tuple[int, int]:
    begin = content.find(BEGIN_MARKER)
    end   = content.find(END_MARKER)
    if begin == -1 or end == -1:
        sys.exit(f"ERROR: rights_db.py is missing the BEGIN/END markers around\n"
                 f"the UCL_MATCH_OVERRIDES dict. Re-add them like so:\n\n"
                 f"  UCL_MATCH_OVERRIDES = {{\n"
                 f"      {BEGIN_MARKER}\n"
                 f"      ...your existing entries...\n"
                 f"      {END_MARKER}\n"
                 f"  }}\n")
    if begin > end:
        sys.exit("ERROR: BEGIN_AUTO_OVERRIDES marker comes AFTER "
                 "END_AUTO_OVERRIDES — file looks malformed.")
    return begin, end


def detect_duplicate(block: str, home_key: str, away_key: str,
                     date: str) -> bool:
    """Return True if a key matching this fixture already exists in the block."""
    # Match either ("home", "away", "date") or ("*", "*", "date") for the
    # final wildcard. We compare on normalised home_key/away_key.
    pattern = re.compile(
        r'\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"(\d{4}-\d{2}-\d{2})"\s*\)\s*:',
    )
    for m in pattern.finditer(block):
        existing_home, existing_away, existing_date = m.group(1), m.group(2), m.group(3)
        if existing_date != date:
            continue
        # Wildcard final entry — date alone is the unique key
        if home_key == "*" and away_key == "*":
            if existing_home == "*" and existing_away == "*":
                return True
            continue
        if existing_home == "*" and existing_away == "*":
            continue
        # Compare normalised forms
        if normalise_for_key(existing_home) == home_key and \
           normalise_for_key(existing_away) == away_key:
            return True
    return False


def remove_existing_entry(block: str, home_key: str, away_key: str,
                          date: str) -> str:
    """Remove an existing entry (for --force replacement). Returns updated block."""
    # Find the entry and the trailing comma + blank lines. We greedy-match
    # everything from any optional preceding comment line(s) through the
    # closing `},` of that entry.
    lines = block.splitlines(keepends=True)
    out_lines = []
    i = 0
    pattern = re.compile(
        r'^\s*\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"(\d{4}-\d{2}-\d{2})"\s*\)\s*:'
    )
    while i < len(lines):
        m = pattern.match(lines[i])
        if not m:
            out_lines.append(lines[i])
            i += 1
            continue
        existing_home, existing_away, existing_date = m.group(1), m.group(2), m.group(3)
        match = False
        if existing_date == date:
            if home_key == "*" and away_key == "*":
                match = (existing_home == "*" and existing_away == "*")
            elif existing_home != "*":
                match = (normalise_for_key(existing_home) == home_key
                         and normalise_for_key(existing_away) == away_key)
        if not match:
            out_lines.append(lines[i])
            i += 1
            continue
        # Found the entry — also drop preceding comment lines (any consecutive
        # `    # ...` lines immediately above) so we don't accumulate stale
        # commentary.
        while out_lines and out_lines[-1].lstrip().startswith("#"):
            out_lines.pop()
        # Skip until we find the closing `},` for this entry (matching brace depth)
        depth = 0
        seen_open = False
        while i < len(lines):
            line = lines[i]
            depth += line.count("{") - line.count("}")
            if "{" in line:
                seen_open = True
            i += 1
            if seen_open and depth == 0:
                # Also skip any blank line immediately after
                if i < len(lines) and lines[i].strip() == "":
                    i += 1
                break
    return "".join(out_lines)


def main():
    ap = argparse.ArgumentParser(
        description="Add a per-fixture UCL broadcaster override to rights_db.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--date", required=True,
                    help="Match date in YYYY-MM-DD")
    ap.add_argument("--home", help="Home team name (as in fixtures.json)")
    ap.add_argument("--away", help="Away team name (as in fixtures.json)")
    ap.add_argument("--uk", choices=list(UK_PRESETS.keys()),
                    help="UK preset: 'amazon' (Tue top-pick) or 'tnt' (everything else)")
    ap.add_argument("--ireland", choices=list(IRELAND_PRESETS.keys()),
                    help="Ireland preset: 'rotated' (RTÉ+Virgin+Premier) "
                         "or 'premier-only'")
    ap.add_argument("--final", action="store_true",
                    help="Treat as the final: wildcard home/away, "
                         "TNT Sports + BBC for UK, full IRE rotation, "
                         "Canal+ + M6 for France. --home/--away ignored.")
    ap.add_argument("--rights-db", default="rights_db.py",
                    help="Path to rights_db.py (default: ./rights_db.py)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be added/changed; don't write")
    ap.add_argument("--force", action="store_true",
                    help="Replace an existing entry for the same fixture "
                         "instead of erroring out")
    args = ap.parse_args()

    # Validate
    date = validate_date(args.date)

    if args.final:
        home = away = "*"
        # Sensible final defaults — caller can still override with explicit flags
        uk_clause = UK_PRESETS["tnt"] if not args.uk else UK_PRESETS[args.uk]
        ie_clause = IRELAND_PRESETS["rotated"] if not args.ireland else IRELAND_PRESETS[args.ireland]
        fr_clause = '"Canal+; M6"'
        is_final = True
    else:
        if not args.home or not args.away:
            sys.exit("ERROR: --home and --away are required for non-final fixtures "
                     "(use --final for the final).")
        home, away = args.home, args.away
        if not args.uk and not args.ireland:
            sys.exit("ERROR: at least one of --uk or --ireland must be set.")
        uk_clause = UK_PRESETS[args.uk] if args.uk else None
        ie_clause = IRELAND_PRESETS[args.ireland] if args.ireland else None
        fr_clause = None
        is_final = False

    home_key = "*" if is_final else normalise_for_key(home)
    away_key = "*" if is_final else normalise_for_key(away)

    # Read file
    rights_path = Path(args.rights_db)
    if not rights_path.exists():
        sys.exit(f"ERROR: {rights_path} not found. Pass --rights-db /path/to/rights_db.py")
    content = rights_path.read_text(encoding="utf-8")

    begin_idx, end_idx = find_marker_block(content)
    block = content[begin_idx + len(BEGIN_MARKER):end_idx]

    # Duplicate detection
    if detect_duplicate(block, home_key, away_key, date):
        if not args.force:
            sys.exit(f"ERROR: an override for ({home_key!r}, {away_key!r}, "
                     f"{date!r}) already exists.\n"
                     f"Use --force to replace it.")
        block = remove_existing_entry(block, home_key, away_key, date)
        action = "REPLACED"
    else:
        action = "ADDED"

    # Build the new entry
    new_entry = render_entry(home if not is_final else "TBC",
                             away if not is_final else "TBC",
                             date, uk_clause, ie_clause, fr_clause,
                             is_final)

    # Splice it in: append to the end of the block (just before END marker).
    # Strip trailing whitespace from the block and add a single newline gap.
    block = block.rstrip() + "\n\n" + new_entry + "\n    "
    new_content = (
        content[:begin_idx + len(BEGIN_MARKER)]
        + block
        + content[end_idx:]
    )

    # Diff preview
    print(f"\n{action}: {date}  {home} v {away}")
    print(f"  UK:      {uk_clause or '(unchanged — uses default UCL_RIGHTS row)'}")
    print(f"  IRE:     {ie_clause or '(unchanged)'}")
    if fr_clause:
        print(f"  FRA:     {fr_clause}")
    print(f"  Key:     ({home_key!r}, {away_key!r}, {date!r})")
    if is_final:
        print(f"  Wildcard: matches ANY UCL fixture on {date}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print("Entry that would be written:\n")
        print(new_entry)
        print("\nNo file changes made. Re-run without --dry-run to commit.")
        return

    # Backup + write
    backup = rights_path.with_suffix(rights_path.suffix + ".bak")
    shutil.copy(rights_path, backup)
    rights_path.write_text(new_content, encoding="utf-8")

    # Round-trip syntax check — if Python can't parse it, restore the backup.
    try:
        import ast
        ast.parse(new_content)
    except SyntaxError as e:
        shutil.copy(backup, rights_path)
        sys.exit(f"ERROR: edit produced invalid Python ({e}). "
                 f"Restored from {backup}.")

    print(f"\n✓ Wrote {rights_path}  (backup at {backup})")
    print(f"✓ Run the scraper to regenerate fixtures.json with the new override:")
    print(f"     cd {rights_path.parent} && python merger.py")


if __name__ == "__main__":
    main()
