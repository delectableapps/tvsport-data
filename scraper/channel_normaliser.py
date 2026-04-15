"""
channel_normaliser.py
---------------------
Normalises raw channel name strings to canonical names using channels.json.
Drop this file into your scraper/ directory alongside merger.py.

Usage in merger.py:
    from channel_normaliser import normalise_channel, normalise_broadcaster_list

    # Single channel name
    clean = normalise_channel("Sky Sports ME")  # → "Sky Sports Main Event"

    # A whole broadcaster list on a fixture
    fixture["broadcasters"] = normalise_broadcaster_list(fixture.get("broadcasters", {}))
"""

import json
import os
import re

# ---------------------------------------------------------------------------
# Load the mapping once at import time
# ---------------------------------------------------------------------------

_CHANNELS_JSON_PATH = os.path.join(os.path.dirname(__file__), "channels.json")

def _load_mapping(path: str) -> dict:
    """
    Flatten the nested channels.json into a single dict:
        { "raw variant": "Canonical Name", ... }
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[channel_normaliser] WARNING: {path} not found — skipping normalisation")
        return {}
    except json.JSONDecodeError as e:
        print(f"[channel_normaliser] WARNING: could not parse {path}: {e}")
        return {}

    flat = {}
    for group_name, entries in data.items():
        if group_name.startswith("_"):
            continue  # skip _comment, _version etc.
        for raw, canonical in entries.items():
            flat[raw] = canonical
            # Also add a lowercase lookup for fuzzy matching
            flat[raw.lower()] = canonical

    print(f"[channel_normaliser] Loaded {len(flat) // 2} channel mappings from {os.path.basename(path)}")
    return flat


_MAPPING: dict = _load_mapping(_CHANNELS_JSON_PATH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalise_channel(raw: str) -> str:
    """
    Return the canonical name for a raw channel string.
    Falls back to the original string (stripped) if no mapping found.

    Examples:
        normalise_channel("Sky Sports ME")          → "Sky Sports Main Event"
        normalise_channel("sky sports me")          → "Sky Sports Main Event"
        normalise_channel("BT Sport 1")             → "TNT Sports 1"
        normalise_channel("Sky Sports Main Event")  → "Sky Sports Main Event"
        normalise_channel("SomeUnknownChannel")     → "SomeUnknownChannel"
    """
    if not isinstance(raw, str):
        return str(raw)

    stripped = raw.strip()

    # Exact match first
    if stripped in _MAPPING:
        return _MAPPING[stripped]

    # Case-insensitive match
    lower = stripped.lower()
    if lower in _MAPPING:
        return _MAPPING[lower]

    # Light normalisation: collapse multiple spaces, strip trailing HD/sd etc.
    normalised = re.sub(r"\s+", " ", stripped)
    if normalised in _MAPPING:
        return _MAPPING[normalised]

    # Not found — return cleaned original
    return stripped


def normalise_channel_list(channels) -> list:
    """
    Normalise a list (or comma-separated string) of channel names.
    Deduplicates after normalisation.

    Args:
        channels: list of strings, OR a single comma-separated string

    Returns:
        Deduplicated list of canonical channel names, preserving order.
    """
    if isinstance(channels, str):
        raw_list = [c.strip() for c in channels.split(",") if c.strip()]
    elif isinstance(channels, (list, tuple)):
        raw_list = [str(c).strip() for c in channels if c]
    else:
        return []

    seen = []
    for ch in raw_list:
        canonical = normalise_channel(ch)
        if canonical not in seen:
            seen.append(canonical)
    return seen


def normalise_broadcaster_list(broadcasters: dict) -> dict:
    """
    Normalise the channels inside a broadcasters dict.

    The broadcasters dict has this shape (as built by merger.py / rights_db.py):
        {
            "United Kingdom": {
                "broadcaster": "Sky Sports",
                "channels": ["Sky Sports ME", "Sky Sports Action HD"],
                "type": "pay-tv",
                ...
            },
            ...
        }

    Returns the same dict with every channels list normalised.
    Also normalises any top-level "channel" string field if present.
    """
    if not isinstance(broadcasters, dict):
        return broadcasters

    normalised = {}
    for territory, info in broadcasters.items():
        if not isinstance(info, dict):
            normalised[territory] = info
            continue

        entry = dict(info)  # shallow copy

        # Normalise "channels" list
        if "channels" in entry and entry["channels"]:
            entry["channels"] = normalise_channel_list(entry["channels"])

        # Normalise single "channel" string (some entries use this)
        if "channel" in entry and entry["channel"]:
            entry["channel"] = normalise_channel(entry["channel"])

        normalised[territory] = entry

    return normalised


# ---------------------------------------------------------------------------
# Standalone test / diagnostics
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        ("Sky Sports ME",          "Sky Sports Main Event"),
        ("sky sports me",          "Sky Sports Main Event"),
        ("BT Sport 1",             "TNT Sports 1"),
        ("BT Sport 2",             "TNT Sports 2"),
        ("Amazon Prime",           "Amazon Prime Video"),
        ("Prime Video",            "Amazon Prime Video"),
        ("beIN SPORTS HD 1",       "beIN Sports HD 1"),
        ("beIN Sports 2",          "beIN Sports HD 2"),
        ("SuperSport 203",         "SuperSport Premier League"),
        ("SuperSport 205",         "SuperSport Football"),
        ("Paramount Plus",         "Paramount+"),
        ("Canal Plus Sport",       "Canal+ Sport"),
        ("Viaplay Sport",          "Viaplay Sports 1"),
        ("SomeUnknownChannel",     "SomeUnknownChannel"),  # no mapping → passthrough
    ]

    print("\n--- Channel normalisation test ---")
    all_pass = True
    for raw, expected in test_cases:
        result = normalise_channel(raw)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_pass = False
        print(f"  {status}  '{raw}' → '{result}'  (expected: '{expected}')")

    print()
    print("All tests passed ✓" if all_pass else "Some tests FAILED ✗")

    # Test list normalisation
    print("\n--- List normalisation test ---")
    raw_list = ["Sky Sports ME", "Sky Sports Main Event HD", "BT Sport 1", "BT Sport 1"]
    result = normalise_channel_list(raw_list)
    print(f"  Input:  {raw_list}")
    print(f"  Output: {result}")
    assert result == ["Sky Sports Main Event", "TNT Sports 1"], f"Unexpected: {result}"
    print("  ✓ Deduplication and normalisation correct")
