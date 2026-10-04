import sys, json, re, urllib.request, urllib.parse, time
sys.stdout.reconfigure(encoding='utf-8')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}

def gj(u, t=40, retry=5):
    last = None
    for i in range(retry):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                sys.stderr.write(f'  (busy {e.code}, retry {i+1})\n')
                time.sleep(2.5 + i * 2.5)
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(2)
    raise last

def cid_of(cas):
    return gj("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/" + urllib.parse.quote(cas) + "/cids/JSON")['IdentifierList']['CID'][0]

KEY = re.compile(r'fire|react|spill|quench|extinguish|emergency|first aid|handling|storage|protective|stabilit|decompos|hazard|precaution|disposal|accidental|leak|neutraliz', re.I)

def headings_with_text(obj):
    """返回 [(heading, [文本...]), ...]，只保留有 StringWithMarkup 的叶子"""
    out = []
    def walk(o, cur):
        if isinstance(o, dict):
            h = o.get('TOCHeading')
            nxt = h if h else cur
            if isinstance(o.get('StringWithMarkup'), list):
                txts = [s.get('String') for s in o['StringWithMarkup'] if s and s.get('String')]
                if txts: out.append((nxt or '?', txts))
            for v in o.values():
                if v is not o.get('StringWithMarkup'): walk(v, nxt)
        elif isinstance(o, list):
            for v in o: walk(v, cur)
    walk(obj, None)
    return out

print("=" * 100)
print("A. 正丁基锂：全部含文本的 heading（筛安全相关）")
print("=" * 100)
cid = cid_of("109-72-8")
d = gj(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON")
rows = headings_with_text(d)
seen = set()
for h, txts in rows:
    if h in seen: continue
    seen.add(h)
    tag = '★' if KEY.search(h) else ' '
    print(f"  {tag} {h:<52} {str(txts[0])[:70]}")

print()
print("=" * 100)
print("B. 安全相关 heading 的完整内容（正丁基锂）")
print("=" * 100)
shown = set()
for h, txts in rows:
    if not KEY.search(h): continue
    key = h
    if key in shown: continue
    shown.add(key)
    print(f"\n■ {h}")
    for t in txts[:4]:
        print(f"   {t[:400]}")

print()
print("=" * 100)
print("C. 其它试剂有没有 'Reactivity Profile' / 'Fire Fighting' 之类")
print("=" * 100)
for name, cas in [("叔丁基锂","594-19-4"), ("氢化钠","7646-69-7"), ("三氟乙酸","76-05-1"),
                  ("乙酰氯","75-36-5"), ("二异丁基氢化铝","1191-15-7"), ("氢化锂铝","16853-85-3")]:
    try:
        c = cid_of(cas)
        dd = gj(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{c}/JSON")
        hs = []
        def walk2(o):
            if isinstance(o, dict):
                h = o.get('TOCHeading')
                if h and KEY.search(h) and h not in hs: hs.append(h)
                for v in o.values(): walk2(v)
            elif isinstance(o, list):
                for v in o: walk2(v)
        walk2(dd)
        print(f"\n  {name} (CID {c}): {hs}")
    except Exception as e:
        print(f"\n  {name}: FAIL {type(e).__name__} {str(e)[:50]}")
    time.sleep(0.3)
