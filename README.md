# TVsport — tvsport.live

Find every TV channel and streaming service showing live football worldwide.
Covers EPL and UCL with a 30-day rolling fixture window.

## What's in this folder

```
tvsport/
│
├── tvsport.html                        ← THE APP — open this in a browser
│
├── scraper/                            ← Nightly data pipeline
│   ├── merger.py                       ← Main entry point — run this
│   ├── rights_db.py                    ← Broadcast rights database
│   ├── requirements.txt                ← Python dependencies
│   └── sources/
│       ├── fixtures_premierleague.py   ← EPL fixture list + 3pm blackouts
│       ├── fixtures_uefa.py            ← UCL fixture list
│       ├── uk_live_footballontv.py     ← UK channels
│       ├── uk_tvguide.py              ← UK coverage times
│       ├── us_nbcsports.py            ← US channels (NBC/Peacock)
│       ├── africa_supersport.py       ← Africa (SuperSport/DStv)
│       ├── asia_scrapers.py           ← Asia (Astro, Star Sports)
│       └── epg/
│           ├── epg_channels.xml       ← Channel list for EPG tool
│           ├── epg_runner.py          ← Drives iptv-org/epg Node.js tool
│           └── epg_xmltv_parser.py    ← Parses XMLTV guide.xml output
│
├── output/
│   └── fixtures.json                  ← Generated data (served to app)
│
├── .github/workflows/
│   └── nightly_scrape.yml             ← GitHub Actions automation
│
└── .gitignore
```

## Quick setup

1. Push this entire folder to a **public** GitHub repo called `tvsport-data`
2. Add `Broadcast_rights_updated_08-04-26.xlsx` to the repo root
3. Install dependencies: `pip install -r scraper/requirements.txt`
4. Run: `cd scraper && python merger.py`
5. Push `output/fixtures.json` to GitHub
6. Enable GitHub Actions — it runs automatically at 2am UTC every night
7. Update the CDN URL in `tvsport.html` with your GitHub username
8. Deploy `tvsport.html` to Cloudflare Pages → tvsport.live

Full step-by-step instructions: see `KickOff_Setup_Instructions.md`
or the TVsport setup chat.

## Data sources

| Source | What it provides | Method |
|--------|-----------------|--------|
| iptv-org/epg | UK, MENA, Africa, Europe channels | XMLTV/EPG |
| live-footballontv.com | UK EPL + UCL channels | HTML scraper |
| tvguide.co.uk | UK coverage start times | HTML scraper |
| nbcsports.com | US NBC/USA/Peacock per fixture | HTML scraper |
| cbssports.com | US Paramount+ per UCL fixture | HTML scraper |
| premierleague.com | EPL fixtures + 3pm blackout flags | HTML scraper |
| Broadcast_rights_*.xlsx | All territory rights (annual) | Local file |

## Cost

£0/month — GitHub Actions (free), jsDelivr CDN (free), Cloudflare Pages (free).
