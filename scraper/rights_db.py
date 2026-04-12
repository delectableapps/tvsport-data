"""
rights_db.py — TVsport Broadcast Rights Database
Generated: April 2026
Source: Broadcast_rights_updated_100426.xlsx + liveonsat audit

Structure per territory:
  { "channels": [...], "type": "epg|static", "badges": [...] }

  type="epg"    → channel assignment comes from EPG/scraper at runtime
  type="static" → channel list is fixed (no EPG feed available)

Badges: live, tv, stream, free, highlights
"""

# ─────────────────────────────────────────────────────────────────────
# EPL RIGHTS  (2025/26–2027/28)
# ─────────────────────────────────────────────────────────────────────
EPL_RIGHTS = {
    # ── UK ────────────────────────────────────────────────────────────
    "United Kingdom": {
        "broadcaster": "Sky Sports / TNT Sports / BBC",
        "channels": ["Sky Sports Main Event HD", "Sky Sports Premier League HD",
                     "Sky Sports HD", "Sky Sports Action HD", "Sky Sports Main Event UHD",
                     "Sky UK Ultra HD 1", "Sky Go UK [online]",
                     "TNT Sports 1 HD", "TNT Sports Ultimate UHD", "TNT Sports Digital Exclusive",
                     "HBO Max (uk/ire)", "BBC iPlayer (MOTD highlights)"],
        "type": "epg",
        "badges": ["live", "tv"],
        "blackout_rule": True,   # 3pm Sat blackout applies
    },
    # ── Europe ────────────────────────────────────────────────────────
    "Republic of Ireland": {
        "broadcaster": "Sky Sports / TNT Sports / Premier Sports",
        "channels": ["Sky Sports Main Event", "Sky Sports Premier League",
                     "TNT Sports 1 HD", "Premier Sports 1 Ireland HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Albania": {
        "broadcaster": "Digitalb",
        "channels": ["Digitalb Sport", "SuperSport 2 Albania HD"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Andorra": {
        "broadcaster": "Canal+ / DAZN",
        "channels": ["Canal+ / DAZN"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Armenia": {
        "broadcaster": "Saran Media",
        "channels": ["Saran TV"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Austria": {
        "broadcaster": "Sky Deutschland",
        "channels": ["Sky Sport Premier League DE HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Belarus": {
        "broadcaster": "Saran Media",
        "channels": ["Saran TV"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Belgium": {
        "broadcaster": "Telenet",
        "channels": ["Play Sports"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Bosnia & Herzegovina": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Bulgaria": {
        "broadcaster": "IMG / Nova Broadcasting",
        "channels": ["Nova Sports Premier League HD", "Nova Sports Prime Hellas HD",
                     "Nova Sports Start Hellas HD", "Nova Sports 5 Hellas HD",
                     "Diema Sport HD", "Diema Sport 2 HD", "Play Diema XTRA ($/geo/R)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Croatia": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport 1 Hrvatska HD", "Arena Sport 5 Hrvatska HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Cyprus": {
        "broadcaster": "Cytavision",
        "channels": ["Cytavision Sports 3 HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Czech Republic": {
        "broadcaster": "Canal+",
        "channels": ["Canal+ Sport 1 Czech HD", "Canal+ Sport 4 Czech HD",
                     "Canal+ Sport 7 Czech HD", "Canal+ Sport 8 Czech HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Denmark": {
        "broadcaster": "Viaplay",
        "channels": ["ViaPlay Danmark HD", "Prime Video Dansk [$]"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Estonia": {
        "broadcaster": "Go3 / TV3",
        "channels": ["Go3 Extra Sport Baltics ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Finland": {
        "broadcaster": "Viaplay",
        "channels": ["ViaPlay Suomi HD", "V Sport Premier League HD"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "France": {
        "broadcaster": "Canal+",
        "channels": ["Canal+ France HD", "Canal+ Foot HD", "Canal+ Premier League HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Georgia": {
        "broadcaster": "Saran Media",
        "channels": ["Saran TV"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Germany": {
        "broadcaster": "Sky Deutschland",
        "channels": ["Sky Sport Premier League DE HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Greece": {
        "broadcaster": "IMG / Nova",
        "channels": ["Nova Sports Premier League HD", "Nova Sports Prime Hellas HD",
                     "Nova Sports Start Hellas HD", "Nova Sports 5 Hellas HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Hungary": {
        "broadcaster": "TV2",
        "channels": ["TV2 Sport"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Iceland": {
        "broadcaster": "Syn",
        "channels": ["Stöð 2"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Israel": {
        "broadcaster": "Charlton",
        "channels": ["Sport 1 Israel HD", "Sport 2 Israel HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Italy": {
        "broadcaster": "Sky Italia",
        "channels": ["Sky Sport Football IT"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Kosovo": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Latvia": {
        "broadcaster": "Go3 / TV3",
        "channels": ["Go3 Extra Sport Baltics ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Lithuania": {
        "broadcaster": "Go3 / TV3",
        "channels": ["Go3 Extra Sport Baltics ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Luxembourg": {
        "broadcaster": "Canal+",
        "channels": ["Canal+ Luxembourg"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Malta": {
        "broadcaster": "TSN",
        "channels": ["TSN Malta"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Moldova": {
        "broadcaster": "Saran Media",
        "channels": ["Saran TV"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Montenegro": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Netherlands": {
        "broadcaster": "Viaplay",
        "channels": ["ViaPlay Nederland HD"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "North Macedonia": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Norway": {
        "broadcaster": "Viaplay",
        "channels": ["ViaPlay Norge HD", "V Sport Premier League HD"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Poland": {
        "broadcaster": "Canal+",
        "channels": ["Canal+ Extra 1 Polska HD", "Canal+ Extra 2 Polska HD",
                     "Canal+ Premier League HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Portugal": {
        "broadcaster": "DAZN",
        "channels": ["DAZN 1 Portugal HD", "DAZN 2 Portugal HD",
                     "DAZN 3 Portugal HD", "DAZN 4 Portugal HD",
                     "DAZN Portugal ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Romania": {
        "broadcaster": "VOYO / Pro TV",
        "channels": ["VOYO Pro TV Romania [$]"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Serbia": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Premium 1 Srbija HD", "Arena Premium 2 Srbija HD",
                     "Arena Premium 3 Srbija HD", "Arena Premium 5 Srbija HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Slovakia": {
        "broadcaster": "Canal+",
        "channels": ["Canal+ SK"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Slovenia": {
        "broadcaster": "Arena Sport",
        "channels": ["Arena Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Spain": {
        "broadcaster": "DAZN",
        "channels": ["DAZN 1 Bar Espana", "DAZN 1 Espana HD",
                     "DAZN 2 Bar Espana", "DAZN 2 Espana HD",
                     "DAZN España ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Sweden": {
        "broadcaster": "Viaplay",
        "channels": ["ViaPlay Sverige HD", "V Sport Premier League HD",
                     "Prime Video Sverige [$]"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Switzerland": {
        "broadcaster": "Canal+ / Sky Deutschland / Sky Italia",
        "channels": ["Sky Sport Premier League DE HD", "Canal+ CH"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Turkey": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports Türkiye 3 HD", "beIN Connect Türkiye"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Ukraine": {
        "broadcaster": "Monomax",
        "channels": ["Monomax Streaming ($/geo/R)"],
        "type": "static", "badges": ["live", "stream"],
    },
    # ── Americas ──────────────────────────────────────────────────────
    "United States": {
        "broadcaster": "NBC Sports / Peacock / Telemundo",
        "channels": ["NBC USA HD", "NBC Sports Network", "USA Network HD",
                     "Peacock Premium USA ($/geo/R)", "NBC Universo USA", "Telemundo USA"],
        "type": "scraper",   # us_nbcsports.py handles this
        "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "FuboTV",
        "channels": ["FuboTV Canada ($/geo/R)"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Brazil": {
        "broadcaster": "ESPN",
        "channels": ["ESPN Brasil"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Caribbean": {
        "broadcaster": "ESPN",
        "channels": ["ESPN Caribbean"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Mexico": {
        "broadcaster": "Fox Sports / TNT Mexico",
        "channels": ["Fox Sports MX / TNT Sports MX"],
        "type": "static", "badges": ["live", "free"],
    },
    "Central America": {
        "broadcaster": "Fox Sports / TNT Mexico",
        "channels": ["Fox Sports CA / TNT Sports MX"],
        "type": "static", "badges": ["live", "free"],
    },
    "South America": {
        "broadcaster": "ESPN",
        "channels": ["Star+ / ESPN"],
        "type": "static", "badges": ["live", "tv"],
    },
    # ── Middle East & Africa ──────────────────────────────────────────
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA 1 HD", "beIN Sports MENA 2 HD",
                     "beIN Sports MENA 3 HD", "beIN Sports MENA 4 HD",
                     "beIN Sports MENA English 1 HD",
                     "beIN Connect MENA", "beIN Connect MENA HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Premier League HD", "SuperSport Action HD",
                     "SuperSport Variety 3 HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Botswana": {
        "broadcaster": "YTV",
        "channels": ["YTV Botswana"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Cameroon": {
        "broadcaster": "CRTV Sports",
        "channels": ["CRTV Sports Cameroon"],
        "type": "static", "badges": ["live", "free"],
    },
    "Africa (online)": {
        "broadcaster": "Fast Sports",
        "channels": ["Fast Sports [online] ($/geo/R)"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Africa (mobile)": {
        "broadcaster": "Sporty TV",
        "channels": ["Sporty TV Africa"],
        "type": "static", "badges": ["live", "stream"],
    },
    # ── Asia ──────────────────────────────────────────────────────────
    "India / South Asia": {
        "broadcaster": "JioStar / Star Sports",
        "channels": ["Star Sports Select HD1", "JioCinema (stream)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Malaysia": {
        "broadcaster": "Astro",
        "channels": ["Astro Premier League HD", "Astro Premier League 2 HD",
                     "Astro Premier League 3 HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Hong Kong": {
        "broadcaster": "PCCW / Now TV",
        "channels": ["NOW Premier League HK 1", "NOW Premier League HK 2",
                     "NOW Premier League HK 3",
                     "Hub Premier 1 HD ($/geo/R)", "Hub Premier 2 HD ($/geo/R)",
                     "Hub Premier 3 HD ($/geo/R)", "Hub Premier 4 HD ($/geo/R)",
                     "Hub Premier 8 HD ($/geo/R)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Singapore": {
        "broadcaster": "StarHub",
        "channels": ["Hub Premier 1 HD ($/geo/R)"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "U-Next",
        "channels": ["U-Next JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "South Korea": {
        "broadcaster": "Coupang Play",
        "channels": ["Coupang Play"],
        "type": "static", "badges": ["live", "stream"],
    },
    "China": {
        "broadcaster": "Migu",
        "channels": ["Migu"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Chinese Taipei": {
        "broadcaster": "ELTA",
        "channels": ["ELTA Sports"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Indonesia": {
        "broadcaster": "EMTEK",
        "channels": ["SCTV / Moji"],
        "type": "static", "badges": ["live", "free"],
    },
    "Cambodia / Laos / Thailand": {
        "broadcaster": "Jasmine International / Mono",
        "channels": ["Mono", "True Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Vietnam": {
        "broadcaster": "FPT Play",
        "channels": ["FPT Play", "K+ Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Afghanistan / Central Asia": {
        "broadcaster": "Saran Media",
        "channels": ["Saran TV"],
        "type": "static", "badges": ["live", "tv"],
    },
    # ── Oceania ───────────────────────────────────────────────────────
    "Australia": {
        "broadcaster": "Stan Sport",
        "channels": ["Stan Sport Australia ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "New Zealand": {
        "broadcaster": "Sky NZ",
        "channels": ["Sky Sport NZ"],
        "type": "static", "badges": ["live", "tv"],
    },
    # ── International (inflight/at-sea) ───────────────────────────────
    "International (inflight/at-sea)": {
        "broadcaster": "Sport 24",
        "channels": ["Sport 24 At Sea HD", "Sport 24 In Flight HD", "Sport 24 Extra HD"],
        "type": "static", "badges": ["live", "tv"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# UCL RIGHTS  (2024-27 cycle)
# ─────────────────────────────────────────────────────────────────────
UCL_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "TNT Sports / Channel 5",
        "channels": ["TNT Sports 1", "TNT Sports 2", "TNT Sports Ultimate", "Channel 5 (selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Republic of Ireland": {
        "broadcaster": "Virgin Media / TNT / RTE",
        "channels": ["Virgin Media Sport", "TNT Sports IE", "RTE2 (selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Germany": {
        "broadcaster": "DAZN / ZDF",
        "channels": ["DAZN DE", "ZDF (free, selected)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "France": {
        "broadcaster": "Canal+ / M6",
        "channels": ["Canal+ Sport", "M6 (finals)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Spain": {
        "broadcaster": "Movistar+",
        "channels": ["Movistar Champions League"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Italy": {
        "broadcaster": "Sky Sport / Prime Video",
        "channels": ["Sky Sport Uno", "Sky Sport 252", "Prime Video IT"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Netherlands": {
        "broadcaster": "Ziggo Sport",
        "channels": ["Ziggo Sport"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Portugal": {
        "broadcaster": "DAZN / Sport TV",
        "channels": ["Sport TV 2", "DAZN PT"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Austria": {
        "broadcaster": "Sky Austria",
        "channels": ["Sky Sport Austria"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Belgium": {
        "broadcaster": "RTL / VTM / Proximus",
        "channels": ["Play Sports", "RTL"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Denmark": {
        "broadcaster": "Viaplay",
        "channels": ["Viaplay DK"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Finland": {
        "broadcaster": "MTV",
        "channels": ["MTV Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Norway": {
        "broadcaster": "TV 2",
        "channels": ["TV 2 Sport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Sweden": {
        "broadcaster": "Viaplay",
        "channels": ["Viaplay SE"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Switzerland": {
        "broadcaster": "Blue Sport / SRG SSR",
        "channels": ["Blue Sport 1", "SRF (free, selected)"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Greece": {
        "broadcaster": "MEGA / Cosmote Sport",
        "channels": ["Cosmote Sport 1 HD"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Poland": {
        "broadcaster": "TVP / Canal+",
        "channels": ["Canal+ PL", "TVP Sport (free, selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Turkey": {
        "broadcaster": "TRT",
        "channels": ["TRT Spor", "TRT 1"],
        "type": "static", "badges": ["live", "free"],
    },
    "Ukraine": {
        "broadcaster": "Megogo",
        "channels": ["Megogo"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Russia": {
        "broadcaster": "Okko",
        "channels": ["Okko Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "CBS Sports / Paramount+",
        "channels": ["CBS", "Paramount+", "UniMás"],
        "type": "scraper",  # cbssports.py
        "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Brazil": {
        "broadcaster": "TNT Sports / SBT",
        "channels": ["TNT Sports BR", "HBO Max BR", "SBT"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Latin America": {
        "broadcaster": "ESPN / Warner",
        "channels": ["ESPN LA", "TNT Sports LA"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Mexico": {
        "broadcaster": "Caliente TV / Warner",
        "channels": ["Caliente TV", "HBO Max MX"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports HD 1", "beIN Sports HD 2", "beIN Connect MENA"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport / Canal+ Afrique",
        "channels": ["SuperSport Football (DStv #204)", "Canal+ Afrique"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "India / South Asia": {
        "broadcaster": "Sony Sports Network",
        "channels": ["Sony Sports Ten 2", "SonyLIV"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Malaysia": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports Malaysia"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "WOWOW / DAZN",
        "channels": ["WOWOW Live", "DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "South Korea": {
        "broadcaster": "SPOTV",
        "channels": ["SPOTV"],
        "type": "static", "badges": ["live", "tv"],
    },
    "China": {
        "broadcaster": "iQIYI",
        "channels": ["iQIYI Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Stan Sport",
        "channels": ["Stan Sport"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "New Zealand": {
        "broadcaster": "DAZN",
        "channels": ["DAZN NZ"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# EFL RIGHTS  (Championship / League One / League Two / National League)
# ─────────────────────────────────────────────────────────────────────
EFL_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Sky Sports / iFollow",
        "channels": ["Sky Sports Football", "Sky Sports Main Event", "Sky Sports Mix", "iFollow (stream)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Republic of Ireland": {
        "broadcaster": "Sky Sports / Premier Sports",
        "channels": ["Sky Sports Football", "Premier Sports"],
        "type": "static", "badges": ["live", "tv"],
    },
    "United States": {
        "broadcaster": "ESPN+",
        "channels": ["ESPN+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "New Zealand": {
        "broadcaster": "Sky NZ",
        "channels": ["Sky Sport NZ"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "India / South Asia": {
        "broadcaster": "JioStar",
        "channels": ["JioStar / StarSports"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Malaysia": {
        "broadcaster": "Astro",
        "channels": ["Astro SuperSport"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Hong Kong": {
        "broadcaster": "PCCW / Now TV",
        "channels": ["Now TV HK"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "DAZN",
        "channels": ["DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "International": {
        "broadcaster": "Sky Sports International",
        "channels": ["Sky Sports International"],
        "type": "static", "badges": ["live", "tv"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# SCOTTISH RIGHTS  (Premiership / Championship / Cup)
# ─────────────────────────────────────────────────────────────────────
SCOTTISH_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Sky Sports / Premier Sports / BBC",
        "channels": ["Sky Sports Football", "Sky Sports Main Event",
                     "Premier Sports 1", "Premier Sports 2",
                     "BBC Scotland", "BBC Alba (selected)", "BBC iPlayer"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Republic of Ireland": {
        "broadcaster": "Sky Sports / Premier Sports",
        "channels": ["Sky Sports Football", "Premier Sports"],
        "type": "static", "badges": ["live", "tv"],
    },
    "United States": {
        "broadcaster": "Paramount+",
        "channels": ["Paramount+ US"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "Paramount+",
        "channels": ["Paramount+ CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "International": {
        "broadcaster": "Premier Sports International",
        "channels": ["Premier Sports International"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# LA LIGA  (2025/26)
# ─────────────────────────────────────────────────────────────────────
LALIGA_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Premier Sports / FreeSports",
        "channels": ["Premier Sports 1", "Premier Sports 2", "FreeSports (selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Republic of Ireland": {
        "broadcaster": "Premier Sports",
        "channels": ["Premier Sports 1"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Spain": {
        "broadcaster": "DAZN / Movistar",
        "channels": ["DAZN 1 Espana HD", "DAZN 2 Espana HD", "Movistar LaLiga",
                     "DAZN España ($/geo/R)"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Germany": {
        "broadcaster": "DAZN",
        "channels": ["DAZN DE"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "France": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports FR 1"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Italy": {
        "broadcaster": "DAZN",
        "channels": ["DAZN IT"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Netherlands": {
        "broadcaster": "Viaplay",
        "channels": ["Viaplay NL"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Portugal": {
        "broadcaster": "Eleven Sports",
        "channels": ["Eleven Sports PT"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "ESPN+",
        "channels": ["ESPN+", "ESPN Deportes"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Brazil / South America": {
        "broadcaster": "ESPN / Star+",
        "channels": ["ESPN BR", "Star+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports HD 3"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "India / South Asia": {
        "broadcaster": "JioStar / Sony",
        "channels": ["Sony Sports TEN"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Japan": {
        "broadcaster": "DAZN",
        "channels": ["DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# BUNDESLIGA  (2025/26)
# ─────────────────────────────────────────────────────────────────────
BUNDESLIGA_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Sky Sports / TNT Sports",
        "channels": ["Sky Sports Football", "Sky Sports Main Event", "TNT Sports (selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Germany": {
        "broadcaster": "Sky Deutschland / DAZN / Sat.1",
        "channels": ["Sky Sport Bundesliga 1 HD", "Sky Sport Bundesliga 2 HD",
                     "DAZN DE", "Sat.1 (free, selected)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Austria": {
        "broadcaster": "Sky Austria",
        "channels": ["Sky Sport Bundesliga AT"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Switzerland": {
        "broadcaster": "Blue Sport",
        "channels": ["Blue Sport 1"],
        "type": "static", "badges": ["live", "tv"],
    },
    "France": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports FR"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Spain": {
        "broadcaster": "DAZN",
        "channels": ["DAZN ES"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Italy": {
        "broadcaster": "DAZN",
        "channels": ["DAZN IT"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "ESPN+",
        "channels": ["ESPN+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "DAZN",
        "channels": ["DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# SERIE A  (2025/26)
# ─────────────────────────────────────────────────────────────────────
SERIEA_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "TNT Sports / Discovery+",
        "channels": ["TNT Sports 4", "Discovery+"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Italy": {
        "broadcaster": "DAZN / Sky Italia",
        "channels": ["DAZN IT", "Sky Sport Calcio", "Sky Sport 251"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Germany": {
        "broadcaster": "DAZN",
        "channels": ["DAZN DE"],
        "type": "static", "badges": ["live", "stream"],
    },
    "France": {
        "broadcaster": "Canal+ Sport",
        "channels": ["Canal+ Sport FR"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Spain": {
        "broadcaster": "DAZN",
        "channels": ["DAZN ES"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Netherlands": {
        "broadcaster": "Viaplay",
        "channels": ["Viaplay NL"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "Paramount+ / CBS Golazo",
        "channels": ["Paramount+", "CBS Sports Golazo"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Brazil / South America": {
        "broadcaster": "ESPN / Star+",
        "channels": ["ESPN BR", "Star+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "SuperSport",
        "channels": ["SuperSport Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "DAZN",
        "channels": ["DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Paramount+",
        "channels": ["Paramount+ AU"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# LIGUE 1  (2025/26)
# ─────────────────────────────────────────────────────────────────────
LIGUE1_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "beIN Sports UK",
        "channels": ["beIN Sports UK 1"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "France": {
        "broadcaster": "Canal+ / Amazon Prime / beIN Sports",
        "channels": ["Canal+", "Canal+ Sport", "Amazon Prime Video FR", "beIN Sports FR"],
        "type": "epg", "badges": ["live", "stream"],
    },
    "Germany": {
        "broadcaster": "DAZN",
        "channels": ["DAZN DE"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "beIN Sports USA / fuboTV",
        "channels": ["beIN Sports USA", "fuboTV"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "beIN Sports CA",
        "channels": ["beIN Sports CA"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Sub-Saharan Africa": {
        "broadcaster": "Canal+ Afrique",
        "channels": ["Canal+ Afrique"],
        "type": "static", "badges": ["live", "tv"],
    },
    "Japan": {
        "broadcaster": "DAZN",
        "channels": ["DAZN JP"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# EREDIVISIE  (2025/26)
# ─────────────────────────────────────────────────────────────────────
EREDIVISIE_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Viaplay UK",
        "channels": ["Viaplay UK"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Netherlands": {
        "broadcaster": "ESPN NL / NOS",
        "channels": ["ESPN 1", "ESPN 2", "ESPN 3", "NOS (highlights)"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Belgium": {
        "broadcaster": "Eleven Sports",
        "channels": ["Eleven Sports BE"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Germany": {
        "broadcaster": "DAZN",
        "channels": ["DAZN DE"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "ESPN+",
        "channels": ["ESPN+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "static", "badges": ["live", "tv"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# PRIMEIRA LIGA  (2025/26)
# ─────────────────────────────────────────────────────────────────────
PRIMEIRA_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Premier Sports / Eleven Sports",
        "channels": ["Premier Sports 1", "Eleven Sports UK"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Portugal": {
        "broadcaster": "Sport TV",
        "channels": ["Sport TV 1", "Sport TV 2"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Brazil / South America": {
        "broadcaster": "ESPN / Star+",
        "channels": ["ESPN BR", "Star+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "United States": {
        "broadcaster": "GolTV / Fubo",
        "channels": ["GolTV", "fuboTV"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Middle East & North Africa": {
        "broadcaster": "beIN Sports",
        "channels": ["beIN Sports MENA"],
        "type": "static", "badges": ["live", "tv"],
    },
    "International": {
        "broadcaster": "Eleven Sports",
        "channels": ["Eleven Sports International"],
        "type": "static", "badges": ["live", "stream"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# FA CUP
# ─────────────────────────────────────────────────────────────────────
FACUP_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "BBC / ITV / Channel 4",
        "channels": ["BBC One", "BBC Two", "BBC iPlayer",
                     "ITV", "ITV4", "ITVX",
                     "Channel 4", "Channel 4 Sport"],
        "type": "epg", "badges": ["live", "free"],
    },
    "Republic of Ireland": {
        "broadcaster": "ITV / RTE",
        "channels": ["ITV", "RTE (selected)"],
        "type": "static", "badges": ["live", "free"],
    },
    "United States": {
        "broadcaster": "ESPN+",
        "channels": ["ESPN+"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Canada": {
        "broadcaster": "DAZN",
        "channels": ["DAZN CA"],
        "type": "static", "badges": ["live", "stream"],
    },
    "Australia": {
        "broadcaster": "Optus Sport",
        "channels": ["Optus Sport"],
        "type": "static", "badges": ["live", "stream"],
    },
    "International": {
        "broadcaster": "BBC Studios International",
        "channels": ["BBC Studios International"],
        "type": "static", "badges": ["live", "tv"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# EFL CUP (Carabao Cup)
# ─────────────────────────────────────────────────────────────────────
EFLCUP_RIGHTS = {
    "United Kingdom": {
        "broadcaster": "Sky Sports",
        "channels": ["Sky Sports Football", "Sky Sports Main Event"],
        "type": "epg", "badges": ["live", "tv"],
    },
    "Republic of Ireland": {
        "broadcaster": "Sky Sports",
        "channels": ["Sky Sports Football"],
        "type": "static", "badges": ["live", "tv"],
    },
    "International": {
        "broadcaster": "Sky Sports International",
        "channels": ["Sky Sports International"],
        "type": "static", "badges": ["live", "tv"],
    },
}

# ─────────────────────────────────────────────────────────────────────
# COMPETITION → RIGHTS MAP
# ─────────────────────────────────────────────────────────────────────
COMPETITION_RIGHTS = {
    "EPL":        EPL_RIGHTS,
    "UCL":        UCL_RIGHTS,
    "EFL-CH":     EFL_RIGHTS,
    "EFL-L1":     EFL_RIGHTS,
    "EFL-L2":     EFL_RIGHTS,
    "NAT":        EFL_RIGHTS,
    "SPL":        SCOTTISH_RIGHTS,
    "SCH":        SCOTTISH_RIGHTS,
    "SCUP":       SCOTTISH_RIGHTS,
    "LALIGA":     LALIGA_RIGHTS,
    "BUNDESLIGA": BUNDESLIGA_RIGHTS,
    "SERIEA":     SERIEA_RIGHTS,
    "SERIEB":     SERIEA_RIGHTS,
    "LIGUE1":     LIGUE1_RIGHTS,
    "EREDIVISIE": EREDIVISIE_RIGHTS,
    "PRIMEIRA":   PRIMEIRA_RIGHTS,
    "FACUP":      FACUP_RIGHTS,
    "EFLCUP":     EFLCUP_RIGHTS,
}


def get_rights(competition_code):
    """Return the rights dict for a given competition code."""
    return COMPETITION_RIGHTS.get(competition_code, {})
