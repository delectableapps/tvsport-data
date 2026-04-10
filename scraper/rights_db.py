"""
rights_db.py
============
Loads the broadcast rights Excel file and provides lookup functions.
This is the static "who has the rights" layer — updated once per season.

Source: Broadcast_rights_updated_08-04-26.xlsx
"""

import os
import pandas as pd

# ── Broadcaster metadata: type + icon ──────────────────────────────────────
BROADCASTER_META = {
    # UK & Ireland
    "Sky Sports":           {"type": "tv",     "icon": "📺"},
    "TNT Sports":           {"type": "tv",     "icon": "📺"},
    "HBO Max":              {"type": "stream", "icon": "📱"},
    "BBC Sport":            {"type": "free",   "icon": "📡"},
    "RTÉ":                  {"type": "free",   "icon": "📡"},
    "Virgin Media":         {"type": "free",   "icon": "📡"},
    "Premier Sports":       {"type": "tv",     "icon": "📺"},
    # Streaming services (channel = service name, never overridden)
    "Amazon Prime Video":   {"type": "stream", "icon": "📱"},
    "DAZN":                 {"type": "stream", "icon": "📱"},
    "Paramount+":           {"type": "stream", "icon": "📱"},
    "Peacock":              {"type": "stream", "icon": "📱"},
    "Stan Sport":           {"type": "stream", "icon": "📱"},
    "Fubo":                 {"type": "stream", "icon": "📱"},
    "Viaplay":              {"type": "stream", "icon": "📱"},
    "HBO Max BR":           {"type": "stream", "icon": "📱"},
    "iQIYI":                {"type": "stream", "icon": "📱"},
    "Coupang":              {"type": "stream", "icon": "📱"},
    "U-Next":               {"type": "stream", "icon": "📱"},
    "Migu":                 {"type": "stream", "icon": "📱"},
    "FPT Play":             {"type": "stream", "icon": "📱"},
    "JioStar":              {"type": "stream", "icon": "📱"},
    "PCCW / Now TV":        {"type": "stream", "icon": "📱"},
    "Megogo":               {"type": "stream", "icon": "📱"},
    "Okko":                 {"type": "stream", "icon": "📱"},
    # Pay TV
    "beIN Sports":          {"type": "tv",     "icon": "📺"},
    "SuperSport":           {"type": "tv",     "icon": "📺"},
    "Canal+ Afrique":       {"type": "tv",     "icon": "📺"},
    "Canal+":               {"type": "tv",     "icon": "📺"},
    "Sky Italia":           {"type": "tv",     "icon": "📺"},
    "Sky Deutschland":      {"type": "tv",     "icon": "📺"},
    "Movistar Plus+":       {"type": "tv",     "icon": "📺"},
    "Astro":                {"type": "tv",     "icon": "📺"},
    "StarHub":              {"type": "tv",     "icon": "📺"},
    "NBC Sports / Peacock": {"type": "tv",     "icon": "📺"},
    "CBS Sports":           {"type": "tv",     "icon": "📺"},
    "ESPN":                 {"type": "tv",     "icon": "📺"},
    "WOWOW":                {"type": "tv",     "icon": "📺"},
    "SPOTV":                {"type": "tv",     "icon": "📺"},
    "Sony Sports / SonyLIV":{"type": "tv",     "icon": "📺"},
    "Ziggo Sport":          {"type": "tv",     "icon": "📺"},
    "TV2 Norway":           {"type": "tv",     "icon": "📺"},
    "Cosmote TV":           {"type": "tv",     "icon": "📺"},
    "Sport TV":             {"type": "tv",     "icon": "📺"},
    "Arena Sport":          {"type": "tv",     "icon": "📺"},
    "EMTEK":                {"type": "tv",     "icon": "📺"},
    # Free-to-air
    "ZDF":                  {"type": "free",   "icon": "📡"},
    "M6":                   {"type": "free",   "icon": "📡"},
    "SBT":                  {"type": "free",   "icon": "📡"},
    "HRT":                  {"type": "free",   "icon": "📡"},
    "TRT":                  {"type": "free",   "icon": "📡"},
    "SRG SSR":              {"type": "free",   "icon": "📡"},
    "RTS":                  {"type": "free",   "icon": "📡"},
    "CBC Sport":            {"type": "free",   "icon": "📡"},
    "TVP":                  {"type": "free",   "icon": "📡"},
}

# Streaming services: their channel IS their service name, never overridden
STREAMING_SERVICES = {
    "Amazon Prime Video", "DAZN", "Paramount+", "Peacock", "Stan Sport",
    "Fubo", "Viaplay", "HBO Max", "HBO Max BR", "iQIYI", "Coupang", "U-Next",
    "Migu", "FPT Play", "JioStar", "PCCW / Now TV", "Megogo", "Okko",
    "discovery+", "NOW TV", "Sky Go",
}

def get_meta(broadcaster_name):
    """Return type + icon for a broadcaster, with sensible defaults."""
    for key, val in BROADCASTER_META.items():
        if key.lower() in broadcaster_name.lower() or broadcaster_name.lower() in key.lower():
            return val
    return {"type": "tv", "icon": "📺"}

def is_streaming_service(name):
    return any(s.lower() in name.lower() for s in STREAMING_SERVICES)


# ── UCL Rights (hardcoded from Excel + UEFA.com Jan 2026) ──────────────────
# Format: country → list of broadcaster dicts
UCL_RIGHTS = {
    "United Kingdom": [
        {"name": "TNT Sports",          "default_channels": "TNT Sports 1 / TNT Sports 2", "highlights_only": False},
        {"name": "Amazon Prime Video",  "default_channels": "Amazon Prime Video",            "highlights_only": False},
        {"name": "BBC Sport",           "default_channels": "BBC One / BBC iPlayer",         "highlights_only": True},
    ],
    "Republic of Ireland": [
        {"name": "RTÉ",           "default_channels": "RTÉ Two / RTÉ Player",   "highlights_only": False},
        {"name": "Premier Sports", "default_channels": "Premier Sports 1",       "highlights_only": False},
        {"name": "Virgin Media",  "default_channels": "Virgin Media Two",        "highlights_only": True},
    ],
    "Albania":              [{"name": "Tring",            "default_channels": "Tring Sport"}],
    "Armenia":              [{"name": "Fast Media",        "default_channels": "Fast TV"}],
    "Austria":              [
        {"name": "Sky Austria",  "default_channels": "Sky Sport Austria"},
        {"name": "Canal+",       "default_channels": "Canal+ Sport Austria"},
        {"name": "Servus TV",    "default_channels": "Servus TV",   "highlights_only": True},
        {"name": "ORF",          "default_channels": "ORF 1",       "highlights_only": True},
    ],
    "Azerbaijan":           [
        {"name": "CBC Sport",    "default_channels": "CBC Sport"},
        {"name": "İçtimai TV",   "default_channels": "İTV"},
    ],
    "Belarus":              [{"name": "Okko",             "default_channels": "Okko Sport"}],
    "Belgium":              [
        {"name": "DPG Media",    "default_channels": "Vier / Vijf"},
        {"name": "RTL Belgium",  "default_channels": "Club RTL"},
        {"name": "Proximus",     "default_channels": "Pickx Sports"},
        {"name": "Telenet",      "default_channels": "Play Sports"},
    ],
    "Bosnia & Herzegovina": [{"name": "Arena Sport",      "default_channels": "Arena Sport 1"}],
    "Brazil":               [
        {"name": "TNT Sports",   "default_channels": "TNT Sports BR"},
        {"name": "SBT",          "default_channels": "SBT"},
    ],
    "Bulgaria":             [
        {"name": "bTV",          "default_channels": "bTV Action"},
        {"name": "A1 Bulgaria",  "default_channels": "A1 Xtra Sport"},
    ],
    "Cambodia":             [{"name": "beIN Sports",      "default_channels": "beIN Sports"}],
    "Cameroon":             [
        {"name": "CRTV",         "default_channels": "CRTV Sport"},
        {"name": "SuperSport",   "default_channels": "SuperSport Football"},
        {"name": "Canal+ Afrique","default_channels": "Canal+ Sport Afrique"},
    ],
    "Canada":               [{"name": "DAZN",             "default_channels": "DAZN Canada"}],
    "Caribbean":            [{"name": "Flow Sports / SportsMax", "default_channels": "SportsMax"}],
    "Central America":      [{"name": "ESPN",             "default_channels": "ESPN Latinoamérica"}],
    "China":                [{"name": "iQIYI",            "default_channels": "iQIYI Sports"}],
    "Croatia":              [
        {"name": "HRT",          "default_channels": "HRT 2"},
        {"name": "Arena Sport",  "default_channels": "Arena Sport 2"},
    ],
    "Cyprus":               [{"name": "CYTA",             "default_channels": "Cytavision Sports"}],
    "Czechia":              [{"name": "TV Nova",           "default_channels": "Voyo"}],
    "Denmark":              [{"name": "Viaplay",           "default_channels": "Viaplay Football"}],
    "Dominican Republic":   [{"name": "ESPN",             "default_channels": "ESPN Caribe"}],
    "Estonia":              [{"name": "TV3",               "default_channels": "Go3"}],
    "Finland":              [{"name": "MTV Oy",            "default_channels": "MTV Sport"}],
    "France":               [
        {"name": "Canal+",       "default_channels": "Canal+ Sport"},
        {"name": "M6",           "default_channels": "M6",          "highlights_only": True},
    ],
    "Georgia":              [
        {"name": "Setanta Sports","default_channels": "Setanta Sports"},
        {"name": "Silknet",      "default_channels": "Silk Sport"},
    ],
    "Germany":              [
        {"name": "DAZN",          "default_channels": "DAZN 1 / DAZN 2"},
        {"name": "Amazon Prime Video", "default_channels": "Amazon Prime Video"},
        {"name": "ZDF",           "default_channels": "ZDF",        "highlights_only": True},
    ],
    "Greece":               [
        {"name": "Cosmote TV",    "default_channels": "Cosmote Sport"},
        {"name": "AlterEgo / MEGA","default_channels": "MEGA Channel"},
    ],
    "Hungary":              [
        {"name": "RTL",           "default_channels": "RTL Klub"},
        {"name": "Sport 1",       "default_channels": "Sport 1"},
    ],
    "Iceland":              [
        {"name": "Syn",           "default_channels": "Stöð 2 Sport"},
        {"name": "Viaplay",       "default_channels": "Viaplay"},
    ],
    "India / South Asia":   [{"name": "Sony Sports / SonyLIV", "default_channels": "Sony Ten 2 / SonyLIV"}],
    "Indonesia":            [
        {"name": "beIN Sports",   "default_channels": "beIN Sports Indonesia"},
        {"name": "EMTEK",         "default_channels": "SCTV"},
    ],
    "Israel":               [{"name": "The Sports Channel", "default_channels": "Sport5"}],
    "Italy":                [
        {"name": "Sky Italia",    "default_channels": "Sky Sport Uno"},
        {"name": "Amazon Prime Video", "default_channels": "Amazon Prime Video"},
    ],
    "Ivory Coast":          [
        {"name": "NCI",           "default_channels": "NCI"},
        {"name": "SuperSport",    "default_channels": "SuperSport Football"},
        {"name": "Canal+ Afrique","default_channels": "Canal+ Sport Afrique"},
    ],
    "Japan":                [
        {"name": "WOWOW",         "default_channels": "WOWOW Prime"},
        {"name": "U-Next",        "default_channels": "U-Next Sport",  "highlights_only": True},
    ],
    "Kazakhstan":           [{"name": "Quest Media / Qazsport", "default_channels": "Qazsport"}],
    "Kosovo":               [
        {"name": "RTK",           "default_channels": "RTK 1"},
        {"name": "Artmotion",     "default_channels": "Artmotion Sport"},
    ],
    "Latvia":               [{"name": "TV3",               "default_channels": "Go3"}],
    "Lithuania":            [{"name": "TV3",               "default_channels": "Go3"}],
    "Luxembourg":           [
        {"name": "DPG Media",     "default_channels": "RTL Luxembourg"},
        {"name": "DAZN",          "default_channels": "DAZN Luxembourg"},
    ],
    "Malaysia":             [{"name": "beIN Sports",       "default_channels": "beIN Sports Malaysia"}],
    "Malta":                [
        {"name": "PBS",           "default_channels": "TVM Sports"},
        {"name": "Melita",        "default_channels": "Melita More Sports"},
    ],
    "Mauritius":            [
        {"name": "MBC",           "default_channels": "MBC Sport"},
        {"name": "SuperSport",    "default_channels": "SuperSport Football"},
    ],
    "Mexico":               [
        {"name": "Max / HBO",     "default_channels": "Max (streaming)"},
        {"name": "FOX",           "default_channels": "Fox Sports Mexico"},
    ],
    "Middle East & North Africa": [{"name": "beIN Sports", "default_channels": "beIN Sports HD 1"}],
    "Moldova":              [
        {"name": "Setanta Sports","default_channels": "Setanta Sports"},
        {"name": "Jurnal TV",     "default_channels": "Jurnal TV"},
    ],
    "Mongolia":             [{"name": "Premier Sports / Look TV", "default_channels": "Look TV"}],
    "Montenegro":           [{"name": "Arena Sport",      "default_channels": "Arena Sport"}],
    "Myanmar":              [{"name": "Canal+",           "default_channels": "Canal+ Myanmar"}],
    "Netherlands":          [{"name": "Ziggo Sport",      "default_channels": "Ziggo Sport Voetbal"}],
    "New Zealand":          [{"name": "DAZN",             "default_channels": "DAZN NZ"}],
    "North Macedonia":      [{"name": "Arena Sport",      "default_channels": "Arena Sport"}],
    "Norway":               [{"name": "TV2 Norway",       "default_channels": "TV2 Sport Premium"}],
    "Pacific Islands":      [{"name": "Digicel",          "default_channels": "Digicel Play"}],
    "Pakistan":             [{"name": "Sony Sports / SonyLIV", "default_channels": "SonyLIV / Tapmad"}],
    "Philippines":          [{"name": "beIN Sports",      "default_channels": "beIN Sports Philippines"}],
    "Poland":               [{"name": "Canal+",           "default_channels": "Canal+ Sport PL"}],
    "Portugal":             [
        {"name": "Sport TV",      "default_channels": "Sport TV1"},
        {"name": "DAZN",          "default_channels": "DAZN Portugal"},
    ],
    "Romania":              [
        {"name": "DIGI",          "default_channels": "Digi Sport"},
        {"name": "Clever Media",  "default_channels": "Prima Sport"},
    ],
    "Russia":               [{"name": "Okko",             "default_channels": "Okko Sport"}],
    "Serbia":               [
        {"name": "Arena Sport",   "default_channels": "Arena Sport 1"},
        {"name": "RTS",           "default_channels": "RTS 1"},
    ],
    "Singapore":            [{"name": "beIN Sports",      "default_channels": "beIN Sports Singapore"}],
    "Slovakia":             [{"name": "TV Nova",           "default_channels": "Voyo SK"}],
    "Slovenia":             [
        {"name": "Pro Plus",      "default_channels": "Voyo SI"},
        {"name": "Sportklub",     "default_channels": "Sport Klub"},
    ],
    "South America":        [{"name": "ESPN",             "default_channels": "Star+ / ESPN"}],
    "South Korea":          [{"name": "SPOTV",            "default_channels": "SPOTV"}],
    "Spain":                [{"name": "Movistar Plus+",   "default_channels": "Movistar Liga de Campeones"}],
    "Sub-Saharan Africa":   [
        {"name": "SuperSport",    "default_channels": "SuperSport Football"},
        {"name": "Canal+ Afrique","default_channels": "Canal+ Sport Afrique"},
        {"name": "New World TV",  "default_channels": "New World TV Sport"},
    ],
    "Sweden":               [{"name": "Viaplay",           "default_channels": "Viaplay Football"}],
    "Switzerland":          [
        {"name": "Blue Sport",    "default_channels": "Blue Sport"},
        {"name": "SRG SSR",       "default_channels": "SRF Zwei",    "highlights_only": True},
    ],
    "Taiwan":               [{"name": "ELTA",             "default_channels": "ELTA Sports"}],
    "Thailand":             [{"name": "beIN Sports",      "default_channels": "beIN Sports Thailand"}],
    "Turkey":               [{"name": "TRT",              "default_channels": "TRT Spor"}],
    "Ukraine":              [{"name": "Megogo",           "default_channels": "Megogo Football"}],
    "United States":        [
        {"name": "CBS Sports",    "default_channels": "CBS Sports Network / Paramount+"},
        {"name": "TUDN / TelevisaUnivision", "default_channels": "TUDN / Univision"},
        {"name": "DAZN",          "default_channels": "DAZN USA (Spanish)"},
    ],
    "Uzbekistan":           [{"name": "Quest Media / Zo'r TV", "default_channels": "Zo'r TV"}],
    "Vietnam":              [
        {"name": "VTVcab",        "default_channels": "VTVcab ON"},
        {"name": "Viettel",       "default_channels": "Mytv / Viettel"},
    ],
    "In-flight / Ships":    [{"name": "Sport24",          "default_channels": "Sport24"}],
}


# ── EPL Rights ─────────────────────────────────────────────────────────────
EPL_RIGHTS = {
    "United Kingdom": [
        {"name": "Sky Sports",    "default_channels": "Sky Sports Main Event / Premier League"},
        {"name": "TNT Sports",    "default_channels": "TNT Sports 1"},
        {"name": "BBC Sport",     "default_channels": "BBC One / BBC iPlayer (MOTD)", "highlights_only": True},
    ],
    "Republic of Ireland": [
        {"name": "Sky Sports",    "default_channels": "Sky Sports Main Event / PL"},
        {"name": "TNT Sports",    "default_channels": "TNT Sports 1"},
        {"name": "Premier Sports","default_channels": "Premier Sports 1"},
    ],
    "Albania":          [{"name": "Digitalb",             "default_channels": "Digitalb Sport"}],
    "Andorra":          [{"name": "Canal+ / DAZN",        "default_channels": "CANAL+ / DAZN"}],
    "Armenia":          [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Austria":          [{"name": "Sky Deutschland",      "default_channels": "Sky Sport Premier League HD"}],
    "Belarus":          [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Belgium":          [{"name": "Telenet",              "default_channels": "Play Sports"}],
    "Bulgaria":         [{"name": "IMG / Nova",           "default_channels": "Nova Sport"}],
    "Croatia":          [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Cyprus":           [{"name": "Cytavision",           "default_channels": "Cytavision Sports"}],
    "Czech Republic":   [{"name": "Canal+",               "default_channels": "Canal+ Sport CZ"}],
    "Denmark":          [{"name": "Viaplay",              "default_channels": "Viaplay Football"}],
    "Estonia":          [{"name": "TV3",                  "default_channels": "Go3"}],
    "Finland":          [{"name": "Viaplay",              "default_channels": "Viaplay Football"}],
    "France":           [{"name": "Canal+",               "default_channels": "Canal+ Sport"}],
    "Georgia":          [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Germany":          [{"name": "Sky Deutschland",      "default_channels": "Sky Sport Premier League HD"}],
    "Greece":           [{"name": "IMG / Nova",           "default_channels": "Nova Sports"}],
    "Hungary":          [{"name": "TV2",                  "default_channels": "TV2 Sport"}],
    "Iceland":          [{"name": "Syn",                  "default_channels": "Stöð 2"}],
    "Israel":           [{"name": "Charlton",             "default_channels": "Sport5"}],
    "Italy":            [{"name": "Sky Italia",           "default_channels": "Sky Sport Football"}],
    "Kosovo":           [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Latvia":           [{"name": "TV3",                  "default_channels": "Go3"}],
    "Lithuania":        [{"name": "TV3",                  "default_channels": "Go3"}],
    "Luxembourg":       [{"name": "Canal+",               "default_channels": "Canal+ Luxembourg"}],
    "Malta":            [{"name": "TSN",                  "default_channels": "TSN Malta"}],
    "Moldova":          [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Montenegro":       [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Netherlands":      [{"name": "Viaplay",              "default_channels": "Viaplay Football"}],
    "North Macedonia":  [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Norway":           [{"name": "Viaplay",              "default_channels": "Viaplay Football"}],
    "Poland":           [{"name": "Canal+",               "default_channels": "Canal+ Sport PL"}],
    "Portugal":         [{"name": "DAZN",                 "default_channels": "DAZN Portugal"}],
    "Romania":          [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Serbia":           [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Slovakia":         [{"name": "Canal+",               "default_channels": "Canal+ SK"}],
    "Slovenia":         [{"name": "Arena Sport",          "default_channels": "Arena Sport"}],
    "Spain":            [{"name": "DAZN",                 "default_channels": "DAZN España"}],
    "Sweden":           [{"name": "Viaplay",              "default_channels": "Viaplay Football"}],
    "Switzerland":      [{"name": "Canal+ (FR) / Sky DE / Sky IT", "default_channels": "Sky Sport PL / Canal+ Sport"}],
    "Turkey":           [{"name": "beIN Sports",          "default_channels": "beIN Sports TR 1"}],
    "Ukraine":          [{"name": "Setanta",              "default_channels": "Setanta Sports Ukraine"}],
    "Middle East & North Africa": [{"name": "beIN Sports","default_channels": "beIN Sports MENA"}],
    "Sub-Saharan Africa": [
        {"name": "SuperSport",    "default_channels": "SuperSport Premier League · DStv 203"},
        {"name": "Canal+ Afrique","default_channels": "Canal+ Sport Afrique"},
    ],
    "Afghanistan":      [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Australia":        [{"name": "Stan Sport",           "default_channels": "Stan Sport"}],
    "Cambodia":         [{"name": "Jasmine / Mono",       "default_channels": "Jasmine / Mono"}],
    "China":            [{"name": "Migu",                 "default_channels": "Migu Video"}],
    "Chinese Taipei":   [{"name": "ELTA",                 "default_channels": "ELTA Sports"}],
    "Hong Kong":        [{"name": "PCCW / Now TV",        "default_channels": "Now Sports Prime"}],
    "Indonesia":        [{"name": "EMTEK",                "default_channels": "RCTI+"}],
    "Japan":            [{"name": "U-Next",               "default_channels": "U-Next Sport"}],
    "Kazakhstan":       [{"name": "Saran Media",          "default_channels": "Saran TV"}],
    "Laos":             [{"name": "Jasmine / Mono",       "default_channels": "Jasmine / Mono"}],
    "Macau":            [{"name": "M Plus",               "default_channels": "M Plus Sport"}],
    "Malaysia":         [{"name": "Astro",                "default_channels": "Astro SuperSport 3"}],
    "Mongolia":         [{"name": "Unitel",               "default_channels": "Unitel Sport"}],
    "Myanmar":          [{"name": "Canal+",               "default_channels": "Canal+ Myanmar"}],
    "New Zealand":      [{"name": "Sky NZ",               "default_channels": "Sky Sport 7 beIN Sports"}],
    "Pacific Islands":  [{"name": "Digicel",              "default_channels": "Digicel Play"}],
    "Singapore":        [{"name": "StarHub",              "default_channels": "StarHub Sports Hub 1"}],
    "South Asia":       [{"name": "JioStar / StarSports", "default_channels": "Star Sports Select HD1 / JioHotstar"}],
    "South Korea":      [{"name": "Coupang",              "default_channels": "Coupang Play"}],
    "Thailand":         [{"name": "Jasmine / Mono",       "default_channels": "True Visions / Mono Max"}],
    "Vietnam":          [{"name": "FPT Play",             "default_channels": "FPT Play"}],
    "Brazil":           [{"name": "ESPN",                 "default_channels": "ESPN Brasil"}],
    "Canada":           [{"name": "Fubo",                 "default_channels": "Fubo Canada"}],
    "Caribbean":        [{"name": "ESPN",                 "default_channels": "ESPN Caribbean"}],
    "Central America":  [{"name": "Fox Sports / TNT Mexico", "default_channels": "Fox Sports CA / TNT Sports MX"}],
    "Mexico":           [{"name": "Fox Sports / TNT Mexico", "default_channels": "Fox Sports MX / TNT Sports MX"}],
    "South America":    [{"name": "ESPN",                 "default_channels": "Star+ / ESPN"}],
    "United States":    [{"name": "NBC Sports / Peacock", "default_channels": "NBC / USA Network / Peacock"}],
}


def get_rights(competition: str) -> dict:
    """Return the rights dict for 'UCL' or 'EPL'."""
    if competition.upper() == "UCL":
        return UCL_RIGHTS
    elif competition.upper() == "EPL":
        return EPL_RIGHTS
    raise ValueError(f"Unknown competition: {competition}")


def build_broadcaster_list(competition: str, country: str,
                            channel_overrides: dict = None) -> list:
    """
    Build the list of broadcaster dicts for a given competition + country.
    channel_overrides: { broadcaster_name: {"channels": str, "coverageStart": str} }
    Streaming services always show their own name as the channel.
    """
    rights = get_rights(competition)
    entries = rights.get(country, [])
    if not entries:
        return []

    result = []
    for entry in entries:
        name = entry["name"]
        meta = get_meta(name)
        hl_only = entry.get("highlights_only", False)

        # Resolve channel
        if is_streaming_service(name):
            # Streaming: always use service name as channel
            channels = name
            coverage_start = None
        else:
            # TV/free: use match-specific override if available
            override = (channel_overrides or {}).get(name, {})
            channels = override.get("channels", entry.get("default_channels", name))
            coverage_start = override.get("coverageStart", None)

        result.append({
            "broadcaster": name,
            "channels": channels,
            "type": meta["type"],
            "icon": meta["icon"],
            "coverageType": "HIGHLIGHTS" if hl_only else "LIVE",
            "coverageStart": coverage_start,
        })

    return result


if __name__ == "__main__":
    # Quick test
    print("UCL UK:", build_broadcaster_list("UCL", "United Kingdom",
        {"TNT Sports": {"channels": "TNT Sports 1", "coverageStart": "18:00"}}))
    print("\nEPL Australia:", build_broadcaster_list("EPL", "Australia"))
    print("\nEPL MENA:", build_broadcaster_list("EPL", "Middle East & North Africa"))
