"""
cup_fetcher.py
--------------
Orchestrates cup scrapers (BBC + Wikipedia), runs them in parallel, and
merges their outputs into a single deduplicated list of cup fixtures.

Why these two sources?

  BBC        Most reliable for current-round kickoff times (once the
             broadcasters have picked fixtures). Clean per-day HTML.
             Only tends to show fixtures in a near-term window.

  Wikipedia  Covers every round of every cup, including qualifying
             rounds that BBC doesn't bother with. Updated quickly
             after draws but kickoff times often lag because they're
             tied to TV picks that happen later.

Sky Sports has been disabled in production: their per-competition
fixture pages are JS-hydrated and the static HTML returned to a plain
requests.get() contains no fixture data. The Sky scraper is still
shipped in the codebase and can be re-enabled by adding sky_cups back
to the SOURCES tuple — but only after Playwright is added to the CI
environment to render the page first.

Combining the two active sources gives:

  - Broad coverage (every round) from Wikipedia
  - Fresh kickoff times (from BBC, once announced)
  - Status/score updates for played matches (from BBC first)

Merge strategy
--------------

All matches are keyed by `Match.dedupe_key()` — a tuple of (date,
normalised home, normalised away) that's consistent across sources
thanks to the team-alias table in _common.py.

For each dedupe key we keep exactly one Match. When multiple sources
report the same fixture:

  1. Start with the first source's match
  2. For each later source:
     - If it fills in a field the first one had empty (time, score,
       round label), take the later value
     - If both are populated, trust the source order

The source preference order is **BBC > Wikipedia**, because BBC's
kickoff times are more reliable. Wikipedia is the fallback for
fixtures BBC missed.

Date disagreements
------------------

A subtle case: BBC and Wikipedia sometimes disagree on the date of a
fixture that was moved for TV. Example: semi-final originally
scheduled Saturday, moved to Sunday 14:00 by Sky. Wikipedia may still
show the original Saturday date if nobody's updated the article yet.

The dedupe key includes the date, so a "same two teams, different
date" case would be treated as TWO separate fixtures, not one. We
detect this by running a second pass over the merged list that looks
for `(home, away)` pairs appearing within a small date window (±7
days) and collapses them — keeping the BBC version when present.

This is deliberately conservative: only collapse if one of the two
candidates comes from BBC. Wikipedia-only dates are left alone
because they may correspond to real replays or two-leg ties.

Parallel execution
------------------

Each scraper is a blocking I/O workload (requests + HTML parsing).
ThreadPoolExecutor is plenty — we're not CPU-bound and the GIL isn't
a problem for network waits.

If one scraper raises, we log the traceback and carry on with the
other. A single scraper's failure should never bring down the cup
feed entirely.
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import replace
from datetime import date as _date_cls, datetime, timedelta
from typing import Callable

from . import bbc_cups, sky_cups, wikipedia_cups
from ._common import CUPS, Match

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source registry — preference order is BBC > Wikipedia.
# Sky is disabled in production (see module docstring).
# ---------------------------------------------------------------------------

# Each entry: (source_name, callable_returning_list_of_Match, timeout_seconds)
# Callable takes no arguments. This means each scraper is called with its
# default settings — defaults are sensible for the nightly GitHub Action.
SOURCES: tuple[tuple[str, Callable[[], list[Match]], float], ...] = (
    ("bbc",       bbc_cups.fetch_all,            60.0),
    ("wikipedia", wikipedia_cups.fetch_all_cups, 60.0),
    # ("sky",     sky_cups.fetch_all,            90.0),  # disabled — needs Playwright
)


# ---------------------------------------------------------------------------
# Parallel fetch
# ---------------------------------------------------------------------------

def _fetch_one(name: str, fn: Callable[[], list[Match]]) -> tuple[str, list[Match]]:
    """Wrapper used by each thread. Catches exceptions so one scraper's
    failure doesn't poison the others."""
    try:
        result = fn()
        log.info("cup_fetcher: %s returned %d matches", name, len(result))
        return (name, result)
    except Exception as e:
        log.exception("cup_fetcher: %s failed: %s", name, e)
        return (name, [])


def fetch_parallel() -> dict[str, list[Match]]:
    """Run all configured scrapers concurrently. Returns {source_name: matches}."""
    results: dict[str, list[Match]] = {name: [] for name, _, _ in SOURCES}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(2, len(SOURCES))) as pool:
        future_to_name = {
            pool.submit(_fetch_one, name, fn): (name, timeout)
            for name, fn, timeout in SOURCES
        }
        for future in concurrent.futures.as_completed(future_to_name):
            name, timeout = future_to_name[future]
            try:
                _, matches = future.result(timeout=timeout)
                results[name] = matches
            except concurrent.futures.TimeoutError:
                log.warning("cup_fetcher: %s timed out after %.0fs", name, timeout)
            except Exception as e:
                log.exception("cup_fetcher: %s crashed: %s", name, e)

    return results


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

# Fields where "filled beats empty". If source A has a value and source B
# doesn't, prefer A regardless of source-order priority. This is how BBC
# enriches Wikipedia's round label, for example.
ENRICHABLE_FIELDS: tuple[str, ...] = (
    "kickoff_utc", "time_local", "round_label", "score_ft", "status",
)


def _is_empty(value) -> bool:
    """Whether a field value counts as 'missing' for enrichment purposes."""
    if value is None or value == "":
        return True
    # 'scheduled' is effectively the default status when nothing is known,
    # so treat it as mergeable — a 'finished' or 'postponed' from another
    # source wins over 'scheduled'.
    if value == "scheduled":
        return True
    return False


def _merge_two(keep: Match, extra: Match, source_priority: dict[str, int]) -> Match:
    """Merge `extra` into `keep`. `keep` wins ties on non-empty fields,
    except when a source later in priority provides richer data for an
    empty field."""
    updates: dict = {}

    # Is the match considered played by at least one source?
    finished_or_postponed = (
        keep.status in ("finished", "postponed")
        or extra.status in ("finished", "postponed")
    )

    for field in ENRICHABLE_FIELDS:
        kv = getattr(keep, field)
        ev = getattr(extra, field)

        # Guard: never paint a pre-kickoff time onto a finished match.
        # This comes up when one source (e.g. Wikipedia) reports the
        # fixture as scheduled with a time, while another (BBC) reports
        # it as finished without a time. The finished view wins.
        if field in ("time_local", "kickoff_utc") and finished_or_postponed:
            # Preserve whatever the finished/postponed source said
            # (typically None). Do not enrich from a scheduled source.
            if keep.status in ("finished", "postponed"):
                continue
            if extra.status in ("finished", "postponed"):
                # extra is the authoritative no-time answer
                if ev is None:
                    updates[field] = None
                continue

        if _is_empty(kv) and not _is_empty(ev):
            updates[field] = ev

    # For the source field, keep the higher-priority source name so
    # downstream consumers can see which one we trusted.
    keep_pri = source_priority.get(keep.source, 999)
    extra_pri = source_priority.get(extra.source, 999)
    if extra_pri < keep_pri:
        updates["source"] = extra.source

    if updates:
        return replace(keep, **updates)
    return keep


def _merge_by_dedupe_key(
    by_source: dict[str, list[Match]],
) -> list[Match]:
    """Build a single list keyed by dedupe_key, merging cross-source."""
    source_priority = {name: i for i, (name, _, _) in enumerate(SOURCES)}

    # Walk sources in priority order. First source "seeds" the dict;
    # later sources either fill empties or add new fixtures.
    merged: dict[tuple[str, str, str], Match] = {}

    for name, _, _ in SOURCES:
        for m in by_source.get(name, []):
            key = m.dedupe_key()
            if key not in merged:
                merged[key] = m
            else:
                merged[key] = _merge_two(merged[key], m, source_priority)

    return list(merged.values())


# ---------------------------------------------------------------------------
# Date-slip reconciliation
# ---------------------------------------------------------------------------

# How many days apart two "same two teams" fixtures can be before we
# stop trying to collapse them. Seven is roughly a typical TV-pick slip
# (Saturday → Sunday → Monday) without risking a two-legged tie being
# merged into a single fixture.
_DATE_SLIP_WINDOW_DAYS = 7


def _parse_iso(date_str: str) -> _date_cls | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _reconcile_date_slips(matches: list[Match]) -> list[Match]:
    """Detect (home, away) pairs that appear on different dates across
    sources and collapse them to the BBC date when one exists.

    We DO NOT touch pairs where both dates came from Wikipedia alone —
    those are more likely to be legitimate two-legged ties or replays
    than a TV-driven date slip."""
    # Group by (normalised home, normalised away)
    from ._common import _normalise_team

    pairs: dict[tuple[str, str], list[Match]] = {}
    for m in matches:
        pair = (_normalise_team(m.home), _normalise_team(m.away))
        pairs.setdefault(pair, []).append(m)

    kept: list[Match] = []
    for pair, group in pairs.items():
        if len(group) == 1:
            kept.append(group[0])
            continue

        # Multiple matches for the same team pair. Try to detect slips.
        # Sort by date so we can look at consecutive gaps.
        group.sort(key=lambda m: m.date)
        dates = [_parse_iso(m.date) for m in group]
        if any(d is None for d in dates):
            kept.extend(group)
            continue

        # Are they all within the slip window of each other?
        span_days = (max(dates) - min(dates)).days
        if span_days > _DATE_SLIP_WINDOW_DAYS:
            # Too far apart — treat as legitimately separate fixtures.
            kept.extend(group)
            continue

        # Prefer a BBC/Sky version if present — those reflect the
        # broadcaster's actual schedule. (Sky disabled but kept in this
        # filter for forward compatibility.)
        authoritative = [m for m in group if m.source in ("bbc", "sky")]
        if authoritative:
            # Sort by source priority (BBC before Sky), then by having a
            # kickoff time (has-time beats no-time).
            authoritative.sort(
                key=lambda m: (m.source != "bbc", m.time_local is None)
            )
            winner = authoritative[0]
            log.info(
                "cup_fetcher: date slip resolved for %s vs %s — "
                "dates seen %s, keeping %s (%s)",
                winner.home, winner.away,
                [m.date for m in group], winner.date, winner.source,
            )
            kept.append(winner)
        else:
            # All Wikipedia — leave as-is, might be a two-legged tie.
            kept.extend(group)

    return kept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_all_cups() -> list[Match]:
    """Run BBC and Wikipedia in parallel and return a merged, deduped,
    reconciled list of cup fixtures."""
    by_source = fetch_parallel()
    for name, _, _ in SOURCES:
        log.info("cup_fetcher: %s -> %d matches", name, len(by_source.get(name, [])))

    merged = _merge_by_dedupe_key(by_source)
    log.info("cup_fetcher: after dedupe: %d matches", len(merged))

    reconciled = _reconcile_date_slips(merged)
    log.info("cup_fetcher: after date-slip reconcile: %d matches", len(reconciled))

    # Stable sort for reproducible output
    reconciled.sort(key=lambda m: (m.date, m.time_local or "99:99",
                                    m.competition_code, m.home))
    return reconciled


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(
        description="Fetch cup fixtures from BBC + Wikipedia with merge"
    )
    ap.add_argument("--out", help="Write matches as JSON to this path")
    ap.add_argument("--no-parallel", action="store_true",
                    help="Run scrapers sequentially (easier to debug)")
    args = ap.parse_args()

    if args.no_parallel:
        by_source: dict[str, list[Match]] = {}
        for name, fn, _ in SOURCES:
            _, matches = _fetch_one(name, fn)
            by_source[name] = matches
        merged = _merge_by_dedupe_key(by_source)
        result = _reconcile_date_slips(merged)
    else:
        result = fetch_all_cups()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            _json.dump([m.to_dict() for m in result], fh,
                       indent=2, ensure_ascii=False)
        print(f"Wrote {len(result)} matches to {args.out}")
    else:
        for m in result[:50]:
            print(f"{m.date} {m.time_local or 'TBC':5s}  "
                  f"{m.competition_code:5s}  "
                  f"[{m.source:9s}]  "
                  f"{m.home} vs {m.away}  "
                  f"{'('+m.status+')' if m.status != 'scheduled' else ''}")
        if len(result) > 50:
            print(f"... and {len(result) - 50} more")
