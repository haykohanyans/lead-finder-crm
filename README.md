# Lead Finder Mini CRM

A web application for finding business leads by scraping public sources.

## Features

- **Streaming results** — leads appear in real-time as they're found
- **Stop search** — cancel anytime
- **Quality filtering** — removes junk leads automatically
- **Phone formatting** — clean +374-XX-XXX-XXX format
- **CSV export** — download results

## Sources

- **spyur.am** — Armenian Yellow Pages (priority for Armenia/Yerevan)
- **OpenStreetMap Overpass API** — global business data
- **DuckDuckGo** — web search fallback
- **Website enrichment** — contact page scraping

## Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "GitHub Repository"
3. Select `haykohanyans/lead-finder-crm`
4. Deploy!

## Local Development

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in browser.

## Usage

1. Enter business niche (e.g. "dentist", "bakery")
2. Enter city (e.g. "Yerevan", "Boston")
3. Click "Find Leads"
4. Results stream in real-time
5. Download as CSV
