"""
Lead Finder Mini CRM - Backend v8
Priority: Armenia / Yerevan — real business leads with phones/emails
"""
import re, csv, json, logging, time, random, concurrent.futures
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, quote_plus, quote
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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s

# ── CITY DATA ────────────────────────────────────────────────────────────

CITY_BBOXES = {
    "yerevan": (40.04, 44.33, 40.32, 44.68), "erevan": (40.04, 44.33, 40.32, 44.68),
    "gyumri": (40.70, 43.74, 40.86, 43.94), "vanadzor": (41.00, 44.30, 41.22, 44.60),
    "vagharshapat": (40.14, 44.26, 40.20, 44.32), "abovyan": (40.26, 44.58, 40.30, 44.64),
    "kapan": (39.18, 46.38, 39.24, 46.46), "hrazdan": (40.48, 44.72, 40.54, 44.80),
    "armavir": (40.12, 44.02, 40.20, 44.12), "artashat": (39.94, 44.52, 40.02, 44.60),
    "sisian": (39.50, 46.02, 39.56, 46.10), "goris": (39.50, 46.32, 39.54, 46.38),
    "dilijan": (40.72, 44.82, 40.78, 44.90), "jermuk": (39.82, 45.66, 39.88, 45.74),
    "tsakhkadzor": (40.52, 44.68, 40.56, 44.74),
    "new york": (40.47, -74.26, 40.92, -73.70), "los angeles": (33.70, -118.67, 34.33, -118.16),
    "chicago": (41.64, -87.94, 42.02, -87.52), "houston": (29.52, -95.77, 30.11, -95.01),
    "boston": (42.23, -71.19, 42.43, -70.99), "miami": (25.71, -80.36, 25.88, -80.13),
    "london": (51.29, -0.51, 51.70, 0.25),
}

ARMENIAN_CITIES = {"yerevan","erevan","gyumri","vanadzor","vagharshapat","abovyan","kapan",
    "hrazdan","armavir","artashat","sisian","goris","dilijan","jermuk","tsakhkadzor"}

NICHE_SYNONYMS = {
    "dentist": ["dentist", "dental", "stomatolog"],
    "bakery": ["bakery", "bakeries", "pastry"],
    "plumber": ["plumber", "plumbing"],
    "restaurant": ["restaurant", "cafe", "bistro"],
    "lawyer": ["lawyer", "attorney", "law firm"],
    "gym": ["gym", "fitness"],
    "clinic": ["clinic", "medical center", "policlinic"],
    "pharmacy": ["pharmacy", "drugstore", "apteka"],
    "hotel": ["hotel", "motel"],
    "cafe": ["cafe", "coffee shop"],
    "hospital": ["hospital"],
    "school": ["school", "academy"],
    "auto": ["auto", "car repair", "car service"],
    "beauty": ["beauty salon", "spa", "cosmetology"],
    "real estate": ["real estate", "realtor"],
}
_SYNONYM_CANON = {s: c for c, ss in NICHE_SYNONYMS.items() for s in ss}

def get_variants(niche):
    canon = _SYNONYM_CANON.get(niche.lower().strip())
    return NICHE_SYNONYMS[canon][:3] if canon else [niche]

# ── TEXT HELPERS ─────────────────────────────────────────────────────────

def is_junk(lead):
    name = lead.get("company_name","")
    if not name or len(name) < 3: return True
    if re.match(r"^(home|search|result|page|about|contact|login|error|404)", name, re.I): return True
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
    return s

def should_skip(url):
    return any(d in url.lower() for d in [
        "wikipedia.org","youtube.com","reddit.com","facebook.com","instagram.com",
        "twitter.com","linkedin.com","google.com","yahoo.com","bing.com",
        "duckduckgo.com","amazon.com","yelp.com","bbb.org",
    ])

def clean_phones(phone_str):
    if not phone_str: return ""
    parts = [p.strip() for p in phone_str.split(",")]
    seen, out = set(), []
    for p in parts:
        p = p.strip()
        if not p: continue
        digits = re.sub(r"\D", "", p)
        if len(digits) < 7 or len(digits) > 15: continue
        if digits in seen: continue
        seen.add(digits)
        out.append(p)
    return ", ".join(out[:3])

def extract_emails(text):
    raw = list(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]{2,6}", text)))
    bad = re.compile(r"\.(png|jpe?g|gif|svg|css|js)(\?|$)", re.I)
    return [e for e in raw if not bad.search(e) and e.count("@")==1 and len(e)<=80
            and not any(x in e for x in ["bootstrap","jquery","font","example","@media","noreply"])][:5]

# ══════════════════════════════════════════════════════════════════════════
# SOURCE 1: spyur.am (main Armenian business directory)
# ══════════════════════════════════════════════════════════════════════════

def spyur_search_page(niche, city, page=1):
    results = []
    try:
        resp = get_session().get(
            "https://www.spyur.am/en/home/search/",
            params={"company_name": niche, "addres": city, "only_by_name": "1", "page": str(page)},
            timeout=12, allow_redirects=True
        )
        if resp.status_code != 200: return results
        text = resp.text
        links = re.findall(r'href="(/en/companies/[^"?#]+)"', text)
        seen = set()
        for href in links:
            if href in seen: continue
            seen.add(href)
            full = f"https://www.spyur.am{href}"
            idx = text.find(href)
            chunk = text[max(0, idx-200):idx+800]
            nm = re.search(r'class="[^"]*company_name[^"]*"[^>]*>([^<]+)<', chunk)
            title = ""
            if nm:
                title = nm.group(1).strip()
                title = re.sub(r"\s+", " ", title)
                title = re.sub(r"\s+(Individual|Entrepreneur|LLC|CJSC|OOO|Ltd)\b.*", "", title, flags=re.I).strip()
            if not title:
                slug = href.split("/")[-2] if "/" in href else href
                title = slug.replace("-", " ").strip().title()
            if title and len(title) >= 3:
                phone_in_listing = re.findall(r'(?:\+374|0)[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{3}', chunk)
                phone_str = ", ".join(phone_in_listing[:2]) if phone_in_listing else ""
                results.append({"title": title, "link": full, "phone_listing": phone_str})
    except Exception as e:
        log.debug("spyur page %d: %s", page, e)
    return results

def spyur_search(niche, city, max_r=80):
    all_r, seen = [], set()
    variants = get_variants(niche)
    if niche not in variants:
        variants.insert(0, niche)
    for var in variants:
        if len(all_r) >= max_r: break
        for pg in range(1, 5):
            if len(all_r) >= max_r: break
            res = spyur_search_page(var, city, pg)
            if not res: break
            for r in res:
                if r["link"] not in seen:
                    seen.add(r["link"])
                    all_r.append(r)
            if len(res) < 10: break
            time.sleep(0.8)
    return all_r[:max_r]

def spyur_details(url):
    info = {"phones": [], "address": "", "website": "", "emails": []}
    try:
        resp = get_session().get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200: return info
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.select("script, style, header, footer, nav"): tag.decompose()
        plain = soup.get_text(" ", strip=True)
        spyur_phones = {"07803803","0357031063","0357097971","0961107813"}
        phone_patterns = re.findall(r'(?:\+374|0)[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{3}', text)
        tel_patterns = re.findall(r'tel:(\+?374\d{8,11}|\d{8})', text)
        all_phones = phone_patterns + [f"+{p[:3]}-{p[3:5]}-{p[5:8]}-{p[8:]}" if len(p)>=8 and p.startswith("374") else p for p in tel_patterns]
        seen_p = set()
        for p in all_phones:
            digits = re.sub(r"\D", "", p)
            if digits in spyur_phones or digits in seen_p: continue
            seen_p.add(digits)
            info["phones"].append(p)
            if len(info["phones"]) >= 3: break
        mailto_emails = re.findall(r'mailto:([^"?\s&]+)', text)
        if mailto_emails:
            info["emails"] = list(dict.fromkeys(mailto_emails))[:3]
        else:
            info["emails"] = extract_emails(text)[:3]
        web_m = re.search(r'[Ww]eb\s*[Ss]ite[:\s]*\n?\s*(https?://[^\s<>"\']{5,80})', plain)
        if not web_m:
            web_m = re.search(r'[Ss]ite[:\s]*\n?\s*(https?://[^\s<>"\']{5,80})', plain)
        if web_m:
            info["website"] = web_m.group(1).rstrip(".,;)")
        addr_m = re.search(r'(\d{4,6}\s*,?\s*(?:Yerevan|Erevan)[^,\n]{0,60})', plain, re.I)
        if addr_m:
            info["address"] = addr_m.group(1).strip()[:120]
    except Exception as e:
        log.debug("spyur detail %s: %s", url, e)
    return info

# ══════════════════════════════════════════════════════════════════════════
# SOURCE 2: list.am (Armenian classifieds)
# ══════════════════════════════════════════════════════════════════════════

def listam_search(niche, city, limit=15):
    results = []
    try:
        resp = get_session().get("https://www.list.am/en/search",
            params={"q": f"{niche} {city}"}, timeout=10)
        if resp.status_code != 200: return results
        text = resp.text
        listing_links = re.findall(r'href="(/en/item/\d+)"', text)
        seen = set()
        for href in listing_links[:limit]:
            if href in seen: continue
            seen.add(href)
            full = f"https://www.list.am{href}"
            idx = text.find(href)
            chunk = text[max(0,idx-50):idx+300]
            tm = re.search(r'class="[^"]*title[^"]*"[^>]*>([^<]+)<', chunk)
            title = tm.group(1).strip() if tm else ""
            if not title:
                tm2 = re.search(r'<a[^>]*' + re.escape(href) + r'[^>]*>([^<]+)<', chunk)
                title = tm2.group(1).strip() if tm2 else niche.title()
            if title and len(title) >= 3:
                results.append({"title": title, "link": full, "source": "list.am"})
    except Exception as e:
        log.debug("list.am error: %s", e)
    return results[:limit]

def listam_details(url):
    info = {"phones": [], "address": "", "website": "", "emails": [], "notes": ""}
    try:
        resp = get_session().get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200: return info
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.select("script, style"): tag.decompose()
        plain = soup.get_text(" ", strip=True)
        phones = re.findall(r'(?:\+374|0)[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{3}', plain)
        info["phones"] = list(dict.fromkeys(phones))[:3]
        info["emails"] = extract_emails(text)[:3]
        desc = re.search(r'[Dd]escription[:\s]*([^\n]{20,200})', plain)
        if desc: info["notes"] = desc.group(1).strip()[:150]
    except Exception as e:
        log.debug("list.am detail %s: %s", url, e)
    return info

# ══════════════════════════════════════════════════════════════════════════
# SOURCE 3: OSM Overpass API
# ══════════════════════════════════════════════════════════════════════════

NICHE_OSM = {
    "bakery": ['shop="bakery"'], "dentist": ['healthcare="dentist"', 'amenity="dentist"'],
    "doctor": ['healthcare="doctor"', 'amenity="doctors"'], "clinic": ['amenity="clinic"', 'healthcare="clinic"'],
    "hospital": ['amenity="hospital"'], "pharmacy": ['amenity="pharmacy"'],
    "restaurant": ['amenity="restaurant"'], "cafe": ['amenity="cafe"'],
    "hotel": ['tourism="hotel"'], "gym": ['leisure="fitness_centre"'],
    "lawyer": ['office="lawyer"'], "plumber": ['craft="plumber"'],
    "shop": ['shop'], "company": ['office'], "beauty": ['shop="beauty"', 'shop="hairdresser"'],
}

def get_osm_filters(niche):
    n = niche.lower().strip()
    canon = _SYNONYM_CANON.get(n, n)
    return NICHE_OSM.get(canon, NICHE_OSM.get(n, []))

def osm_search(niche, city, limit=30):
    filters = get_osm_filters(niche)
    if not filters: return []
    city_lower = city.lower().strip()
    bbox = CITY_BBOXES.get(city_lower)
    try:
        if bbox:
            tag_str = "".join(
                f'  node[{f}]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});\n'
                f'  way[{f}]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});\n'
                for f in filters
            )
            query = f"[out:json][timeout:25];\n(\n{tag_str});\nout body {limit};\n"
        else:
            tag_str = "".join(f"  node[{f}](area.search);\n  way[{f}](area.search);\n" for f in filters)
            query = f'[out:json][timeout:25];\narea["name=\""{city}\""]["admin_level"]->.search;\n(\n{tag_str}\n);\nout body {limit};\n'
        r = requests.post("https://overpass-api.de/api/interpreter", data={"data": query},
            headers={"User-Agent": "LeadFinderCRM/3.0"}, timeout=30)
        if r.status_code != 200 or not r.text.strip(): return []
        elems = r.json().get("elements", [])
        results = []
        for el in elems:
            t = el.get("tags", {})
            name = t.get("name", "")
            if not name or len(name) < 2: continue
            name_lower = name.lower()
            if re.match(r'^\d+[\w/]*$', name): continue
            if re.match(r'^\d{4,}$', name): continue
            if any(kw in name_lower for kw in ["street","avenue","boulevard","road","lane","drive","փողոց"]): continue
            if re.match(r'^\d+[/-]\d+$', name): continue
            osm_amenity = t.get("amenity", "")
            osm_shop = t.get("shop", "")
            osm_craft = t.get("craft", "")
            osm_office = t.get("office", "")
            has_type = bool(osm_amenity or osm_shop or osm_craft or osm_office)
            name_words = name.split()
            is_biz = (
                has_type or
                (len(name_words) >= 2 and any(w[0].isupper() for w in name_words)) or
                any(kw in name_lower for kw in ["clinic","dental","dentist","center","studio","salon","shop","store","pharmacy","hospital","gym","cafe","restaurant","hotel","school","group","company","agency","office","medical","health","beauty","spa","fitness","auto","car","repair","service","law","legal","accounting","consulting","it","tech","software"])
            )
            if not is_biz:
                if not t.get("phone") and not t.get("website"): continue
            phone_raw = t.get("phone", t.get("contact:phone", ""))
            phone = ""
            if phone_raw:
                d = re.sub(r"\D", "", phone_raw)
                if d.startswith("374") and len(d) == 11:
                    phone = f"+{d[:3]}-{d[3:5]}-{d[5:8]}-{d[8:]}"
                else:
                    phone = phone_raw
            results.append({
                "title": name,
                "link": t.get("website", t.get("contact:website", "")),
                "phone": phone,
                "email": t.get("email", t.get("contact:email", "")),
                "notes": f'{t.get("addr:street","")}, {t.get("addr:city",city)}'.strip(", "),
                "source": "osm"
            })
        return results
    except Exception as e:
        log.warning("OSM error: %s", e)
        return []

# ══════════════════════════════════════════════════════════════════════════
# SOURCE 4: Website enrichment
# ══════════════════════════════════════════════════════════════════════════

def enrich_site(url):
    info = {"emails": [], "phones": [], "notes": ""}
    if not url or not url.startswith("http"): return info
    try:
        resp = get_session().get(url, timeout=8, allow_redirects=True)
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.select("script, style"): tag.decompose()
        plain = soup.get_text(" ", strip=True)
        for a in soup.select("a[href^='mailto:']"):
            e = a["href"].replace("mailto:","").split("?")[0].strip()
            if e and "@" in e and len(e)<=80: info["emails"].append(e)
        if not info["emails"]:
            info["emails"] = extract_emails(text)[:3]
        phones = re.findall(r'[\+]?[\d\s\-\(\)]{7,20}', plain)
        seen_p, out_p = set(), []
        for p in phones:
            d = re.sub(r"\D", "", p)
            if 7 <= len(d) <= 15 and d not in seen_p:
                seen_p.add(d)
                out_p.append(p.strip())
        info["phones"] = ", ".join(out_p[:3])
        meta = soup.find("meta", attrs={"name": lambda x: x and x.lower() in ("description","og:description")})
        if meta: info["notes"] = (meta.get("content","") or "")[:150]
    except Exception as e:
        log.debug("enrich %s: %s", url[:50], e)
    return info

# ══════════════════════════════════════════════════════════════════════════
# DEMO FALLBACK
# ══════════════════════════════════════════════════════════════════════════

DEMO_BY_NICHE = {
    "dentist": [("Dental Care Clinic","+1-555-0101","info@dentalcare.com"),("Smile Dentistry","+1-555-0102","contact@smiledental.com"),("Family Dental","+1-555-0103","info@familydental.com")],
    "bakery": [("Sunrise Bakery","+1-555-0201","orders@sunrisebakery.com"),("Artisan Bread Co.","+1-555-0202","info@artisanbread.com")],
    "plumber": [("Quick Fix Plumbing","+1-555-0301","info@quickfix.com"),("Pro Plumbers","+1-555-0302","office@proplumbers.com")],
    "lawyer": [("Law Offices","+1-555-0401","info@law.com"),("Legal Group","+1-555-0402","contact@legal.com")],
    "restaurant": [("Corner Bistro","+1-555-0501","info@bistro.com"),("City Grill","+1-555-0502","res@grill.com")],
    "gym": [("FitLife Gym","+1-555-0601","info@fitlife.com"),("PowerHouse","+1-555-0602","join@powerhouse.com")],
    "clinic": [("Health Clinic","+1-555-0701","info@health.com"),("Med Center","+1-555-0702","appt@med.com")],
    "company": [("Global Solutions","+1-555-0801","info@global.com"),("Premier Group","+1-555-0802","contact@premier.com")],
}

# ── CSV ─────────────────────────────────────────────────────────────────

def save_csv(leads, niche, city):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sn = re.sub(r'\W+', '_', niche)[:30]
    sc = re.sub(r'\W+', '_', city)[:30]
    fn = f"leads_{sn}_{sc}_{ts}.csv"
    path = DATA_DIR / fn
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["company_name","website","email","phone","notes"], extrasaction="ignore")
        w.writeheader()
        w.writerows(leads)
    return path

def list_csv():
    return sorted([f.name for f in DATA_DIR.glob("*.csv") if f.name!="app.log"], reverse=True)

# ══════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

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
        seen = set()
        def emit(t, **kw): yield json.dumps({"type": t, **kw}) + "\n"
        def add_lead(lead):
            if is_junk(lead): return False
            name = lead.get("company_name","").lower().strip()[:40]
            if name in seen: return False
            seen.add(name)
            leads.append(lead)
            return True

        try:
            city_lower = city.lower().strip()
            is_armenian = city_lower in ARMENIAN_CITIES

            # ── Phase 1: Armenian sources ──
            if is_armenian:
                yield from emit("progress", text="🔍 spyur.am + list.am…", pct=5)
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    f_spyur = pool.submit(spyur_search, niche, city)
                    f_listam = pool.submit(listam_search, niche, city)
                    spyur_results = f_spyur.result(timeout=45) or []
                    listam_results = f_listam.result(timeout=20) or []

                yield from emit("progress", text=f"📋 {len(spyur_results)} spyur, {len(listam_results)} list.am", pct=20)

                # Spyur details concurrently
                if spyur_results:
                    yield from emit("progress", text=f"📞 {len(spyur_results[:25])} spyur details…", pct=30)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                        futs = {pool.submit(spyur_details, r["link"]): r for r in spyur_results[:25]}
                        for f in concurrent.futures.as_completed(futs, timeout=40):
                            try:
                                r = futs[f]
                                d = f.result()
                                phone = clean_phones(", ".join(d.get("phones",[])))
                                if not phone and r.get("phone_listing"):
                                    phone = clean_phones(r["phone_listing"])
                                lead = {"company_name": r["title"], "website": d.get("website",""),
                                    "email": ", ".join(d.get("emails",[])), "phone": phone,
                                    "notes": d.get("address","") or "spyur.am", "link": r["link"]}
                                if add_lead(lead): yield from emit("lead", lead=lead)
                            except Exception:
                                try:
                                    r = futs[f]
                                    lead = {"company_name": r["title"], "website": "", "email": "",
                                        "phone": clean_phones(r.get("phone_listing","")),
                                        "notes": "spyur.am", "link": r["link"]}
                                    if add_lead(lead): yield from emit("lead", lead=lead)
                                except: pass

                for r in listam_results:
                    try:
                        d = listam_details(r["link"])
                        lead = {"company_name": r["title"], "website": "",
                            "email": ", ".join(d.get("emails",[])),
                            "phone": clean_phones(", ".join(d.get("phones",[]))),
                            "notes": d.get("notes","") or "list.am", "link": r["link"]}
                        if add_lead(lead): yield from emit("lead", lead=lead)
                    except: pass

            # ── Phase 2: OSM ──
            yield from emit("progress", text="🌍 OSM…", pct=55)
            osm_results = osm_search(niche, city, limit=30) or []
            for r in osm_results:
                lead = {"company_name": r["title"], "website": r.get("link",""),
                    "email": r.get("email",""), "phone": clean_phones(r.get("phone","")),
                    "notes": r.get("notes",""), "link": r.get("link","")}
                if add_lead(lead): yield from emit("lead", lead=lead)

            # ── Phase 3: Demo fallback ──
            if not leads:
                yield from emit("progress", text="⚠ Demo fallback", pct=75)
                nk = _SYNONYM_CANON.get(niche.lower(), niche.lower())
                for name, phone, email in DEMO_BY_NICHE.get(nk, DEMO_BY_NICHE.get("company", [])):
                    l = {"company_name": f"{name} ({city})", "website": "", "email": email,
                         "phone": phone, "notes": "Demo"}
                    if add_lead(l): yield from emit("lead", lead=l)

            # ── Phase 4: Enrich ──
            to_enrich = [(i, l) for i, l in enumerate(leads)
                         if (not l.get("phone") or not l.get("email"))
                         and l.get("website") and not should_skip(l.get("website",""))][:8]
            if to_enrich:
                yield from emit("progress", text=f"🔄 Enriching {len(to_enrich)}…", pct=85)
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futs = {pool.submit(enrich_site, l["website"]): i for i, l in to_enrich}
                    for f in concurrent.futures.as_completed(futs, timeout=20):
                        try:
                            extra = f.result()
                            li = futs[f]
                            if extra["emails"] and not leads[li].get("email"):
                                leads[li]["email"] = ", ".join(extra["emails"])
                            if extra["phones"] and not leads[li].get("phone"):
                                leads[li]["phone"] = extra["phones"][:200]
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
    port = int(os.environ.get("PORT", 7860))
    app.run(debug=False, host="0.0.0.0", port=port)
