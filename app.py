"""
Lead Finder Mini CRM - Backend v5
Priority: Armenia / Yerevan
"""
import re, csv, json, logging, time, random, concurrent.futures
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, quote_plus
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from bs4 import BeautifulSoup
import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8")])
log = logging.getLogger(__name__)
app = Flask(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# City bounding boxes
CITY_BBOXES = {
    "new york": (40.47, -74.26, 40.92, -73.70), "los angeles": (33.70, -118.67, 34.33, -118.16),
    "chicago": (41.64, -87.94, 42.02, -87.52), "houston": (29.52, -95.77, 30.11, -95.01),
    "phoenix": (33.29, -112.33, 33.72, -111.65), "philadelphia": (39.87, -75.28, 40.13, -74.96),
    "san antonio": (29.25, -98.75, 29.65, -98.35), "san diego": (32.53, -117.30, 33.11, -116.92),
    "dallas": (32.61, -97.00, 33.01, -96.47), "san jose": (37.20, -122.05, 37.47, -121.75),
    "austin": (30.10, -97.94, 30.52, -97.56), "jacksonville": (30.17, -81.88, 30.55, -81.38),
    "fort worth": (32.60, -97.53, 32.93, -97.09), "columbus": (39.80, -83.21, 40.15, -82.77),
    "charlotte": (34.92, -81.05, 35.41, -80.62), "san francisco": (37.64, -122.63, 37.93, -122.29),
    "seattle": (47.48, -122.46, 47.74, -122.23), "denver": (39.56, -105.19, 39.92, -104.69),
    "boston": (42.23, -71.19, 42.43, -70.99), "miami": (25.71, -80.36, 25.88, -80.13),
    "las vegas": (35.98, -115.33, 36.38, -114.98), "portland": (45.42, -122.84, 45.65, -122.47),
    "atlanta": (33.65, -84.56, 33.89, -84.29), "minneapolis": (44.89, -93.36, 45.05, -93.20),
    "detroit": (42.26, -83.30, 42.45, -82.92),
    # Armenian cities
    "yerevan": (40.04, 44.33, 40.32, 44.68), "erevan": (40.04, 44.33, 40.32, 44.68),
    "gyumri": (40.70, 43.74, 40.86, 43.94), "vanadzor": (41.00, 44.30, 41.22, 44.60),
    "vagharshapat": (40.14, 44.26, 40.20, 44.32), "abovyan": (40.26, 44.58, 40.30, 44.64),
    "kapan": (39.18, 46.38, 39.24, 46.46), "hrazdan": (40.48, 44.72, 40.54, 44.80),
    "armavir": (40.12, 44.02, 40.20, 44.12), "artashat": (39.94, 44.52, 40.02, 44.60),
    "sisian": (39.50, 46.02, 39.56, 46.10), "goris": (39.50, 46.32, 39.54, 46.38),
    "dilijan": (40.72, 44.82, 40.78, 44.90), "jermuk": (39.82, 45.66, 39.88, 45.74),
    "tsakhkadzor": (40.52, 44.68, 40.56, 44.74),
}

NICHE_OSM = {
    "bakery": ['shop="bakery"'], "dentist": ['healthcare="dentist"', 'amenity="dentist"'],
    "doctor": ['healthcare="doctor"', 'amenity="doctors"'], "clinic": ['amenity="clinic"', 'healthcare="clinic"'],
    "hospital": ['amenity="hospital"'], "pharmacy": ['amenity="pharmacy"'],
    "restaurant": ['amenity="restaurant"'], "cafe": ['amenity="cafe"'],
    "bar": ['amenity="bar"', 'amenity="pub"'], "hotel": ['tourism="hotel"', 'tourism="motel"'],
    "gym": ['leisure="fitness_centre"'], "school": ['amenity="school"'],
    "lawyer": ['office="lawyer"', 'office="attorney"'], "accountant": ['office="accountant"'],
    "plumber": ['craft="plumber"'], "electrician": ['craft="electrician"'],
    "hairdresser": ['shop="hairdresser"'], "beauty": ['shop="beauty"'],
    "car_repair": ['shop="car_repair"'], "pet": ['shop="pet"'], "florist": ['shop="florist"'],
    "pool": ['leisure="swimming_pool"'], "programmer": ['office="it"'],
    "shop": ['shop'], "store": ['shop'], "company": ['office'], "salon": ['shop="hairdresser"', 'shop="beauty"'],
    "auto": ['shop="car"', 'shop="car_repair"'], "repair": ['craft'], "construction": ['craft="construction"'],
    "cleaning": ['craft="cleaner"'], "catering": ['amenity="restaurant"'], "real estate": ['office="estate_agent"'],
    "insurance": ['office="insurance"'], "agency": ['office'], "studio": ['shop="studio"'],
    "print": ['shop="copyshop"'], "transport": ['office="transport"'], "delivery": ['craft="delivery"'],
    "wholesale": ['shop="wholesale"'], "market": ['amenity="marketplace"'],
}

NICHE_SYNONYMS = {
    "dentist": ["dentist", "dental", "stomatolog"], "bakery": ["bakery", "bakeries", "pastry"],
    "plumber": ["plumber", "plumbing"], "restaurant": ["restaurant", "cafe", "bistro"],
    "lawyer": ["lawyer", "attorney", "law firm"], "accountant": ["accountant", "accounting"],
    "hairdresser": ["hairdresser", "hair salon", "barber"], "electrician": ["electrician"],
    "programmer": ["programmer", "IT company", "software"], "pool": ["pool", "swimming pool"],
}
_SYNONYM_CANON = {s: c for c, ss in NICHE_SYNONYMS.items() for s in ss}

def get_variants(niche):
    canon = _SYNONYM_CANON.get(niche.lower().strip())
    return NICHE_SYNONYMS[canon][:3] if canon else [niche]

def get_osm_filters(niche):
    n = niche.lower().strip()
    canon = _SYNONYM_CANON.get(n, n)
    return NICHE_OSM.get(canon, NICHE_OSM.get(n, []))

def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"})
    return s

def extract_emails(text):
    bad = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|css|js|html?)(\?|$)", re.I)
    raw = list(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]{2,6}", text)))
    return [e for e in raw if not bad.search(e) and e.count("@")==1 and len(e)<=80
            and not any(x in e for x in ["bootstrap","jquery","font","example","@media","@keyframes"])][:5]

def extract_phones(text):
    pat = re.compile(r"(?:\+?\d{1,3}[-.\s?])?(?:\(?\d{2,4}\)?)?[-.\s]?\d{2,4}[-.\s]?\d{3,4}(?:[-.\s]?\d{2,4})?")
    core = re.compile(r"(?:\+?\d{1,3}[.\s-])?(?:\(?\d{2,4}\)?[.\s-])?\d{3}[.\s-]\d{4}")
    out = []
    for m in pat.findall(text):
        m = m.strip()
        d = re.sub(r"\D", "", m)
        if not (7 <= len(d) <= 15): continue
        if re.match(r"^\d+\.\d+\.\d+", m): continue
        if re.match(r"^(19|20)\d{6,}$", d): continue
        if core.search(m) or re.match(r"^\+\d", m) or re.match(r"^\(\d{3}\)\s*\d{3}[-.\s]\d{4}$", m):
            out.append(m)
    return list(dict.fromkeys(out))[:5]

SKIP_DOMAINS = {
    "wikipedia.org","youtube.com","reddit.com","pinterest.com","facebook.com","instagram.com",
    "twitter.com","linkedin.com","indeed.com","glassdoor.com","ziprecruiter.com","quora.com",
    "tiktok.com","amazon.com","ebay.com","etsy.com","nytimes.com","cnn.com","bbc.com","forbes.com",
    "healthline.com","webmd.com","mayoclinic.org","opencare.com","vitals.com","zocdoc.com",
    "healthgrades.com","duckduckgo.com","google.com","bing.com","yahoo.com","tripadvisor.com",
    "booking.com","airbnb.com","apartments.com","zillow.com","realtor.com","chamberofcommerce.com",
    "manta.com","yellowpages.com","yelp.com","bbb.org","superpages.com","dexknows.com",
    "hotfro.com","thumbtack.com","angieslist.com","houzz.com","zoominfo.com","openstreetmap.org",
    "overpass-api.de","spyur.am",
}

def should_skip(url):
    return any(d in url.lower() for d in SKIP_DOMAINS)

def is_junk(lead):
    name = lead.get("company_name","")
    if not name or len(name) < 3: return True
    if re.match(r"^(home|search|result|page|about|contact|login|sign)\b", name, re.I): return True
    if re.match(r"^\d+$", name): return True
    return False

def quality_score(lead):
    s = 0
    n = lead.get("company_name","")
    if n and len(n)>3: s+=10
    if lead.get("phone"): s+=30
    if lead.get("email"): s+=25
    w = lead.get("website","")
    if w and not should_skip(w): s+=15
    if lead.get("notes"): s+=10
    if len(n)>10: s+=10
    return s

def clean_phones(phone_str):
    if not phone_str: return ""
    parts = [p.strip() for p in phone_str.split(",")]
    seen, out = set(), []
    for p in parts:
        digits = re.sub(r"\D", "", p)
        if digits in seen or len(digits) < 7: continue
        seen.add(digits)
        if digits.startswith("374") and len(digits)==11: p = f"+{digits[:3]}-{digits[3:5]}-{digits[5:8]}-{digits[8:]}"
        elif digits.startswith("0") and len(digits)==8: p = f"+374-{digits[1:3]}-{digits[3:6]}-{digits[6:]}"
        out.append(p)
    return ", ".join(out[:3])

# ── SOURCE 1: spyur.am ─────────────────────────────────────────────────

def spyur_search_page(niche, city, page=1):
    results = []
    try:
        resp = get_session().get("https://www.spyur.am/en/home/search/",
            params={"company_name": niche, "addres": city, "only_by_name": "1", "page": str(page)}, timeout=15)
        if resp.status_code != 200: return results
        text = resp.text
        links = re.findall(r'href="(/en/companies/[^"?#]+)"', text)
        seen = set()
        for href in links:
            if href in seen: continue
            seen.add(href)
            full = f"https://www.spyur.am{href}"
            idx = text.index(href)
            chunk = text[max(0, idx-100):idx+500]
            nm = re.search(r'class="[^"]*company_name[^"]*"[^>]*>([^<]+)<', chunk)
            title = nm.group(1).strip() if nm else ""
            title = title.replace("&quot;",'"').replace("&#39;","'").replace("&amp;","&")
            if title:
                results.append({"title": title, "link": full})
    except Exception as e:
        log.debug("spyur page %d: %s", page, e)
    return results

def spyur_search(niche, city, max_r=60):
    all_r, seen = [], set()
    for var in get_variants(niche):
        if len(all_r) >= max_r: break
        for pg in range(1, 4):
            if len(all_r) >= max_r: break
            res = spyur_search_page(var, city, pg)
            if not res: break
            for r in res:
                if r["link"] not in seen:
                    seen.add(r["link"])
                    all_r.append(r)
            if len(res) < 20: break
            time.sleep(1.5)
    return all_r[:max_r]

def spyur_details(url):
    info = {"phones": [], "address": "", "website": "", "emails": []}
    try:
        text = get_session().get(url, timeout=12).text
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.select("header, footer, nav, script, style"): tag.decompose()
        plain = soup.get_text(" ", strip=True)
        # Remove repeated spyur.am boilerplate
        plain = re.sub(r'ARMENIA\s*\(YEREVAN\)\s*•\s*SPYUR[^.]*', '', plain)
        plain = re.sub(r'Products and services.*?Armenia', '', plain, flags=re.DOTALL)
        plain = re.sub(r'Search\s+Advanced\s+search.*', '', plain, flags=re.DOTALL)
        # Phones
        spyur_phones = {"07803803","0357031063","0357097971","0961107813","+37410558698","+37410559725"}
        phones = list(dict.fromkeys(p.strip() for p in
            re.findall(r"(?:\+374|0)[\s\-]?\d{2}[\s\-]?\d{2,3}[\s\-]?\d{2,4}", plain)
            if len(re.sub(r"\D","",p))>=7 and re.sub(r"\D","",p) not in spyur_phones))[:5]
        info["phones"] = phones
        sm = re.search(r'Site\s+(https?://[^\s<>"\']+)', plain, re.I)
        if sm: info["website"] = sm.group(1).strip()
        # Email from mailto links first
        mailto_emails = re.findall(r'mailto:([^"?\s]+)', text)
        if mailto_emails:
            info["emails"] = list(dict.fromkeys(mailto_emails))[:3]
        else:
            info["emails"] = extract_emails(text)[:3]
        # Address: look for Armenian address patterns
        addr_m = re.search(r'(\d{4,6}\s*,?\s*(?:Yerevan|Erevan)[^,\n]{0,50})', plain, re.I)
        if addr_m:
            info["address"] = addr_m.group(1).strip()[:120]
        else:
            addr_m2 = re.search(r'((?:Street|St|Ave|Avenue|Blvd|Qochar|Yerevan)[^,\n]{5,60})', plain, re.I)
            if addr_m2: info["address"] = addr_m2.group(1).strip()[:120]
    except Exception as e:
        log.debug("spyur detail %s: %s", url, e)
    return info

# ── SOURCE 2: OSM Overpass ──────────────────────────────────────────────

def osm_search(niche, city, limit=50):
    filters = get_osm_filters(niche)
    if not filters: return []
    city_lower = city.lower().strip()
    bbox = CITY_BBOXES.get(city_lower)
    if bbox:
        tag_str = "".join(f'  node[{f}]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});\n  way[{f}]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});\n' for f in filters)
        query = f"[out:json][timeout:30];\n{tag_str}out body {limit};\n"
    else:
        tag_str = "".join(f"  node[{f}](area.search);\n  way[{f}](area.search);\n" for f in filters)
        query = f'[out:json][timeout:30];\narea["name="{city}"]["admin_level"="8"]->.search;\n(\n{tag_str}\n);\nout body {limit};\n'
    try:
        r = requests.post("https://overpass-api.de/api/interpreter", data={"data": query},
            headers={"User-Agent": "LeadFinderCRM/2.0"}, timeout=30)
        if r.status_code != 200 or not r.text.strip(): return []
        elems = r.json().get("elements", [])
        results = []
        for el in elems:
            t = el.get("tags", {})
            name = t.get("name", "")
            if not name or len(name) < 2: continue
            results.append({"title": name, "link": t.get("website", t.get("contact:website", "")),
                "phone": t.get("phone", t.get("contact:phone", "")),
                "email": t.get("email", t.get("contact:email", "")),
                "notes": f'{t.get("addr:street","")}, {t.get("addr:city",city)}'.strip(", ") })
        return results
    except Exception as e:
        log.warning("OSM error: %s", e)
        return []

# ── SOURCE 3: DuckDuckGo ───────────────────────────────────────────────

def ddg_search(query, limit=10):
    results = []
    try:
        resp = get_session().post("https://html.duckduckgo.com/html/", data={"q": query}, timeout=15)
        if resp.status_code != 200: return results
        soup = BeautifulSoup(resp.text, "html.parser")
        for r in soup.select(".result"):
            a, sn = r.select_one(".result__a"), r.select_one(".result__snippet")
            if not a: continue
            results.append({"title": a.get_text(" ","strip"), "link": a.get("href",""),
                "snippet": sn.get_text(" ","strip") if sn else ""})
            if len(results) >= limit: break
    except Exception as e:
        log.warning("DDG error: %s", e)
    return results

# ── SOURCE 4: Website enrichment ────────────────────────────────────────

def enrich_site(url):
    info = {"emails": [], "phones": [], "notes": ""}
    if not url or not url.startswith("http"): return info
    try:
        resp = get_session().get(url, timeout=10, allow_redirects=True)
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        for a in soup.select("a[href^='mailto:']"):
            e = a["href"].replace("mailto:","").split("?")[0].strip()
            if e and "@" in e: info["emails"].append(e)
        info["emails"] = extract_emails(text)[:5]
        info["phones"] = extract_phones(text)[:3]
        meta = soup.find("meta", attrs={"name": lambda x: x and x.lower()=="description"})
        if meta: info["notes"] = (meta.get("content") or "")[:150]
        if not info["emails"] and not info["phones"]:
            for a in soup.find_all("a", href=True):
                if "contact" in a.get_text(" ","strip").lower() or "contact" in a["href"].lower():
                    cl = a["href"]
                    if cl.startswith("/"): cl = f"{urlparse(url).scheme}://{urlparse(url).netloc}{cl}"
                    try:
                        r2 = get_session().get(cl, timeout=8)
                        e2 = extract_emails(r2.text)
                        p2 = extract_phones(r2.text)
                        if e2: info["emails"] = e2[:5]
                        if p2: info["phones"] = p2[:3]
                    except: pass
                    break
    except Exception as e:
        log.debug("enrich %s: %s", url, e)
    return info

# ── CSV ────────────────────────────────────────────────────────────────

def save_csv(leads, niche, city):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sn = re.sub(r"\W+","_",niche)[:30]
    sc = re.sub(r"\W+","_",city)[:30]
    fn = f"leads_{sn}_{sc}_{ts}.csv"
    path = DATA_DIR / fn
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["company_name","website","email","phone","notes"], extrasaction="ignore")
        w.writeheader()
        w.writerows(leads)
    return path

def list_csv():
    return sorted([f.name for f in DATA_DIR.glob("*.csv") if f.name!="app.log"], reverse=True)

# ── Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", files=list_csv())

@app.route("/search", methods=["POST"])
def search():
    data = request.get_json(force=True)
    niche = (data.get("niche") or "").strip()
    city = (data.get("city") or "").strip()
    if not niche or not city:
        return jsonify({"error": "niche and city required"}), 400

    def generate():
        leads = []
        def emit(t, **kw): yield json.dumps({"type": t, **kw}) + "\n"

        try:
            # 1. spyur.am for Armenian cities
            city_lower = city.lower().strip()
            if city_lower in CITY_BBOXES and city_lower in {
                "yerevan","erevan","gyumri","vanadzor","vagharshapat","abovyan","kapan",
                "hrazdan","armavir","artashat","sisian","goris","dilijan","jermuk","tsakhkadzor"
            }:
                yield from emit("progress", text="Searching spyur.am…", pct=15)
                for r in spyur_search(niche, city):
                    d = spyur_details(r["link"])
                    web = d.get("website","")
                    ph = clean_phones(", ".join(d.get("phones",[])))
                    em = ", ".join(d.get("emails",[]))
                    ad = d.get("address","")
                    lead = {"company_name": r["title"], "website": web, "email": em, "phone": ph, "notes": ad}
                    leads.append(lead)
                    yield from emit("lead", lead=lead)

            # 2. OSM
            yield from emit("progress", text="Searching OpenStreetMap…", pct=40)
            for r in osm_search(niche, city):
                name = r["title"]
                try: name = name.encode("latin-1").decode("utf-8")
                except: pass
                lead = {"company_name": name, "website": r.get("link",""),
                    "email": r.get("email",""), "phone": clean_phones(r.get("phone","")), "notes": r.get("notes","")}
                if not is_junk(lead):
                    leads.append(lead)
                    yield from emit("lead", lead=lead)

            # 3. DDG
            if len(leads) < 10:
                yield from emit("progress", text="Web search…", pct=60)
                for q in [f'"{niche}" "{city}" contact phone email', f'{niche} {city} business']:
                    for r in ddg_search(q):
                        lead = {"company_name": r["title"], "website": r["link"], "email": "", "phone": "", "notes": r.get("snippet","")[:100]}
                        if not is_junk(lead):
                            leads.append(lead)
                            yield from emit("lead", lead=lead)
                    if len(leads) >= 15: break
                    time.sleep(1)

            # 4. Enrich
            yield from emit("progress", text="Enriching websites…", pct=80)
            to_enrich = [l for l in leads if (not l["email"] or not l["phone"]) and l["website"]][:10]
            if to_enrich:
                idx_map = {l: i for i, l in enumerate(leads) if l in to_enrich}
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                    futs = {ex.submit(enrich_site, l["website"]): i for l, i in idx_map.items()}
                    for f in concurrent.futures.as_completed(futs, timeout=45):
                        try:
                            extra = f.result()
                            li = futs[f]
                            if extra["emails"] and not leads[li]["email"]: leads[li]["email"] = ", ".join(extra["emails"])
                            if extra["phones"] and not leads[li]["phone"]: leads[li]["phone"] = clean_phones(", ".join(extra["phones"]))
                            if extra["notes"] and not leads[li]["notes"]: leads[li]["notes"] = extra["notes"]
                        except: pass

            leads.sort(key=quality_score, reverse=True)
            leads = leads[:50]
            csv_path = save_csv(leads, niche, city)
            yield from emit("done", leads=leads, csv_file=csv_path.name, count=len(leads))

        except Exception as e:
            log.error("Search error: %s", e, exc_info=True)
            yield from emit("error", text=str(e))

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")

@app.route("/history")
def history():
    return jsonify(list_csv())

@app.route("/download/<filename>")
def download(filename):
    path = DATA_DIR / filename
    if not path.exists(): return "Not found", 404
    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
