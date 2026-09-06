"""
rugby_rights_db.py
------------------
Rugby Union broadcast rights by territory — the "rights layer" for the
rugby side of TVsport.live. Mirrors the shape used by rights_db.py for
football so rugby_merger.py can emit the same broadcasters[] structure the
front-end already renders.

Sources (David, Sept 2026):
  * Broadcast_rights_updated_130426.xlsx — sheets "Six Nations Rights",
    "Premiership Rights", "Champions Cup Rights", "URC Rights",
    "Top 14 Rights", "Rugby Union Sources"
  * "Rugby TV rights by country.docx" — Nations Championship (ITV UK),
    Super Rugby (Sky Sports UK), TOP 14 Rugby TV + TV5MONDE alternatives
  * rugbyworld.com Nations Championship & Super Rugby how-to-watch guides
  * talkingrugbyunion.co.uk — ITV/TNT Gallagher PREM extension 2026/27–27/28

Comp codes (used in fixture["comp_code"] and the front-end filter):
  SIXN   Six Nations                      PREM   Gallagher PREM (Premiership)
  URC    United Rugby Championship         TOP14  French Top 14
  ECC    Investec Champions Cup            ECHC   EPCR Challenge Cup
  NATC   Nations Championship              INTL   Other internationals
  SUPER  Super Rugby Pacific
"""

# ─────────────────────────────────────────────────────────────────────────────
# Broadcaster metadata — channels shown when we only have rights-level data.
# Keys must match the broadcaster names used in the *_RIGHTS tables below
# (split on ";"). Anything not listed falls back to {channels:[name], pay_tv}.
# ─────────────────────────────────────────────────────────────────────────────
RUGBY_BROADCASTER_META = {
    # UK & Ireland
    "ITV":                 {"channels": ["ITV1", "ITVX"], "type": "free_tv"},
    "BBC":                 {"channels": ["BBC One", "BBC Two", "BBC iPlayer"], "type": "free_tv"},
    "BBC Wales":           {"channels": ["BBC One Wales", "BBC Two Wales", "BBC iPlayer"], "type": "free_tv"},
    "S4C":                 {"channels": ["S4C", "S4C Clic"], "type": "free_tv"},
    "STV":                 {"channels": ["STV", "STV Player"], "type": "free_tv"},
    "TNT Sports":          {"channels": ["TNT Sports 1", "TNT Sports 2", "TNT Sports 3", "TNT Sports 4"], "type": "pay_tv"},
    "Discovery+":          {"channels": ["discovery+ (TNT Sports pass)"], "type": "streaming"},
    "Sky Sports":          {"channels": ["Sky Sports Main Event", "Sky Sports Action", "Sky Sports Arena", "Sky Sports+"], "type": "pay_tv"},
    "Premier Sports":      {"channels": ["Premier Sports 1", "Premier Sports 2", "Premier Sports Rugby", "Premier Sports Player"], "type": "pay_tv"},
    "Premier Sports Ireland": {"channels": ["Premier Sports 1 Ireland", "Premier Sports 2 Ireland", "Premier Sports Player"], "type": "pay_tv"},
    "RTÉ":                 {"channels": ["RTÉ 2", "RTÉ Player"], "type": "free_tv"},
    "Virgin Media":        {"channels": ["Virgin Media One", "Virgin Media Two", "Virgin Media Play"], "type": "free_tv"},
    "TG4":                 {"channels": ["TG4", "TG4 Player"], "type": "free_tv"},
    # France / Italy / Spain / Germany
    "Canal+":              {"channels": ["Canal+", "Canal+ Sport", "myCANAL"], "type": "pay_tv"},
    "France Télévisions":  {"channels": ["France 2", "France 3", "france.tv"], "type": "free_tv"},
    "TF1":                 {"channels": ["TF1", "TF1+"], "type": "free_tv"},
    "beIN Sports":         {"channels": ["beIN Sports 1", "beIN Sports 2", "beIN Connect"], "type": "pay_tv"},
    "Sky Italia":          {"channels": ["Sky Sport Arena", "Sky Sport Uno", "NOW"], "type": "pay_tv"},
    "Sky Sport Italia":    {"channels": ["Sky Sport Arena", "Sky Sport Uno", "NOW"], "type": "pay_tv"},
    "RAI/TV8":             {"channels": ["TV8", "RaiPlay"], "type": "free_tv"},
    "DAZN Italy":          {"channels": ["DAZN"], "type": "streaming"},
    "Movistar":            {"channels": ["Movistar Plus+", "M+ Deportes"], "type": "pay_tv"},
    "DAZN":                {"channels": ["DAZN"], "type": "streaming"},
    "MoreThanSportsTV":    {"channels": ["MoreThanSports TV"], "type": "streaming"},
    "Viaplay":             {"channels": ["Viaplay"], "type": "streaming"},
    # Americas
    "NBC Sports / Peacock":{"channels": ["Peacock", "NBC", "CNBC"], "type": "streaming"},
    "Peacock":             {"channels": ["Peacock"], "type": "streaming"},
    "FloRugby (FloSports)":{"channels": ["FloRugby"], "type": "streaming"},
    "FloRugby":            {"channels": ["FloRugby"], "type": "streaming"},
    "RugbyPass":           {"channels": ["RugbyPass TV"], "type": "streaming"},
    "RugbyPass TV":        {"channels": ["RugbyPass TV (free, registration)"], "type": "streaming"},
    "Sportsnet World":     {"channels": ["Sportsnet World"], "type": "pay_tv"},
    "TSN":                 {"channels": ["TSN", "TSN+"], "type": "pay_tv"},
    "ESPN Sur":            {"channels": ["ESPN", "ESPN 2", "Disney+"], "type": "pay_tv"},
    "ESPN":                {"channels": ["ESPN", "ESPN 2", "Disney+"], "type": "pay_tv"},
    # Oceania / Asia / Africa / MENA
    "Stan Sport":          {"channels": ["Stan Sport"], "type": "streaming"},
    "Channel 9":           {"channels": ["Channel 9", "9Now"], "type": "free_tv"},
    "Nine Network":        {"channels": ["Channel 9", "9Now"], "type": "free_tv"},
    "Sky Sport NZ":        {"channels": ["Sky Sport 1 NZ", "Sky Sport Now"], "type": "pay_tv"},
    "NZR+":                {"channels": ["NZR+ (free, geo-restricted)"], "type": "streaming"},
    "FBC":                 {"channels": ["FBC TV"], "type": "free_tv"},
    "Sky Pacific":         {"channels": ["Sky Pacific"], "type": "pay_tv"},
    "Digicel":             {"channels": ["Digicel Sports"], "type": "pay_tv"},
    "SuperSport":          {"channels": ["SuperSport Rugby", "SuperSport Grandstand", "DStv Stream"], "type": "pay_tv"},
    "WOWOW":               {"channels": ["WOWOW"], "type": "pay_tv"},
    "Wowow":               {"channels": ["WOWOW"], "type": "pay_tv"},
    "DAZN Japan":          {"channels": ["DAZN"], "type": "streaming"},
    "Setanta Sports":      {"channels": ["Setanta Sports"], "type": "pay_tv"},
    "TOD TV (Starzplay)":  {"channels": ["TOD", "Starzplay"], "type": "streaming"},
    "Sport 5":             {"channels": ["Sport 5"], "type": "pay_tv"},
    "Imedi TV":            {"channels": ["Imedi TV"], "type": "free_tv"},
    # League OTT platforms (worldwide fall-backs)
    "TOP 14 Rugby TV":     {"channels": ["top14rugbytv.com (subscription / pay-per-view)"], "type": "streaming"},
    "TV5MONDE":            {"channels": ["TV5MONDE (free-to-air, select matches)", "TV5MONDEplus"], "type": "free_tv"},
    "EPCR TV":             {"channels": ["epcrugby.tv"], "type": "streaming"},
    "URC TV":              {"channels": ["urc.tv"], "type": "streaming"},
    "PRTV Live":           {"channels": ["PRTV Live"], "type": "streaming"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Territory → rights holders per competition.  broadcaster: "A; B; C"
# Region labels match the football tables so the front-end groups them.
# ─────────────────────────────────────────────────────────────────────────────

SIX_NATIONS_RIGHTS = {
    # 2026–2029 cycle. FTA in UK: ITV 10 matches (all England home games),
    # BBC 5 (Scotland & Wales home games). S4C Welsh-language, STV simulcasts ITV.
    "United Kingdom":       {"broadcaster": "ITV; BBC; S4C; STV", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "RTÉ; Virgin Media", "region": "Europe"},
    "France":               {"broadcaster": "France Télévisions; TF1", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Italia; RAI/TV8", "region": "Europe"},
    "Belgium":              {"broadcaster": "Telenet", "region": "Europe"},
    "Bulgaria":             {"broadcaster": "A1", "region": "Europe"},
    "Croatia":              {"broadcaster": "Zonasports", "region": "Europe"},
    "Czechia":              {"broadcaster": "Nova", "region": "Europe"},
    "Estonia":              {"broadcaster": "TV3", "region": "Europe"},
    "Georgia":              {"broadcaster": "Georgian Rugby Union (GRU)", "region": "Europe"},
    "Germany":              {"broadcaster": "MoreThanSportsTV", "region": "Europe"},
    "Austria":              {"broadcaster": "MoreThanSportsTV", "region": "Europe"},
    "Switzerland":          {"broadcaster": "MoreThanSportsTV", "region": "Europe"},
    "Liechtenstein":        {"broadcaster": "MoreThanSportsTV", "region": "Europe"},
    "Luxembourg":           {"broadcaster": "MoreThanSportsTV", "region": "Europe"},
    "Latvia":               {"broadcaster": "TV3", "region": "Europe"},
    "Lithuania":            {"broadcaster": "TV3", "region": "Europe"},
    "Malta":                {"broadcaster": "GO", "region": "Europe"},
    "Portugal":             {"broadcaster": "Sport TV", "region": "Europe"},
    "Romania":              {"broadcaster": "Digi", "region": "Europe"},
    "Slovakia":             {"broadcaster": "Nova", "region": "Europe"},
    "Spain":                {"broadcaster": "Movistar", "region": "Europe"},
    "United States":        {"broadcaster": "NBC Sports / Peacock", "region": "Americas"},
    "Canada":               {"broadcaster": "Premier Sports Canada (OTT); DAZN", "region": "Americas"},
    "Argentina":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Brazil":               {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Chile":                {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Colombia":             {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Mexico":               {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Peru":                 {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Uruguay":              {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Caribbean":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Japan":                {"broadcaster": "WOWOW", "region": "Asia"},
    "India":                {"broadcaster": "Premier Sports", "region": "Asia"},
    "Hong Kong":            {"broadcaster": "Premier Sports", "region": "Asia"},
    "Singapore":            {"broadcaster": "Premier Sports", "region": "Asia"},
    "Malaysia":             {"broadcaster": "Premier Sports", "region": "Asia"},
    "Philippines":          {"broadcaster": "Premier Sports", "region": "Asia"},
    "Thailand":             {"broadcaster": "Premier Sports", "region": "Asia"},
    "Indonesia":            {"broadcaster": "Premier Sports", "region": "Asia"},
    "South Korea":          {"broadcaster": "Premier Sports", "region": "Asia"},
    "Taiwan":               {"broadcaster": "Premier Sports", "region": "Asia"},
    "Australia":            {"broadcaster": "Stan Sport", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Sky Sport NZ", "region": "Asia-Pacific"},
    "Fiji":                 {"broadcaster": "FBC; Digicel", "region": "Asia-Pacific"},
    "Pacific Islands":      {"broadcaster": "Digicel; TV5MONDE", "region": "Asia-Pacific"},
    "UAE":                  {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Saudi Arabia":         {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Qatar":                {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Egypt":                {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Bahrain":              {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Kuwait":               {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Oman":                 {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Jordan":               {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Lebanon":              {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Iraq":                 {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Morocco":              {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Tunisia":              {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Algeria":              {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Libya":                {"broadcaster": "TOD TV (Starzplay)", "region": "Middle East & N. Africa"},
    "Israel":               {"broadcaster": "Sport 5", "region": "Middle East & N. Africa"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Sub-Saharan Africa":   {"broadcaster": "SuperSport; TV5MONDE", "region": "Sub-Saharan Africa"},
}

PREMIERSHIP_RIGHTS = {
    # 2025/26–2030/31: TNT Sports every match (also on discovery+ / HBO Max
    # TNT Sports pass). ITV: 7 live matches a season incl. the Final,
    # simulcast on TNT — extended through 2027/28.
    "United Kingdom":       {"broadcaster": "TNT Sports; Discovery+; ITV", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "TNT Sports; Discovery+; Premier Sports Ireland", "region": "Europe"},
    "France":               {"broadcaster": "beIN Sports", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Italia", "region": "Europe"},
    "Germany":              {"broadcaster": "DAZN", "region": "Europe"},
    "Spain":                {"broadcaster": "Movistar", "region": "Europe"},
    "Netherlands":          {"broadcaster": "Viaplay", "region": "Europe"},
    "Nordics":              {"broadcaster": "Viaplay", "region": "Europe"},
    "United States":        {"broadcaster": "FloRugby (FloSports)", "region": "Americas"},
    "Canada":               {"broadcaster": "Sportsnet World", "region": "Americas"},
    "Argentina":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Brazil":               {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Latin America":        {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Australia":            {"broadcaster": "Stan Sport", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Sky Sport NZ", "region": "Asia-Pacific"},
    "Japan":                {"broadcaster": "DAZN Japan", "region": "Asia"},
    "India":                {"broadcaster": "RugbyPass TV", "region": "Asia"},
    "South-East Asia":      {"broadcaster": "RugbyPass TV; Setanta Sports", "region": "Asia"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Sub-Saharan Africa":   {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Middle East & N. Africa": {"broadcaster": "beIN Sports", "region": "Middle East & N. Africa"},
    "Pacific Islands":      {"broadcaster": "Digicel", "region": "Asia-Pacific"},
    "Rest of World":        {"broadcaster": "PRTV Live", "region": "International"},
}

# Investec Champions Cup and EPCR Challenge Cup share one deal (2025/26–2026/27)
EPCR_RIGHTS = {
    "United Kingdom":       {"broadcaster": "Premier Sports; S4C", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Premier Sports Ireland", "region": "Europe"},
    "France":               {"broadcaster": "beIN Sports; France Télévisions", "region": "Europe"},
    "Italy":                {"broadcaster": "EPCR TV", "region": "Europe"},
    "Europe (other)":       {"broadcaster": "EPCR TV", "region": "Europe"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "United States":        {"broadcaster": "FloRugby (FloSports)", "region": "Americas"},
    "Canada":               {"broadcaster": "EPCR TV", "region": "Americas"},
    "Australia":            {"broadcaster": "EPCR TV; Stan Sport", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "EPCR TV; Sky Sport NZ", "region": "Asia-Pacific"},
    "Japan":                {"broadcaster": "EPCR TV", "region": "Asia"},
    "Rest of World":        {"broadcaster": "EPCR TV", "region": "International"},
}

URC_RIGHTS = {
    # 2025/26–2028/29
    "United Kingdom":       {"broadcaster": "Premier Sports; S4C; BBC Wales", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Premier Sports Ireland; TG4", "region": "Europe"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Italy":                {"broadcaster": "DAZN Italy", "region": "Europe"},
    "France":               {"broadcaster": "beIN Sports", "region": "Europe"},
    "Nordics":              {"broadcaster": "Viaplay", "region": "Europe"},
    "United States":        {"broadcaster": "FloRugby (FloSports)", "region": "Americas"},
    "Canada":               {"broadcaster": "URC TV", "region": "Americas"},
    "Australia":            {"broadcaster": "Setanta Sports", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Setanta Sports", "region": "Asia-Pacific"},
    "Japan":                {"broadcaster": "DAZN Japan", "region": "Asia"},
    "South-East Asia":      {"broadcaster": "Setanta Sports", "region": "Asia"},
    "Middle East & N. Africa": {"broadcaster": "Setanta Sports", "region": "Middle East & N. Africa"},
    "Rest of World":        {"broadcaster": "URC TV", "region": "International"},
}

TOP14_RIGHTS = {
    # 2025/26–2026/27. Canal+ exclusive in France. Premier Sports UK shows
    # 4 matches per round + finals. TOP 14 Rugby TV (LNR's own OTT) is in
    # 170+ territories but geo-blocked in the UK/Ireland by the Premier
    # Sports exclusivity; TV5MONDE carries select matches FTA — David wants
    # both always listed (see TOP14_ALWAYS_INCLUDE below).
    "France":               {"broadcaster": "Canal+", "region": "Europe"},
    "United Kingdom":       {"broadcaster": "Premier Sports", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Premier Sports Ireland", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Italia", "region": "Europe"},
    "Spain":                {"broadcaster": "Movistar", "region": "Europe"},
    "Georgia":              {"broadcaster": "Imedi TV", "region": "Europe"},
    "Andorra":              {"broadcaster": "Canal+; Movistar", "region": "Europe"},
    "Austria":              {"broadcaster": "Canal+", "region": "Europe"},
    "Czechia":              {"broadcaster": "Canal+", "region": "Europe"},
    "Hungary":              {"broadcaster": "Canal+", "region": "Europe"},
    "Monaco":               {"broadcaster": "Canal+", "region": "Europe"},
    "Netherlands":          {"broadcaster": "Canal+", "region": "Europe"},
    "Poland":               {"broadcaster": "Canal+", "region": "Europe"},
    "Romania":              {"broadcaster": "Canal+", "region": "Europe"},
    "Slovakia":             {"broadcaster": "Canal+", "region": "Europe"},
    "Switzerland":          {"broadcaster": "Canal+", "region": "Europe"},
    "United States":        {"broadcaster": "FloRugby (FloSports); RugbyPass", "region": "Americas"},
    "Argentina":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Chile":                {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Bolivia":              {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Paraguay":             {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Peru":                 {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Colombia":             {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Ecuador":              {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Uruguay":              {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Venezuela":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "Haiti":                {"broadcaster": "Canal+", "region": "Americas"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Sub-Saharan Africa":   {"broadcaster": "Canal+", "region": "Sub-Saharan Africa"},
    "Japan":                {"broadcaster": "DAZN Japan", "region": "Asia"},
    "Myanmar":              {"broadcaster": "Canal+", "region": "Asia"},
    "Vietnam":              {"broadcaster": "Canal+", "region": "Asia"},
    "Australia":            {"broadcaster": "beIN Sports; TOP 14 Rugby TV", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "TOP 14 Rugby TV", "region": "Asia-Pacific"},
    "Pacific Islands":      {"broadcaster": "Digicel", "region": "Asia-Pacific"},
    # Rest of World handled by ALWAYS_INCLUDE (TOP 14 Rugby TV + TV5MONDE)
}

NATIONS_CHAMPIONSHIP_RIGHTS = {
    # New 12-team competition, 2026 and 2028 (July + November windows).
    # ITV exclusive in UK incl. summer & autumn Nations Series in those years.
    "United Kingdom":       {"broadcaster": "ITV", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Virgin Media", "region": "Europe"},
    "France":               {"broadcaster": "TF1", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Sport Italia", "region": "Europe"},
    "Australia":            {"broadcaster": "Stan Sport; Channel 9", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Sky Sport NZ", "region": "Asia-Pacific"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Japan":                {"broadcaster": "WOWOW", "region": "Asia"},
    "United States":        {"broadcaster": "RugbyPass TV", "region": "Americas"},
    "Rest of World":        {"broadcaster": "RugbyPass TV", "region": "International"},
}

# Other internationals (Rugby Championship, non-NC autumn Tests, Lions etc.)
# Rights vary by host union; UK: Sky Sports (Rugby Championship, SA/NZ/AUS/ARG
# home Tests), TNT Sports (some England/Wales/Scotland/Ireland autumn Tests
# in non-NC years), ITV (Nations Series in 2026/2028). Kept conservative.
INTERNATIONAL_RIGHTS = {
    "United Kingdom":       {"broadcaster": "Sky Sports; TNT Sports; ITV", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Sky Sports; Virgin Media", "region": "Europe"},
    "France":               {"broadcaster": "Canal+; France Télévisions", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Sport Italia", "region": "Europe"},
    "Australia":            {"broadcaster": "Stan Sport; Channel 9", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Sky Sport NZ", "region": "Asia-Pacific"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "Argentina":            {"broadcaster": "ESPN Sur", "region": "Americas"},
    "United States":        {"broadcaster": "FloRugby (FloSports); RugbyPass TV", "region": "Americas"},
    "Japan":                {"broadcaster": "WOWOW", "region": "Asia"},
}

SUPER_RUGBY_RIGHTS = {
    # Super Rugby Pacific — Feb to June. UK/Ireland: Sky Sports (NOW).
    "United Kingdom":       {"broadcaster": "Sky Sports", "region": "UK"},
    "Republic of Ireland":  {"broadcaster": "Sky Sports", "region": "Europe"},
    "Australia":            {"broadcaster": "Stan Sport; Nine Network", "region": "Asia-Pacific"},
    "New Zealand":          {"broadcaster": "Sky Sport NZ", "region": "Asia-Pacific"},
    "Fiji":                 {"broadcaster": "FBC; Sky Pacific", "region": "Asia-Pacific"},
    "Pacific Islands":      {"broadcaster": "Digicel", "region": "Asia-Pacific"},
    "South Africa":         {"broadcaster": "SuperSport", "region": "Sub-Saharan Africa"},
    "United States":        {"broadcaster": "FloRugby (FloSports)", "region": "Americas"},
    "Canada":               {"broadcaster": "TSN", "region": "Americas"},
    "France":               {"broadcaster": "Canal+", "region": "Europe"},
    "Italy":                {"broadcaster": "Sky Italia", "region": "Europe"},
    "Spain":                {"broadcaster": "Movistar", "region": "Europe"},
    "Japan":                {"broadcaster": "WOWOW", "region": "Asia"},
    "Latin America":        {"broadcaster": "ESPN Sur", "region": "Americas"},
    "South-East Asia":      {"broadcaster": "Premier Sports", "region": "Asia"},
    "Rest of World":        {"broadcaster": "NZR+", "region": "International"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Competition registry
# ─────────────────────────────────────────────────────────────────────────────
RUGBY_COMPETITIONS = {
    "SIXN":  {"display": "Six Nations",                 "rights": SIX_NATIONS_RIGHTS,          "tz": "Europe/London"},
    "PREM":  {"display": "Gallagher PREM",              "rights": PREMIERSHIP_RIGHTS,          "tz": "Europe/London"},
    "URC":   {"display": "United Rugby Championship",   "rights": URC_RIGHTS,                  "tz": "Europe/London"},
    "TOP14": {"display": "Top 14",                      "rights": TOP14_RIGHTS,                "tz": "Europe/Paris"},
    "ECC":   {"display": "Investec Champions Cup",      "rights": EPCR_RIGHTS,                 "tz": "Europe/London"},
    "ECHC":  {"display": "EPCR Challenge Cup",          "rights": EPCR_RIGHTS,                 "tz": "Europe/London"},
    "NATC":  {"display": "Nations Championship",        "rights": NATIONS_CHAMPIONSHIP_RIGHTS, "tz": "Europe/London"},
    "INTL":  {"display": "International",               "rights": INTERNATIONAL_RIGHTS,        "tz": "Europe/London"},
    "SUPER": {"display": "Super Rugby Pacific",         "rights": SUPER_RUGBY_RIGHTS,          "tz": "Pacific/Auckland"},
}

# Entries appended to EVERY fixture of a competition regardless of territory
# match — the league's own worldwide OTT platform / FTA alternative.
# David (Sept 2026): "TOP 14 Rugby TV ... should always be included."
ALWAYS_INCLUDE = {
    "TOP14": [
        {"territory": "Worldwide (170+ territories)", "region": "International",
         "broadcaster": "TOP 14 Rugby TV", "type": "streaming",
         "note": "Official LNR streaming service — geo-blocked in UK & Ireland (Premier Sports exclusivity)"},
        {"territory": "Worldwide", "region": "International",
         "broadcaster": "TV5MONDE", "type": "free_tv",
         "note": "Free-to-air coverage of select Top 14 matches via TV5MONDE website/app"},
    ],
    "ECC":  [{"territory": "Worldwide (outside rights-holder territories)", "region": "International",
              "broadcaster": "EPCR TV", "type": "streaming", "note": "epcrugby.tv"}],
    "ECHC": [{"territory": "Worldwide (outside rights-holder territories)", "region": "International",
              "broadcaster": "EPCR TV", "type": "streaming", "note": "epcrugby.tv"}],
    "URC":  [{"territory": "Worldwide (outside rights-holder territories)", "region": "International",
              "broadcaster": "URC TV", "type": "streaming", "note": "urc.tv"}],
    "NATC": [{"territory": "Worldwide (outside rights-holder territories)", "region": "International",
              "broadcaster": "RugbyPass TV", "type": "streaming", "note": "Free with registration"}],
}

# UK broadcasters that are free-to-air — used to flag FTA in the output
UK_FTA = {"ITV", "BBC", "BBC Wales", "S4C", "STV"}


def get_rights_map(comp_code: str) -> dict:
    comp = RUGBY_COMPETITIONS.get(comp_code)
    return dict(comp["rights"]) if comp else {}


def broadcaster_meta(name: str) -> dict:
    return RUGBY_BROADCASTER_META.get(name, {"channels": [name], "type": "pay_tv"})
