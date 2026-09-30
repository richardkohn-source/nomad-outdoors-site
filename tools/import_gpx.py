"""Import Gaia GPS (or any) GPX files into the Nomad Outdoors route library.

Usage:  python3 tools/import_gpx.py [file.gpx ...]
        (with no arguments it re-processes everything in content/gpx/)

For each track it writes:
  dist/data/routes/<slug>.json   map track, elevation profile and stats
  dist/data/routes/<slug>.gpx    tidy, trimmed GPX for download
  dist/data/routes/index.json    the library list with totals
  dist/sitemap.xml
Editable titles, notes and flags live in content/routes/meta.json; the importer
adds new routes there with working titles and never overwrites your edits.

Privacy: waypoints are never copied; the first and last PRIVACY_TRIM_M metres of
every track are removed; any stop longer than CAMP_STOP_H hours (an overnight
camp) is cut out along with CAMP_RADIUS_M around it.
"""
import json, math, re, shutil, sys, pathlib, datetime
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
GPX_DIR = ROOT / "content" / "gpx"
META = ROOT / "content" / "routes" / "meta.json"
OUT = ROOT / "dist" / "data" / "routes"
SITE = "https://www.nomadoutdoors.org"

PRIVACY_TRIM_M = 500
CAMP_STOP_H = 2.0
CAMP_RADIUS_M = 300
MAP_TOLERANCE_M = 8       # track simplification for the map
THUMB_POINTS = 70         # points in the list thumbnail

# Rough gazetteer: nearest named area within its radius wins. Extend as needed.
AREAS = [
    # name, country, lat, lon, radius_km
    ("Al Qudra", "UAE", 24.80, 55.38, 22),
    ("Lisaili and Al Faqa", "UAE", 24.85, 55.58, 18),
    ("Sweihan", "UAE", 24.45, 55.33, 25),
    ("Fossil Rock", "UAE", 25.18, 55.83, 15),
    ("Al Dhaid and Falaj Al Mualla", "UAE", 25.40, 55.88, 25),
    ("Hatta", "UAE", 24.80, 56.12, 20),
    ("Liwa", "UAE", 23.10, 53.70, 70),
    ("Al Ain desert", "UAE", 24.20, 55.70, 35),
    ("Hisma, Tabuk", "Saudi Arabia", 28.70, 35.90, 120),
    ("Great Nafud, Ha'il", "Saudi Arabia", 28.20, 41.00, 150),
    ("Eastern Province near Qatar", "Saudi Arabia", 24.20, 51.20, 60),
]
COUNTRY_BOXES = [  # fallback when no named area matches: (name, lat_min, lat_max, lon_min, lon_max)
    ("UAE", 22.6, 26.1, 51.6, 56.4), ("Oman", 16.6, 26.4, 52.0, 59.9), ("Saudi Arabia", 16.3, 32.2, 34.5, 55.7),
]

def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 2 * R * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))

def parse_time(s):
    if not s: return None
    s = s.strip().replace("Z", "+00:00")
    try: return datetime.datetime.fromisoformat(s)
    except ValueError: return None

def read_tracks(path):
    root = ET.parse(path).getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    for trk in root.findall(ns + "trk"):
        pts = []
        for p in trk.iter(ns + "trkpt"):
            ele = p.findtext(ns + "ele")
            pts.append({"lat": float(p.get("lat")), "lon": float(p.get("lon")),
                        "ele": float(ele) if ele not in (None, "") else None,
                        "t": parse_time(p.findtext(ns + "time"))})
        if len(pts) >= 10:
            yield (trk.findtext(ns + "name") or "").strip(), pts

def trim_ends(pts, metres):
    def cut(seq):
        d = 0
        for i in range(1, len(seq)):
            d += hav((seq[i-1]["lat"], seq[i-1]["lon"]), (seq[i]["lat"], seq[i]["lon"]))
            if d >= metres: return i
        return len(seq)
    a = cut(pts); b = len(pts) - cut(pts[::-1])
    return pts[a:b] if b - a >= 10 else pts

def cut_camps(pts):
    """Remove long stationary periods (overnight camps) and the area around them.
    Returns (segments, number_of_camps_removed)."""
    segs, cur, camps, i = [], [], 0, 0
    n = len(pts)
    while i < n:
        j = i
        while j + 1 < n and hav((pts[i]["lat"], pts[i]["lon"]), (pts[j+1]["lat"], pts[j+1]["lon"])) < CAMP_RADIUS_M:
            j += 1
        if pts[i]["t"] and pts[j]["t"] and (pts[j]["t"] - pts[i]["t"]).total_seconds() >= CAMP_STOP_H * 3600:
            centre = (pts[i]["lat"], pts[i]["lon"])
            while cur and hav((cur[-1]["lat"], cur[-1]["lon"]), centre) < CAMP_RADIUS_M * 3: cur.pop()
            if len(cur) >= 2: segs.append(cur)
            cur, camps = [], camps + 1
            k = j + 1
            while k < n and hav((pts[k]["lat"], pts[k]["lon"]), centre) < CAMP_RADIUS_M * 3: k += 1
            i = k
            continue
        cur.append(pts[i]); i += 1
    if len(cur) >= 2: segs.append(cur)
    return segs, camps

def rdp(points, eps):
    """Ramer-Douglas-Peucker on (x metres, y metres, payload) tuples."""
    if len(points) < 3: return points
    keep = [False] * len(points); keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        s, e = stack.pop()
        ax, ay = points[s][0], points[s][1]; bx, by = points[e][0], points[e][1]
        dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1e-9
        best, idx = -1, -1
        for k in range(s + 1, e):
            d = abs(dy * points[k][0] - dx * points[k][1] + bx * ay - by * ax) / L
            if d > best: best, idx = d, k
        if best > eps:
            keep[idx] = True; stack += [(s, idx), (idx, e)]
    return [p for p, k in zip(points, keep) if k]

def to_xy(pts, lat0):
    kx = 111320 * math.cos(math.radians(lat0)); ky = 110540
    return [(p["lon"] * kx, p["lat"] * ky, p) for p in pts]

def smooth(vals, w=9):
    out, h = [], w // 2
    for i in range(len(vals)):
        win = [v for v in vals[max(0, i-h): i+h+1] if v is not None]
        out.append(sum(win) / len(win) if win else None)
    return out

def stats(segs):
    dist = moving = 0.0
    eles = []
    for seg in segs:
        for a, b in zip(seg, seg[1:]):
            d = hav((a["lat"], a["lon"]), (b["lat"], b["lon"])); dist += d
            if a["t"] and b["t"]:
                dt = (b["t"] - a["t"]).total_seconds()
                if 0 < dt < 300 and d / dt > 0.6: moving += dt
        eles += smooth([p["ele"] for p in seg])
    ev = [e for e in eles if e is not None]
    ascent, last = 0.0, (ev[0] if ev else None)
    for e in ev:  # 3 m hysteresis filters GPS jitter
        if e - last >= 3: ascent += e - last; last = e
        elif last - e >= 3: last = e
    first = next((p["t"] for p in segs[0] if p["t"]), None)
    lastt = next((p["t"] for p in reversed(segs[-1]) if p["t"]), None)
    return {
        "distance_km": round(dist / 1000, 1),
        "duration_min": round((lastt - first).total_seconds() / 60) if first and lastt else None,
        "moving_min": round(moving / 60),
        "ascent_m": round(ascent),
        "ele_max_m": round(max(ev)) if ev else None,
        "ele_min_m": round(min(ev)) if ev else None,
    }

def area_for(lat, lon):
    best = None
    for name, country, alat, alon, r in AREAS:
        d = hav((lat, lon), (alat, alon)) / 1000
        if d <= r and (best is None or d < best[0]): best = (d, name, country)
    if best: return best[1], best[2]
    for name, a, b, c, d in COUNTRY_BOXES:
        if a <= lat <= b and c <= lon <= d: return None, name
    return None, None

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def local_date(t):  # Gulf time for dates and titles
    return (t + datetime.timedelta(hours=4)).date() if t else None

def process(name, pts, meta):
    t0 = next((p["t"] for p in pts if p["t"]), None)
    lat0 = sum(p["lat"] for p in pts) / len(pts); lon0 = sum(p["lon"] for p in pts) / len(pts)
    area, country = area_for(lat0, lon0)
    day = local_date(t0)
    trimmed = trim_ends(pts, PRIVACY_TRIM_M)
    segs, camps = cut_camps(trimmed)
    if not segs: return None
    st = stats(segs)
    slug = slugify(f"{day.isoformat() if day else 'undated'}-{area or country or 'route'}")
    base, n = slug, 2
    while slug in process.seen: slug, n = f"{base}-{n}", n + 1
    process.seen.add(slug)

    m = meta.setdefault(slug, {})
    if "title" not in m:
        place = area or country or "Off-road route"
        m.update({
            "title": f"{place}" + (" overland" if st["distance_km"] > 150 else "") + (f", {day.strftime('%B %Y')}" if day else ""),
            "type": "overland" if st["distance_km"] > 150 else "desert",
            "notes": "", "vehicle": "", "hidden": False, "featured": False,
            "gaia_name": name, "draft_title": True,
        })

    # map track: simplified per segment, rounded to ~1 m
    map_segs, profile, run = [], [], 0.0
    for seg in segs:
        xy = to_xy(seg, lat0)
        simp = rdp(xy, MAP_TOLERANCE_M)
        map_segs.append([[round(p[2]["lat"], 5), round(p[2]["lon"], 5)] for p in simp])
        eles = smooth([p["ele"] for p in seg])
        for i, p in enumerate(seg):
            if i: run += hav((seg[i-1]["lat"], seg[i-1]["lon"]), (p["lat"], p["lon"]))
            if eles[i] is not None: profile.append((run, eles[i], p["lat"], p["lon"]))
    step = max(1, len(profile) // 300)
    profile = [[round(d / 1000, 2), round(e), round(la, 5), round(lo, 5)] for d, e, la, lo in profile[::step]]

    allpts = [pt for s in map_segs for pt in s]
    thumb_step = max(1, len(allpts) // THUMB_POINTS)
    lats = [p[0] for p in allpts]; lons = [p[1] for p in allpts]
    return {
        "slug": slug, "title": m["title"], "type": m.get("type", "desert"), "area": area, "country": country,
        "date": day.isoformat() if day else None,
        "start_local": (t0 + datetime.timedelta(hours=4)).strftime("%H:%M") if t0 else None,
        "notes": m.get("notes", ""), "vehicle": m.get("vehicle", ""), "featured": bool(m.get("featured")),
        "hidden": bool(m.get("hidden")), "camps_removed": camps, **st,
        "bbox": [min(lats), min(lons), max(lats), max(lons)],
        "centre": [round(lat0, 4), round(lon0, 4)],
        "thumb": [[round(p[0], 4), round(p[1], 4)] for p in allpts[::thumb_step]] + [[round(allpts[-1][0], 4), round(allpts[-1][1], 4)]],
        "segments": map_segs, "profile": profile,
    }
process.seen = set()

def write_gpx(route, path):
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    segs = "".join("<trkseg>" + "".join(f'<trkpt lat="{a}" lon="{b}"/>' for a, b in s) + "</trkseg>" for s in route["segments"])
    path.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Nomad Outdoors" xmlns="http://www.topografix.com/GPX/1/1">'
                    f'<metadata><name>{esc(route["title"])}</name><link href="{SITE}/routes/{route["slug"]}"/></metadata>'
                    f'<trk><name>{esc(route["title"])}</name>{segs}</trk></gpx>\n')

def main(args):
    GPX_DIR.mkdir(parents=True, exist_ok=True); META.parent.mkdir(parents=True, exist_ok=True)
    for a in args:  # keep originals in the repo so everything can be rebuilt
        src = pathlib.Path(a); dst = GPX_DIR / re.sub(r"^[0-9a-f]{8}-", "", src.name)
        if src.resolve() != dst.resolve(): shutil.copy(src, dst)
    meta = json.loads(META.read_text()) if META.exists() else {}
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    routes = []
    for f in sorted(GPX_DIR.glob("*.gpx")):
        for name, pts in read_tracks(f):
            r = process(name, pts, meta)
            if r: routes.append(r)
    # meta may override computed fields after an edit
    for r in routes:
        m = meta[r["slug"]]
        for k in ("title", "type", "notes", "vehicle", "featured", "hidden", "area"):
            if k in m and m[k] not in (None, ""): r[k] = m[k]
    META.write_text(json.dumps(dict(sorted(meta.items())), indent=2, ensure_ascii=False) + "\n")

    visible = sorted([r for r in routes if not r["hidden"]], key=lambda r: r["date"] or "", reverse=True)
    for r in visible:
        (OUT / f"{r['slug']}.json").write_text(json.dumps(r, separators=(",", ":"), ensure_ascii=False))
        write_gpx(r, OUT / f"{r['slug']}.gpx")
    index = {
        "totals": {
            "routes": len(visible),
            "distance_km": round(sum(r["distance_km"] for r in visible)),
            "moving_hours": round(sum(r["moving_min"] for r in visible) / 60),
            "countries": sorted({r["country"] for r in visible if r["country"]}),
            "areas": len({r["area"] for r in visible if r["area"]}),
        },
        "routes": [{k: r[k] for k in ("slug", "title", "type", "area", "country", "date", "distance_km", "moving_min",
                                      "duration_min", "ascent_m", "featured", "thumb")} for r in visible],
    }
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False))
    urls = [f"{SITE}/", f"{SITE}/routes"] + [f"{SITE}/routes/{r['slug']}" for r in visible]
    (ROOT / "dist" / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    for r in visible:
        print(f"{r['slug']:48} {r['distance_km']:7.1f} km  {r['moving_min']:4d} min moving  +{r['ascent_m']}m  camps cut: {r['camps_removed']}")
    print(f"{len(visible)} routes, {index['totals']['distance_km']} km")

if __name__ == "__main__":
    main(sys.argv[1:])
