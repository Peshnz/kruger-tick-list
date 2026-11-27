"""Build sg-transit/data.json: every public transport stop in Singapore.

Sources
  - OpenStreetMap (Overpass API): MRT/LRT stations, bus stops, bus interchanges, ferry terminals,
    bike share, cable car, and the taxi stands OSM has names for (malls, hotels).
  - LTA Taxi Stop dataset on data.gov.sg: the official list of every taxi stand and taxi stop.

Run weekly by .github/workflows/sg-transit-data.yml. If a source fails, the previous data.json is kept.
"""
import json, math, os, re, sys, time, urllib.parse, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')
TYPES = ['mrt', 'lrt', 'bus', 'int', 'taxi', 'ferry', 'bike', 'cable']   # same order as index.html
TI = TYPES.index('taxi')
UA = {'User-Agent': 'sg-transit-near-me/1.0 (+https://github.com/Peshnz/kruger-tick-list)'}
SERVERS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter',
           'https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
QUERY = """[out:json][timeout:240];
area["ISO3166-1"="SG"][admin_level=2]->.sg;
(
 node["highway"="bus_stop"](area.sg);
 nwr["amenity"="bus_station"](area.sg);
 nwr["amenity"="taxi"](area.sg);
 nwr["railway"~"^(station|halt)$"](area.sg);
 nwr["amenity"="ferry_terminal"](area.sg);
 nwr["amenity"="bicycle_rental"](area.sg);
 nwr["aerialway"="station"](area.sg);
);
out center tags;"""
LTA_TAXI = 'https://api-open.data.gov.sg/v1/public/api/datasets/d_fa1896e73ded89dd513788d501d45033/poll-download'


def metres(a, b):
    r = math.radians
    h = math.sin(r(b[0] - a[0]) / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(r(b[1] - a[1]) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def get_json(url, data=None, timeout=300):
    req = urllib.request.Request(url, data, UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# Singapore's LRT lines are not tagged consistently in OSM, so name them. Interchange stations
# (Choa Chu Kang, Bukit Panjang, Sengkang, Punggol) stay as MRT.
LRT_NAMES = {
    # Bukit Panjang LRT
    'South View', 'Keat Hong', 'Teck Whye', 'Phoenix', 'Petir', 'Pending', 'Bangkit', 'Fajar', 'Segar', 'Jelapang', 'Senja',
    # Sengkang LRT
    'Compassvale', 'Rumbia', 'Bakau', 'Kangkar', 'Ranggung', 'Cheng Lim', 'Farmway', 'Kupang', 'Thanggam', 'Fernvale', 'Layar', 'Tongkang', 'Renjong',
    # Punggol LRT
    'Cove', 'Meridian', 'Coral Edge', 'Riviera', 'Kadaloor', 'Oasis', 'Damai', 'Sam Kee', 'Teck Lee', 'Punggol Point', 'Samudera', 'Nibong', 'Sumang', 'Soo Teck',
    # Sentosa Express
    'Beach', 'Imbiah', 'Resorts World', 'VivoCity',
}
THIS_YEAR = int(time.strftime('%Y'))


def not_open(t):
    """Stations still being built or only planned (Jurong Region Line, Cross Island Line, ...)."""
    for k, v in t.items():
        if re.search(r'construction|proposed|planned|disused|abandoned|razed', k) or \
           (k in ('railway', 'public_transport', 'building') and re.search(r'construction|proposed|planned|disused', v)):
            return True
    for k in ('opening_date', 'start_date', 'check_date:opening_date'):
        m = re.match(r'(\d{4})(?:-(\d{2}))?', t.get(k, ''))
        if m and (int(m.group(1)), int(m.group(2) or 1)) > (THIS_YEAR, int(time.strftime('%m'))):
            return True
    return False


def classify(t):
    if t.get('highway') == 'bus_stop': return 'bus'
    if t.get('amenity') == 'bus_station': return 'int'
    if t.get('amenity') == 'taxi': return 'taxi'
    if t.get('amenity') == 'ferry_terminal': return 'ferry'
    if t.get('amenity') == 'bicycle_rental': return 'bike'
    if t.get('aerialway') == 'station': return 'cable'
    if t.get('railway') in ('station', 'halt'):
        name = t.get('name', '')
        if not_open(t): return None
        if re.fullmatch(r'[A-H]( North| South| East| West)?|MRT|LRT|', name.strip(), re.I): return None            # Changi Airport Skytrain A/B/C..., unnamed platforms
        if t.get('station') == 'monorail' and name not in LRT_NAMES: return None
        if re.search(r'skytrain|people mover', ' '.join(t.values()), re.I): return None
        lrt = name in LRT_NAMES or t.get('station') == 'light_rail' or t.get('light_rail') == 'yes' \
            or re.search(r'\bLRT\b', name, re.I)
        return 'lrt' if lrt else 'mrt'
    return None


def label(kind, t):
    n = t.get('name') or t.get('name:en')
    if n: return n
    return {'taxi': 'Taxi stand', 'bus': 'Bus stop', 'int': 'Bus interchange', 'ferry': 'Ferry',
            'bike': 'Bike share', 'cable': 'Cable car', 'mrt': 'MRT', 'lrt': 'LRT'}[kind]


def osm_rows():
    body = urllib.parse.urlencode({'data': QUERY}).encode()
    for attempt in range(3):
        for url in SERVERS:
            try:
                d = get_json(url, body)
                els = d.get('elements', [])
                print(f'OSM {url}: {len(els)} elements {d.get("remark", "")}')
                if len(els) > 1000:
                    break
            except Exception as e:
                print(f'OSM {url}: {e}')
        else:
            time.sleep(60)
            continue
        break
    else:
        return None
    seen, rows = {}, []
    for el in els:
        t = el.get('tags', {})
        kind = classify(t)
        if not kind: continue
        lat = el.get('lat', el.get('center', {}).get('lat'))
        lng = el.get('lon', el.get('center', {}).get('lon'))
        if lat is None: continue
        name = label(kind, t)
        key = (kind, name)
        if key in seen and kind not in ('bus', 'taxi') and metres(seen[key], (lat, lng)) < 400:
            continue   # one station mapped once per line, or as node + building
        seen[key] = (lat, lng)
        ref = (t.get('ref') or t.get('asset_ref') or '') if kind == 'bus' else ''
        rows.append([TYPES.index(kind), name, round(lat, 6), round(lng, 6), ref])
    return rows


def lta_taxi():
    for attempt in range(3):
        try:
            j = get_json(LTA_TAXI, timeout=60)
            g = get_json(j['data']['url'], timeout=120)
            pts = [(f['geometry']['coordinates'][1], f['geometry']['coordinates'][0],
                    f.get('properties', {}).get('TYPE_CD') == 'TSTAND')
                   for f in g.get('features', []) if (f.get('geometry') or {}).get('type') == 'Point']
            print(f'LTA taxi: {len(pts)} points')
            if pts: return pts
        except Exception as e:
            print(f'LTA taxi: {e}')
        time.sleep(30)
    return None


def combine(osm, taxi):
    """LTA taxi points replace OSM's: keep an OSM name where one is mapped on the same spot,
    otherwise name it after the nearest station or bus stop. OSM stands LTA doesn't list stay."""
    named = [r for r in osm if r[0] != TI and r[1] != 'Bus stop']
    osm_taxi = [r for r in osm if r[0] == TI]
    used, out = set(), [r for r in osm if r[0] != TI]
    for lat, lng, stand in taxi:
        name = None
        for k, o in enumerate(osm_taxi):
            if k not in used and abs(o[2] - lat) < .001 and metres((o[2], o[3]), (lat, lng)) < 60:
                used.add(k)
                if o[1] != 'Taxi stand': name = o[1]
                break
        if not name:
            best, bd = None, 400
            for r in named:
                if abs(r[2] - lat) > .004 or abs(r[3] - lng) > .004: continue
                d = metres((r[2], r[3]), (lat, lng))
                if d < bd: best, bd = r, d
            name = ('Taxi stand' if stand else 'Taxi stop') + (' near ' + best[1] if best else '')
        out.append([TI, name, round(lat, 6), round(lng, 6), ''])
    out += [o for k, o in enumerate(osm_taxi) if k not in used]
    return out


osm = osm_rows()
taxi = lta_taxi()
if osm is None or taxi is None:
    sys.exit('A source failed - keeping the previous data.json')
rows = combine(osm, taxi)
rows.sort(key=lambda r: (r[0], r[1], r[2]))
counts = {k: sum(1 for r in rows if r[0] == i) for i, k in enumerate(TYPES)}
print(counts)
print('MRT:', ', '.join(sorted(r[1] for r in rows if r[0] == 0)))
print('LRT:', ', '.join(sorted(r[1] for r in rows if r[0] == 1)))
if counts['bus'] < 3000 or counts['mrt'] < 80 or counts['lrt'] < 20 or counts['taxi'] < 100:
    sys.exit('Too few stops - keeping the previous data.json')
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('{"updated":"%s","counts":%s,"stops":[\n' % (time.strftime('%Y-%m-%d'), json.dumps(counts, separators=(',', ':'))))
    f.write(',\n'.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in rows))
    f.write('\n]}\n')
print(f'Wrote {len(rows)} stops to {OUT}')
