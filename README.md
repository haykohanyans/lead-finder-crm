# Lead Finder Mini CRM

A local web application for finding business leads by scraping public sources.

## Sources

- **spyur.am** — Armenian Yellow Pages (Armenia/Yerevan priority)
- **OpenStreetMap Overpass API** — global business data via bounding boxes
- **DuckDuckGo** — web search fallback
- **Website enrichment** — contact page scraping for email/phone

## Features

- Real-time streaming results
- Quality filtering (removes junk leads)
- Phone number formatting
- Export to CSV

## Tech Stack

- Python + Flask backend
- HTML/CSS/JS frontend
- BeautifulSoup + requests for scraping

## Installation

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 in browser.

## Usage

1. Enter business niche (e.g. "dentist", "bakery")
2. Enter city (e.g. "Yerevan", "Boston")
3. Click "Find Leads"
4. Results appear in real-time
5. Download as CSV
