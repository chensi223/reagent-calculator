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
                time.sleep(3 + i * 3); continue
            raise
        except Exception as e:
            last = e; time.sleep(2)
    raise last

def cid_of(cas):
    return gj("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/" + urllib.parse.quote(cas) + "/cids/JSON")['IdentifierList']['CID'][0]

def heading_texts(cid, heading):
    u = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=" + urllib.parse.quote(heading)
    try:
        d = gj(u)
    except Exception:
        return None
    out = []
    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get('StringWithMarkup'), list):
                for s in o['StringWithMarkup']:
                    if s and s.get('String'): out.append(s['String'])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d)
    return out or None

HEADS = ['Stability and Reactivity', 'Reactivity Alerts', 'CSL Reaction Information',
         'Exposure Control and Personal Protection', 'Fire Fighting', 'Extinguishing Media',
         'First Aid Measures', 'Handling and Storage']

reagents = [("正丁基锂","109-72-8"), ("叔丁基锂","594-19-4"), ("氢化钠","7646-69-7"),
            ("氢化锂铝","16853-85-3"), ("二异丁基氢化铝","1191-15-7"), ("乙酰氯","75-36-5")]

print("=" * 100)
print("各试剂在相关 heading 上的覆盖情况")
print("=" * 100)
coverage = {h: 0 for h in HEADS}
data = {}
for name, cas in reagents:
    try:
        cid = cid_of(cas); time.sleep(0.4)
    except Exception as e:
        print(f"\n{name}: CID 查询失败 {e}"); continue
    data[name] = {}
    print(f"\n■ {name} (CID {cid})")
    for h in HEADS:
        t = heading_texts(cid, h)
        time.sleep(0.4)
        if t:
            coverage[h] += 1
            data[name][h] = t
            print(f"   ✓ {h:<42} {len(t)} 条")
        else:
            print(f"   · {h:<42} —")

print()
print("=" * 100)
print("覆盖率汇总（共 %d 个试剂）" % len(reagents))
print("=" * 100)
for h in HEADS:
    print(f"  {h:<44} {coverage[h]}/{len(reagents)}")

print()
print("=" * 100)
print("★ 实际内容（正丁基锂 / 叔丁基锂 / 氢化锂铝）")
print("=" * 100)
for name in ["正丁基锂", "叔丁基锂", "氢化锂铝"]:
    if name not in data: continue
    print(f"\n{'='*90}\n■■ {name}\n{'='*90}")
    for h, txts in data[name].items():
        print(f"\n  ── {h} ──")
        for t in txts[:6]:
            print(f"     {t[:500]}")
