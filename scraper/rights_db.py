"""
rights_db.py — TVsport broadcast rights database
Built from Broadcast_rights_updated_100426.xlsx
Covers: EPL (overseas + UK), UCL, EFL, Scottish, La Liga, Bundesliga, Serie A, Ligue 1
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL METADATA
# Maps broadcaster name → { channels, type, url }
# type: "pay_tv" | "free_tv" | "streaming"
# ─────────────────────────────────────────────────────────────────────────────

BROADCASTER_META = {
    # UK
    "Sky Sports":        {"channels": ["Sky Sports Main Event", "Sky Sports Premier League", "Sky Sports Football", "Sky Sports Action"], "type": "pay_tv"},
    "TNT Sports":        {"channels": ["TNT Sports 1", "TNT Sports 2", "TNT Sports 3", "TNT Sports 4"], "type": "pay_tv"},
    "BBC":               {"channels": ["BBC One", "BBC Two", "BBC iPlayer"], "type": "free_tv"},
    "ITV":               {"channels": ["ITV1", "ITVX"], "type": "free_tv"},
    "Prime Video":       {"channels": ["Amazon Prime Video"], "type": "streaming"},
    "Premier Sports":    {"channels": ["Premier Sports 1", "Premier Sports 2"], "type": "pay_tv"},
    "FreeSports":        {"channels": ["FreeSports"], "type": "free_tv"},
    # Europe
    "CANAL+":            {"channels": ["Canal+ Sport", "Canal+ Foot"], "type": "pay_tv"},
    "beIN Sports":       {"channels": ["beIN Sports 1", "beIN Sports 2", "beIN Sports 3"], "type": "pay_tv"},
    "Sky Deutschland":   {"channels": ["Sky Sport 1", "Sky Sport 2", "Sky Sport Bundesliga"], "type": "pay_tv"},
    "Sky Italia":        {"channels": ["Sky Sport 1 IT", "Sky Sport Calcio"], "type": "pay_tv"},
    "DAZN":              {"channels": ["DAZN 1", "DAZN 2"], "type": "streaming"},
    "Viaplay":           {"channels": ["Viaplay Sport 1", "Viaplay Sport 2"], "type": "streaming"},
    "Movistar Plus+":    {"channels": ["Movistar LaLiga", "Movistar Liga de Campeones"], "type": "pay_tv"},
    "Arena Sport":       {"channels": ["Arena Sport 1", "Arena Sport 2"], "type": "pay_tv"},
    "Nova Sports":       {"channels": ["Nova Sports 1", "Nova Sports 2"], "type": "pay_tv"},
    "Ziggo Sport":       {"channels": ["Ziggo Sport"], "type": "pay_tv"},
    "Eleven Sports":     {"channels": ["Eleven Sports 1", "Eleven Sports 2"], "type": "pay_tv"},
    "RTL":               {"channels": ["RTL"], "type": "free_tv"},
    "TV2":               {"channels": ["TV 2 Sport"], "type": "pay_tv"},
    "MTV":               {"channels": ["MTV3 Sport"], "type": "pay_tv"},
    "Cosmote Sport":     {"channels": ["Cosmote Sport 1", "Cosmote Sport 2"], "type": "pay_tv"},
    "Tring":             {"channels": ["Tring Sport 1"], "type": "pay_tv"},
    "Digitalb":          {"channels": ["Digitalb"], "type": "pay_tv"},
    "Play Sports":       {"channels": ["Play Sports"], "type": "pay_tv"},
    "Blue Sport":        {"channels": ["Blue Sport 1"], "type": "pay_tv"},
    # Americas
    "NBC Sports":        {"channels": ["NBC", "USA Network", "Peacock"], "type": "pay_tv"},
    "ESPN":              {"channels": ["ESPN", "ESPN2", "ESPN+"], "type": "pay_tv"},
    "CBS Sports":        {"channels": ["CBS", "Paramount+", "CBS Sports Golazo"], "type": "pay_tv"},
    "Fubo":              {"channels": ["Fubo Sports"], "type": "streaming"},
    "DAZN CA":           {"channels": ["DAZN Canada"], "type": "streaming"},
    "TNT Sports Mexico": {"channels": ["TNT Sports Mexico", "Max Mexico"], "type": "pay_tv"},
    # Asia-Pacific
    "Stan Sport":        {"channels": ["Stan Sport"], "type": "streaming"},
    "Optus Sport":       {"channels": ["Optus Sport"], "type": "streaming"},
    "Sky NZ":            {"channels": ["Sky Sport NZ"], "type": "pay_tv"},
    "JioStar":           {"channels": ["JioStar Sports", "Star Sports 1", "Star Sports 2"], "type": "streaming"},
    "Astro":             {"channels": ["Astro SuperSport 2", "Astro SuperSport 3"], "type": "pay_tv"},
    "beIN Sports MENA":  {"channels": ["beIN Sports HD 1", "beIN Sports HD 2", "beIN Sports HD 3"], "type": "pay_tv"},
    "StarHub":           {"channels": ["StarHub Sports"], "type": "pay_tv"},
    "PCCW":              {"channels": ["Now Sports", "Now Premier League Channel"], "type": "pay_tv"},
    "U-Next":            {"channels": ["U-Next Soccer"], "type": "streaming"},
    "WOWOW":             {"channels": ["WOWOW"], "type": "pay_tv"},
    "SPOTV":             {"channels": ["SPOTV"], "type": "pay_tv"},
    "Coupang":           {"channels": ["Coupang Play"], "type": "streaming"},
    "Migu":              {"channels": ["Migu Video"], "type": "streaming"},
    "EMTEK":             {"channels": ["SCTV", "Vidio"], "type": "pay_tv"},
    # Africa
    "SuperSport":        {"channels": ["SuperSport Premier League", "SuperSport Football", "SuperSport Variety 1"], "type": "pay_tv"},
    "Canal+ Afrique":    {"channels": ["Canal+ Sport Afrique"], "type": "pay_tv"},
    "YTV":               {"channels": ["YTV Botswana"], "type": "free_tv"},
    "CRTV Sports":       {"channels": ["CRTV Sport"], "type": "free_tv"},
    # International
    "Sport 24":          {"channels": ["Sport 24"], "type": "pay_tv"},
}

# ─────────────────────────────────────────────────────────────────────────────
# EPL OVERSEAS BROADCAST RIGHTS  (2025/26 – 2027/28)
# ─────────────────────────────────────────────────────────────────────────────

EPL_RIGHTS = {
    # Europe
    "Albania":                    {"broadcaster": "Digitalb",                            "region": "Europe"},
    "Andorra":                    {"broadcaster": "CANAL+ / DAZN",                       "region": "Europe"},
    "Armenia":                    {"broadcaster": "Saran Media",                          "region": "Europe"},
    "Austria":                    {"broadcaster": "Sky Deutschland",                      "region": "Europe"},
    "Belarus":                    {"broadcaster": "Saran Media",                          "region": "Europe"},
    "Belgium":                    {"broadcaster": "Telenet",                              "region": "Europe"},
    "Bulgaria":                   {"broadcaster": "IMG / Nova Broadcasting Group",        "region": "Europe"},
    "Croatia":                    {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Cyprus":                     {"broadcaster": "Cytavision",                           "region": "Europe"},
    "Czech Republic":             {"broadcaster": "CANAL+",                               "region": "Europe"},
    "Denmark":                    {"broadcaster": "Viaplay",                              "region": "Europe"},
    "Estonia":                    {"broadcaster": "TV3",                                  "region": "Europe"},
    "Finland":                    {"broadcaster": "Viaplay",                              "region": "Europe"},
    "France":                     {"broadcaster": "CANAL+",                               "region": "Europe"},
    "Georgia":                    {"broadcaster": "Saran Media",                          "region": "Europe"},
    "Germany":                    {"broadcaster": "Sky Deutschland",                      "region": "Europe"},
    "Greece":                     {"broadcaster": "IMG / Nova",                           "region": "Europe"},
    "Hungary":                    {"broadcaster": "TV2",                                  "region": "Europe"},
    "Iceland":                    {"broadcaster": "Syn",                                  "region": "Europe"},
    "Israel":                     {"broadcaster": "Charlton",                             "region": "Europe"},
    "Republic of Ireland":        {"broadcaster": "Sky Sports; TNT Sports; Premier Sports","region": "Europe"},
    "Italy":                      {"broadcaster": "Sky Italia",                           "region": "Europe"},
    "Kosovo":                     {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Latvia":                     {"broadcaster": "TV3",                                  "region": "Europe"},
    "Lithuania":                  {"broadcaster": "TV3",                                  "region": "Europe"},
    "Luxembourg":                 {"broadcaster": "CANAL+",                               "region": "Europe"},
    "Malta":                      {"broadcaster": "TSN",                                  "region": "Europe"},
    "Moldova":                    {"broadcaster": "Saran Media",                          "region": "Europe"},
    "Montenegro":                 {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Netherlands":                {"broadcaster": "Viaplay",                              "region": "Europe"},
    "North Macedonia":            {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Norway":                     {"broadcaster": "Viaplay",                              "region": "Europe"},
    "Poland":                     {"broadcaster": "CANAL+",                               "region": "Europe"},
    "Portugal":                   {"broadcaster": "DAZN",                                 "region": "Europe"},
    "Romania":                    {"broadcaster": "Saran Media; VOYO / Pro TV",           "region": "Europe"},
    "Serbia":                     {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Slovakia":                   {"broadcaster": "CANAL+",                               "region": "Europe"},
    "Slovenia":                   {"broadcaster": "Arena Sport",                          "region": "Europe"},
    "Spain":                      {"broadcaster": "DAZN",                                 "region": "Europe"},
    "Sweden":                     {"broadcaster": "Viaplay",                              "region": "Europe"},
    "Switzerland":                {"broadcaster": "CANAL+ (FR); Sky Deutschland (DE); Sky Italia (IT)", "region": "Europe"},
    "Turkey":                     {"broadcaster": "beIN Sports",                          "region": "Europe"},
    "Ukraine":                    {"broadcaster": "Setanta; Monomax",                     "region": "Europe"},
    # Asia-Pacific
    "Australia":                  {"broadcaster": "Stan Sport",                           "region": "Asia-Pacific"},
    "New Zealand":                {"broadcaster": "Sky NZ",                               "region": "Asia-Pacific"},
    "Pacific Islands":            {"broadcaster": "Digicel",                              "region": "Asia-Pacific"},
    # Asia
    "Afghanistan":                {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Azerbaijan":                 {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Cambodia":                   {"broadcaster": "Jasmine International / Mono",         "region": "Asia"},
    "China":                      {"broadcaster": "Migu",                                 "region": "Asia"},
    "Chinese Taipei":             {"broadcaster": "ELTA",                                 "region": "Asia"},
    "Hong Kong":                  {"broadcaster": "PCCW",                                 "region": "Asia"},
    "Indonesia":                  {"broadcaster": "EMTEK",                                "region": "Asia"},
    "Japan":                      {"broadcaster": "U-Next",                               "region": "Asia"},
    "Kazakhstan":                 {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Kyrgyzstan":                 {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Laos":                       {"broadcaster": "Jasmine International / Mono",         "region": "Asia"},
    "Macao":                      {"broadcaster": "M Plus",                               "region": "Asia"},
    "Malaysia":                   {"broadcaster": "Astro",                                "region": "Asia"},
    "Mongolia":                   {"broadcaster": "Unitel",                               "region": "Asia"},
    "Myanmar":                    {"broadcaster": "CANAL+",                               "region": "Asia"},
    "Singapore":                  {"broadcaster": "StarHub",                              "region": "Asia"},
    "South Asia":                 {"broadcaster": "JioStar",                              "region": "Asia"},
    "South Korea":                {"broadcaster": "Coupang",                              "region": "Asia"},
    "Tajikistan":                 {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Thailand":                   {"broadcaster": "Jasmine International / Mono",         "region": "Asia"},
    "Turkmenistan":               {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Uzbekistan":                 {"broadcaster": "Saran Media",                          "region": "Asia"},
    "Vietnam":                    {"broadcaster": "FPT Play / Jasmine International / Mono","region": "Asia"},
    # MENA / Africa
    "Middle East & N. Africa":    {"broadcaster": "beIN Sports",                          "region": "Middle East & N. Africa"},
    "Sub-Saharan Africa":         {"broadcaster": "SuperSport",                           "region": "Africa"},
    "Botswana":                   {"broadcaster": "YTV",                                  "region": "Africa"},
    "Cameroon":                   {"broadcaster": "CRTV Sports",                          "region": "Africa"},
    # Americas
    "Brazil":                     {"broadcaster": "ESPN",                                 "region": "Americas"},
    "Canada":                     {"broadcaster": "Fubo",                                 "region": "Americas"},
    "Caribbean":                  {"broadcaster": "ESPN",                                 "region": "Americas"},
    "Costa Rica":                 {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "El Salvador":                {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "Guatemala":                  {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "Honduras":                   {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "Mexico":                     {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "Nicaragua":                  {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "Panama":                     {"broadcaster": "Fox Broadcasting Corporation; TNT Sports Mexico", "region": "Americas"},
    "South America":              {"broadcaster": "ESPN",                                 "region": "Americas"},
    "United States":              {"broadcaster": "NBC Sports",                           "region": "Americas"},
    # International
    "International (inflight / at-sea)": {"broadcaster": "Sport 24",                     "region": "International"},
}

# EPL UK rights (handled separately with blackout logic)
EPL_UK_RIGHTS = {
    "United Kingdom": {
        "Sky Sports":  {"channels": ["Sky Sports Main Event", "Sky Sports Premier League", "Sky Sports Football"], "type": "pay_tv"},
        "TNT Sports":  {"channels": ["TNT Sports 1", "TNT Sports 2"], "type": "pay_tv"},
        "BBC":         {"channels": ["BBC iPlayer", "BBC One"], "type": "free_tv", "coverage": "highlights"},
        "Prime Video": {"channels": ["Amazon Prime Video"], "type": "streaming"},
    }
}

# 3pm Saturday blackout — no UK broadcaster shown for these slots
EPL_BLACKOUT_SLOTS = [
    {"day": "Saturday", "kickoff_hour": 15, "kickoff_minute": 0},
]

# ─────────────────────────────────────────────────────────────────────────────
# UCL BROADCAST RIGHTS  (2024-27 Cycle)
# ─────────────────────────────────────────────────────────────────────────────

UCL_RIGHTS = {
    "Afghanistan":          {"broadcaster": "Arezo TV; Solhsports",                  "region": "Asia"},
    "Albania":              {"broadcaster": "Tring; Vizion Plus",                    "region": "Europe"},
    "Armenia":              {"broadcaster": "Fast Sports",                            "region": "Europe"},
    "Australia":            {"broadcaster": "Stan Sport",                             "region": "Asia-Pacific"},
    "Austria":              {"broadcaster": "Sky Sport; Canal+",                     "region": "Europe"},
    "Azerbaijan":           {"broadcaster": "CBC Sport; İTV",                        "region": "Europe"},
    "Belgium":              {"broadcaster": "RTL; VTM; Proximus; Play Sports",       "region": "Europe"},
    "Bosnia & Herz.":       {"broadcaster": "Arena Sport",                            "region": "Europe"},
    "Brazil":               {"broadcaster": "TNT Sports; SBT",                       "region": "Americas"},
    "Brunei":               {"broadcaster": "beIN Sports",                            "region": "Asia"},
    "Bulgaria":             {"broadcaster": "bTV; Max Sport",                        "region": "Europe"},
    "Cambodia":             {"broadcaster": "beIN Sports",                            "region": "Asia"},
    "Cameroon":             {"broadcaster": "CRTV",                                  "region": "Africa"},
    "Canada":               {"broadcaster": "DAZN",                                  "region": "Americas"},
    "Caribbean":            {"broadcaster": "Rush Sports",                            "region": "Americas"},
    "Central America":      {"broadcaster": "ESPN",                                  "region": "Americas"},
    "China":                {"broadcaster": "iQIYI",                                 "region": "Asia"},
    "Croatia":              {"broadcaster": "HRT; Arena Sport",                      "region": "Europe"},
    "Cyprus":               {"broadcaster": "CYTA",                                  "region": "Europe"},
    "Czech Republic":       {"broadcaster": "Nova Sport",                             "region": "Europe"},
    "Denmark":              {"broadcaster": "Viaplay",                               "region": "Europe"},
    "Dominican Republic":   {"broadcaster": "Antena 7",                              "region": "Americas"},
    "Estonia":              {"broadcaster": "Go3 Sport",                             "region": "Europe"},
    "Finland":              {"broadcaster": "MTV",                                   "region": "Europe"},
    "France":               {"broadcaster": "Canal+; M6",                            "region": "Europe"},
    "Georgia":              {"broadcaster": "Setanta Sports; Silk Sport",            "region": "Europe"},
    "Germany":              {"broadcaster": "DAZN; Prime Video; ZDF",               "region": "Europe"},
    "Gibraltar":            {"broadcaster": "Gibtelecom",                            "region": "Europe"},
    "Greece":               {"broadcaster": "MEGA; Cosmote Sport",                  "region": "Europe"},
    "Haiti":                {"broadcaster": "Canal+",                                "region": "Americas"},
    "Hong Kong":            {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Hungary":              {"broadcaster": "RTL; Sport1",                           "region": "Europe"},
    "Iceland":              {"broadcaster": "Sýn; Viaplay",                          "region": "Europe"},
    "Indian Subcontinent":  {"broadcaster": "Sony Sports Network",                   "region": "Asia"},
    "Indonesia":            {"broadcaster": "beIN Sports; Emtek",                    "region": "Asia"},
    "Iran":                 {"broadcaster": "IRIB TV3; Persiana Sports; GEM Sport",  "region": "Asia"},
    "Ireland":              {"broadcaster": "RTÉ; Premier Sports; TNT Sports; Prime Video", "region": "Europe"},
    "Israel":               {"broadcaster": "Sports Channel",                        "region": "Middle East"},
    "Italy":                {"broadcaster": "Sky Sport; Prime Video",                "region": "Europe"},
    "Ivory Coast":          {"broadcaster": "NCI",                                   "region": "Africa"},
    "Jamaica":              {"broadcaster": "TVJ",                                   "region": "Americas"},
    "Japan":                {"broadcaster": "WOWOW",                                 "region": "Asia"},
    "Kazakhstan":           {"broadcaster": "Qazsport; Q Sport",                    "region": "Asia"},
    "Kosovo":               {"broadcaster": "RTK; ArtMotion",                        "region": "Europe"},
    "Kyrgyzstan":           {"broadcaster": "Q Sport",                               "region": "Asia"},
    "Laos":                 {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Latvia":               {"broadcaster": "Go3 Sport",                             "region": "Europe"},
    "Lithuania":            {"broadcaster": "Go3 Sport",                             "region": "Europe"},
    "Luxembourg":           {"broadcaster": "RTL; Proximus",                         "region": "Europe"},
    "Macau":                {"broadcaster": "TDM",                                   "region": "Asia"},
    "Malaysia":             {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Malta":                {"broadcaster": "PBS; TSN",                              "region": "Europe"},
    "Mauritius":            {"broadcaster": "MBC",                                   "region": "Africa"},
    "MENA":                 {"broadcaster": "beIN Sports",                           "region": "Middle East & N. Africa"},
    "Mexico":               {"broadcaster": "Caliente TV; Warner Bros. Discovery",  "region": "Americas"},
    "Moldova":              {"broadcaster": "Jurnal TV; Setanta Sports",             "region": "Europe"},
    "Mongolia":             {"broadcaster": "PSN",                                   "region": "Asia"},
    "Montenegro":           {"broadcaster": "Arena Sport",                           "region": "Europe"},
    "Myanmar":              {"broadcaster": "Canal+",                                "region": "Asia"},
    "Netherlands":          {"broadcaster": "Ziggo Sport",                           "region": "Europe"},
    "New Zealand":          {"broadcaster": "DAZN",                                  "region": "Asia-Pacific"},
    "North Macedonia":      {"broadcaster": "Arena Sport",                           "region": "Europe"},
    "Norway":               {"broadcaster": "TV 2",                                  "region": "Europe"},
    "Pakistan":             {"broadcaster": "tapmad",                                "region": "Asia"},
    "Philippines":          {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Poland":               {"broadcaster": "TVP; Canal+",                           "region": "Europe"},
    "Portugal":             {"broadcaster": "DAZN; Sport TV",                        "region": "Europe"},
    "Romania":              {"broadcaster": "Digi Sport; Prima Sport",               "region": "Europe"},
    "Russia":               {"broadcaster": "Okko",                                  "region": "Europe"},
    "Serbia":               {"broadcaster": "RTS; Arena Sport",                      "region": "Europe"},
    "Singapore":            {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Slovakia":             {"broadcaster": "Nova Sport",                             "region": "Europe"},
    "Slovenia":             {"broadcaster": "Pro Plus; Sport Klub",                  "region": "Europe"},
    "South America":        {"broadcaster": "ESPN",                                  "region": "Americas"},
    "South Korea":          {"broadcaster": "SPOTV",                                 "region": "Asia"},
    "Spain":                {"broadcaster": "Movistar Plus+",                        "region": "Europe"},
    "Sub-Saharan Africa":   {"broadcaster": "SuperSport; Canal+ Afrique; New World TV", "region": "Africa"},
    "Suriname":             {"broadcaster": "ATV",                                   "region": "Americas"},
    "Sweden":               {"broadcaster": "Viaplay",                               "region": "Europe"},
    "Switzerland":          {"broadcaster": "SRG SSR; Blue Sport",                  "region": "Europe"},
    "Taiwan":               {"broadcaster": "ELTA",                                  "region": "Asia"},
    "Tajikistan":           {"broadcaster": "Varzish TV",                            "region": "Asia"},
    "Thailand":             {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Timor Leste":          {"broadcaster": "beIN Sports",                           "region": "Asia"},
    "Turkey":               {"broadcaster": "TRT",                                   "region": "Europe"},
    "Ukraine":              {"broadcaster": "Megogo",                                "region": "Europe"},
    "United Kingdom":       {"broadcaster": "TNT Sports; Prime Video; BBC",         "region": "Europe"},
    "United States":        {"broadcaster": "CBS Sports; TelevisaUnivision; DAZN",  "region": "Americas"},
    "Uzbekistan":           {"broadcaster": "Zo'r TV",                               "region": "Asia"},
    "Vietnam":              {"broadcaster": "VTVcab; Viettel",                       "region": "Asia"},
    "Pacific Islands":      {"broadcaster": "Digicel",                               "region": "Asia-Pacific"},
}

# ─────────────────────────────────────────────────────────────────────────────
# EFL BROADCAST RIGHTS  (2025/26)
# ─────────────────────────────────────────────────────────────────────────────

EFL_RIGHTS = {
    "United Kingdom":             {"broadcaster": "Sky Sports",                        "region": "UK"},
    "Republic of Ireland":        {"broadcaster": "Sky Sports; Premier Sports",        "region": "Europe"},
    "Albania":                    {"broadcaster": "SuperSport Albania",                "region": "Europe"},
    "Armenia":                    {"broadcaster": "Saran Media",                       "region": "Europe"},
    "Austria":                    {"broadcaster": "Sky Deutschland",                   "region": "Europe"},
    "Belgium":                    {"broadcaster": "Eleven Sports",                     "region": "Europe"},
    "Bulgaria":                   {"broadcaster": "IMG / Nova",                        "region": "Europe"},
    "Croatia":                    {"broadcaster": "Arena Sport",                       "region": "Europe"},
    "Czech Republic":             {"broadcaster": "CANAL+",                            "region": "Europe"},
    "Denmark":                    {"broadcaster": "Viaplay",                           "region": "Europe"},
    "Estonia":                    {"broadcaster": "Go3 / TV3",                         "region": "Europe"},
    "Finland":                    {"broadcaster": "Viaplay",                           "region": "Europe"},
    "France":                     {"broadcaster": "CANAL+",                            "region": "Europe"},
    "Germany":                    {"broadcaster": "Sky Deutschland",                   "region": "Europe"},
    "Greece":                     {"broadcaster": "Nova Sports",                       "region": "Europe"},
    "Hungary":                    {"broadcaster": "TV2 Sport",                         "region": "Europe"},
    "Israel":                     {"broadcaster": "Sport Channel",                     "region": "Europe"},
    "Italy":                      {"broadcaster": "Sky Italia",                        "region": "Europe"},
    "Latvia":                     {"broadcaster": "Go3 / TV3",                         "region": "Europe"},
    "Lithuania":                  {"broadcaster": "Go3 / TV3",                         "region": "Europe"},
    "Netherlands":                {"broadcaster": "Viaplay",                           "region": "Europe"},
    "Norway":                     {"broadcaster": "Viaplay",                           "region": "Europe"},
    "Poland":                     {"broadcaster": "CANAL+",                            "region": "Europe"},
    "Portugal":                   {"broadcaster": "DAZN",                              "region": "Europe"},
    "Romania":                    {"broadcaster": "VOYO / Pro TV",                     "region": "Europe"},
    "Serbia":                     {"broadcaster": "Arena Sport",                       "region": "Europe"},
    "Spain":                      {"broadcaster": "DAZN",                              "region": "Europe"},
    "Sweden":                     {"broadcaster": "Viaplay",                           "region": "Europe"},
    "Switzerland":                {"broadcaster": "Blue Sport; Sky Deutschland",       "region": "Europe"},
    "Turkey":                     {"broadcaster": "beIN Sports",                       "region": "Europe"},
    "Ukraine":                    {"broadcaster": "Monomax",                           "region": "Europe"},
    "United States":              {"broadcaster": "ESPN+",                             "region": "Americas"},
    "Canada":                     {"broadcaster": "DAZN",                              "region": "Americas"},
    "Brazil":                     {"broadcaster": "ESPN BR",                           "region": "Americas"},
    "Australia":                  {"broadcaster": "Optus Sport",                       "region": "Asia-Pacific"},
    "New Zealand":                {"broadcaster": "Sky NZ",                            "region": "Asia-Pacific"},
    "Middle East & N. Africa":    {"broadcaster": "beIN Sports",                       "region": "Middle East & N. Africa"},
    "Sub-Saharan Africa":         {"broadcaster": "SuperSport",                        "region": "Africa"},
    "India / South Asia":         {"broadcaster": "JioStar",                           "region": "Asia"},
    "Malaysia":                   {"broadcaster": "Astro",                             "region": "Asia"},
    "Hong Kong":                  {"broadcaster": "PCCW / Now TV",                    "region": "Asia"},
    "Japan":                      {"broadcaster": "DAZN",                              "region": "Asia"},
    "South Korea":                {"broadcaster": "Coupang Play",                      "region": "Asia"},
}

# ─────────────────────────────────────────────────────────────────────────────
# SCOTTISH FOOTBALL BROADCAST RIGHTS  (2025/26)
# ─────────────────────────────────────────────────────────────────────────────

SCOTTISH_RIGHTS = {
    "United Kingdom":          {"broadcaster": "Sky Sports; Premier Sports; BBC Scotland; BBC Alba", "region": "UK"},
    "Republic of Ireland":     {"broadcaster": "Sky Sports; Premier Sports",       "region": "Europe"},
    "United States":           {"broadcaster": "Paramount+",                       "region": "Americas"},
    "Canada":                  {"broadcaster": "Paramount+",                       "region": "Americas"},
    "Australia":               {"broadcaster": "Optus Sport",                      "region": "Asia-Pacific"},
    "Middle East & N. Africa": {"broadcaster": "beIN Sports",                      "region": "Middle East & N. Africa"},
    "Sub-Saharan Africa":      {"broadcaster": "SuperSport",                       "region": "Africa"},
    "International":           {"broadcaster": "Premier Sports International",     "region": "International"},
}

# ─────────────────────────────────────────────────────────────────────────────
# EUROPEAN LEAGUES BROADCAST RIGHTS  (2025/26)
# Covers: La Liga, Bundesliga, Serie A, Ligue 1
# ─────────────────────────────────────────────────────────────────────────────

EUROPEAN_LEAGUES_RIGHTS = {
    # Format: territory -> { "la_liga": ..., "bundesliga": ..., "serie_a": ..., "ligue_1": ... }
    "United Kingdom":         {"la_liga": "Premier Sports; FreeSports", "bundesliga": "Sky Sports; TNT Sports", "serie_a": "TNT Sports; Discovery+", "ligue_1": "beIN Sports UK"},
    "Republic of Ireland":    {"la_liga": "Premier Sports",             "bundesliga": "Sky Sports",             "serie_a": "TNT Sports",             "ligue_1": "beIN Sports"},
    "United States":          {"la_liga": "ESPN+; ESPN Deportes",        "bundesliga": "ESPN+",                  "serie_a": "Paramount+; CBS Golazo",  "ligue_1": "beIN Sports USA; fuboTV"},
    "Canada":                 {"la_liga": "DAZN",                        "bundesliga": "DAZN",                   "serie_a": "DAZN",                    "ligue_1": "beIN Sports CA"},
    "Germany":                {"la_liga": "DAZN",                        "bundesliga": "Sky Deutschland; DAZN",  "serie_a": "DAZN",                    "ligue_1": "DAZN"},
    "France":                 {"la_liga": "beIN Sports FR",              "bundesliga": "beIN Sports FR",         "serie_a": "Canal+ Sport FR",         "ligue_1": "Canal+; Amazon Prime"},
    "Spain":                  {"la_liga": "DAZN; Movistar LaLiga",       "bundesliga": "DAZN",                   "serie_a": "DAZN",                    "ligue_1": "DAZN"},
    "Italy":                  {"la_liga": "DAZN",                        "bundesliga": "DAZN",                   "serie_a": "DAZN IT; Sky Sport",      "ligue_1": "DAZN"},
    "Netherlands":            {"la_liga": "Viaplay NL",                  "bundesliga": "Viaplay NL",             "serie_a": "Viaplay NL",              "ligue_1": "Viaplay NL"},
    "Portugal":               {"la_liga": "Eleven Sports PT",            "bundesliga": "Eleven Sports PT",       "serie_a": "Eleven Sports PT",        "ligue_1": "Eleven Sports PT"},
    "Nordics":                {"la_liga": "Viaplay",                     "bundesliga": "Viaplay",                "serie_a": "Viaplay",                 "ligue_1": "Viaplay"},
    "Poland":                 {"la_liga": "Eleven Sports PL",            "bundesliga": "Eleven Sports PL",       "serie_a": "Eleven Sports PL",        "ligue_1": "Eleven Sports PL"},
    "Middle East & N. Africa":{"la_liga": "beIN Sports",                 "bundesliga": "beIN Sports",            "serie_a": "beIN Sports",             "ligue_1": "beIN Sports"},
    "Sub-Saharan Africa":     {"la_liga": "SuperSport",                  "bundesliga": "SuperSport",             "serie_a": "SuperSport",              "ligue_1": "Canal+ Afrique"},
    "India / South Asia":     {"la_liga": "JioStar / Sony",              "bundesliga": "JioStar / Sony",         "serie_a": "JioStar / Sony",          "ligue_1": "JioStar / Sony"},
    "Australia":              {"la_liga": "Optus Sport",                 "bundesliga": "Optus Sport",            "serie_a": "Paramount+",             "ligue_1": "Optus Sport"},
    "Japan":                  {"la_liga": "DAZN JP",                     "bundesliga": "DAZN JP",                "serie_a": "DAZN JP",                 "ligue_1": "DAZN JP"},
    "South Korea":            {"la_liga": "Coupang Play",                "bundesliga": "Coupang Play",           "serie_a": "Coupang Play",            "ligue_1": "Coupang Play"},
    "Malaysia":               {"la_liga": "Astro",                       "bundesliga": "Astro",                  "serie_a": "Astro",                   "ligue_1": "Astro"},
    "Brazil / S. America":    {"la_liga": "ESPN BR; Star+",              "bundesliga": "ESPN BR",                "serie_a": "ESPN BR; Star+",          "ligue_1": "ESPN BR"},
}

# Map football-data.org competition codes to rights lookup key
COMP_CODE_TO_RIGHTS_KEY = {
    "PL":  "epl",        # Premier League
    "CL":  "ucl",        # UEFA Champions League
    "EL":  "ucl",        # UEFA Europa League — use UCL rights as proxy
    "EC":  "ucl",        # UEFA Conference League
    "ELC": "efl",        # EFL Championship
    "EL1": "efl",        # EFL League One
    "EL2": "efl",        # EFL League Two
    "FAC": "efl",        # FA Cup — use EFL rights
    "FL1": "ligue_1",    # Ligue 1
    "BL1": "bundesliga", # Bundesliga
    "SA":  "serie_a",    # Serie A
    "PD":  "la_liga",    # La Liga
}


def get_rights(competition_code: str, territory: str) -> dict | None:
    """
    Return broadcast rights info for a competition + territory.
    Returns dict with 'broadcaster', 'region' or None if no rights found.
    """
    key = COMP_CODE_TO_RIGHTS_KEY.get(competition_code)
    if not key:
        return None

    if key == "epl":
        if territory == "United Kingdom":
            return {"broadcaster": "Sky Sports; TNT Sports", "region": "UK"}
        return EPL_RIGHTS.get(territory)
    if key == "ucl":
        return UCL_RIGHTS.get(territory)
    if key == "efl":
        return EFL_RIGHTS.get(territory)
    if key in ("la_liga", "bundesliga", "serie_a", "ligue_1"):
        row = EUROPEAN_LEAGUES_RIGHTS.get(territory)
        if row:
            return {"broadcaster": row.get(key, ""), "region": "various"}
    return None


def get_all_rights_for_competition(competition_code: str) -> dict:
    """Return the full territory → rights dict for a competition."""
    key = COMP_CODE_TO_RIGHTS_KEY.get(competition_code)
    if key == "epl":
        result = dict(EPL_RIGHTS)
        result["United Kingdom"] = {"broadcaster": "Sky Sports; TNT Sports", "region": "UK"}
        return result
    if key == "ucl":
        return dict(UCL_RIGHTS)
    if key == "efl":
        return dict(EFL_RIGHTS)
    if key in ("la_liga", "bundesliga", "serie_a", "ligue_1"):
        result = {}
        for territory, row in EUROPEAN_LEAGUES_RIGHTS.items():
            broadcaster = row.get(key, "")
            if broadcaster:
                result[territory] = {"broadcaster": broadcaster, "region": territory}
        return result
    return {}


def is_epl_blackout(kickoff_iso: str) -> bool:
    """
    Return True if this EPL kickoff falls in the UK 3pm Saturday blackout window.
    kickoff_iso: ISO datetime string e.g. '2026-04-19T15:00:00Z'
    """
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
        # Saturday = 5 in Python's weekday()
        if dt.weekday() == 5 and dt.hour == 15 and dt.minute == 0:
            return True
    except Exception:
        pass
    return False
