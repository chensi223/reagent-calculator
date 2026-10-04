import sys, os, io, json, re, time, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}

AW = {'H':1.008,'Li':6.94,'B':10.81,'C':12.011,'N':14.007,'O':15.999,'F':18.998403163,
      'Na':22.98976928,'Mg':24.305,'Al':26.9815385,'Si':28.085,'P':30.973761998,'S':32.06,
      'Cl':35.45,'K':39.0983,'Ca':40.078,'Ti':47.867,'Cr':51.9961,'Mn':54.938044,'Fe':55.845,
      'Co':58.933194,'Ni':58.6934,'Cu':63.546,'Zn':65.38,'Br':79.904,'Pd':106.42,'Ag':107.8682,
      'I':126.90447,'Cs':132.90545196,'Ba':137.327,'Pt':195.084,'Au':196.966569,'Mo':95.95,'W':183.84}
MM = {'H':1.0078250319,'Li':7.016004,'B':11.0093055,'C':12.0,'N':14.0030740052,'O':15.9949146221,
      'F':18.99840320,'Na':22.98976928,'Mg':23.9850417,'Al':26.9815385,'Si':27.9769265,
      'P':30.97376151,'S':31.97207069,'Cl':34.96885271,'K':38.96370649,'Ca':39.9625909,
      'Fe':55.9349363,'Ni':57.9353429,'Cu':62.9295975,'Zn':63.9291422,'Br':78.9183376,
      'Pd':105.903486,'Ag':106.905097,'I':126.904468,'Cs':132.90545196,'Ba':137.905247,'Pt':194.9647911}

# 失败条目的人工 CAS 补丁（全部已过校验位，再经 PubChem 分子式核对）
PATCH = {
    "二甲苯": "1330-20-7",
    "叔丁醇钠": "865-48-5",
    "仲丁基锂": "598-30-1",
    "双(三甲基硅基)氨基锂": "4039-32-1",
    "双(三甲基硅基)氨基钠": "1070-89-9",
    "1,8-二氮杂双环十一碳-7-烯": "6674-22-2",
    "酒石酸": "87-69-4",
    "2-碘酰基苯甲酸": "61717-82-6",
    "硼烷二甲硫醚": "13292-87-0",
    "三异丙基硅烷": "6485-79-6",
    "铁粉": "7439-89-6",
    "钯碳": "7440-05-3",
    "氢氧化钯碳": "12135-22-7",
    "雷尼镍": "7440-02-0",
    "铂碳": "7440-06-4",
    "二氯双(三苯基膦)钯": "13965-03-2",
    "1,10-邻菲罗啉": "66-71-7",
    "四丁基氟化铵": "429-41-4",
    "O-(7-氮杂苯并三唑-1-基)-N,N,N',N'-四甲基脲六氟磷酸盐": "148893-10-1",
    "N,N'-羰基二咪唑": "530-62-1",
    "二碳酸二叔丁酯": "24424-99-5",
    "氯甲酸苄酯": "501-53-1",
    "氯甲酸-9-芴基甲酯": "28920-43-6",
    "三甲基硅烷基三氟甲磺酸酯": "27607-77-8",
    "苄溴": "100-39-0",
    "苄氯": "100-44-7",
    "二氢吡喃": "110-87-2",
    "六甲基二硅氮烷": "999-97-3",
    "对氯苯甲醛": "104-88-1",
    "溴代苯": "108-86-1",
    "碘代苯": "591-50-4",
    "氯代苯": "108-90-7",
    "叠氮化钠": "26628-22-8",
    "二苯甲醇": "91-01-0",
    "异丙基氯化镁": "1068-55-9",
    "联硼酸频那醇酯": "73183-34-3",
    "二氯化镁": "7786-30-3",
    "氯化铵": "12125-02-9",
    "N-氯代丁二酰亚胺": "128-09-6",
    "偶氮二甲酸二乙酯": "1972-28-7",
    "三甲基碘硅烷": "16029-98-4",
    "劳森试剂": "19172-47-5",
    "氢溴酸": "10035-10-6",
    "三氟乙酸酐": "407-25-0",
    "三氟甲磺酸锂": "33454-82-9",
    "六氟异丙醇": "920-66-1",
    "N,N-二异丙基碳二亚胺": "693-13-0",
    "三氟甲磺酸乙酯": "425-75-2",
    "对甲基苄氯": "104-82-5",
    "对甲氧基苄氯": "824-94-2",
    "叔丁醇铝": "555-31-7",
}
# 别名补丁：指向词典里已有的条目
ALIAS_PATCH = {
    "铝锂氢": "氢化锂铝",
}
# 有些 CAS 对应的是混合物/异构体统称，PubChem 不认，退回按英文名查
NAME_FALLBACK = {
    "二甲苯": "m-xylene",
}
# 手工条目：PubChem 里没有对应的"混合物"条目，直接写死（数值取间二甲苯，最常用作溶剂）
MANUAL = [
    {"zh": "二甲苯", "alias": ["混合二甲苯", "xylenes"], "en": "Xylene", "cas": "1330-20-7",
     "formula": "C8H10", "cid": 7929, "mw": 106.168, "exact": None,
     "density": 0.864, "bp": "138–144 ℃", "hazard": None},
]
# 已作为别名并入其它条目的空壳，从 reagents 里删掉
DROP = ["铝锂氢"]

def gj(u, t=25):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))

def cas_ok(c):
    d = c.replace('-', '')
    if not (5 <= len(d) <= 10): return False
    return sum(int(x)*(i+1) for i, x in enumerate(reversed(d[:-1]))) % 10 == int(d[-1])

def parse_formula(f):
    return {e: (int(n) if n else 1) for e, n in re.findall(r'([A-Z][a-z]?)(\d*)', f) if e}

def mw_of(f):
    p = parse_formula(f)
    return sum(AW[e]*n for e, n in p.items()) if p else None

def exact_of(f):
    p = parse_formula(f)
    return sum(MM.get(e, AW[e])*n for e, n in p.items()) if p else None

def clean_formula(raw):
    m = re.match(r'^([A-Z][a-z]?\d*)+', str(raw or '').replace(' ', ''))
    return m.group(0) if m else None

def density_of(cid):
    try:
        d = gj(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=" + urllib.parse.quote("Density"))
    except Exception:
        return None
    raw = []
    def walk(o):
        if isinstance(o, dict):
            if o.get('TOCHeading') == 'Density':
                for inf in o.get('Information', []):
                    for s in inf.get('Value', {}).get('StringWithMarkup', []):
                        if s.get('String'): raw.append(s['String'])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d)
    cands = []
    for s in raw:
        for num, temp in re.findall(r'(\d\.\d+)\s*(?:g/(?:cu )?cm|g/mL)?[^;]{0,30}?(\d{1,3})\s*(?:°|deg)?\s*C', s):
            cands.append((float(num), int(temp)))
        for num in re.findall(r'(?<![\d.])(\d\.\d{2,4})(?![\d])', s):
            cands.append((float(num), None))
    for lo, hi in [(20, 25), (10, 35)]:
        g = [c for c in cands if c[1] is not None and lo <= c[1] <= hi and 0.1 < c[0] < 5]
        if g: return g[0][0]
    g = [c for c in cands if c[1] is None and 0.1 < c[0] < 5]
    return g[0][0] if g else None

def ghs_of(cid):
    try:
        d = gj(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=" + urllib.parse.quote("GHS Classification"))
    except Exception:
        return None
    texts, pics = [], set()
    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get('StringWithMarkup'), list):
                for s in o['StringWithMarkup']:
                    if not s: continue
                    if s.get('String'): texts.append(s['String'])
                    for mk in (s.get('Markup') or []):
                        if mk and mk.get('URL'): pics.add(mk['URL'])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d)
    blob = '\n'.join(texts)
    sig = 'Danger' if re.search(r'\bDanger\b', blob) else ('Warning' if re.search(r'\bWarning\b', blob) else None)
    hm = {}
    for m in re.finditer(r'\b(H\d{3}|EUH\d{3})\s*\((\d+(?:\.\d+)?)\s*%\)', blob):
        c, p = m.group(1), float(m.group(2))
        if c not in hm or hm[c] is None or p > hm[c]: hm[c] = p
    for m in re.finditer(r'\b(H\d{3}|EUH\d{3})\b', blob):
        hm.setdefault(m.group(1), None)
    pg = set()
    for u in pics:
        mm = re.search(r'GHS(\d{2})\.svg', u)
        if mm: pg.add('GHS' + mm.group(1))
    if not hm and not sig: return None
    order = sorted(hm.items(), key=lambda x: -(x[1] if x[1] is not None else -1))
    return {"signal": sig, "pict": sorted(pg), "h": [[k, v] for k, v in order]}

def main():
    # 始终从 dict.json 重新开始，保证可重复运行
    src = os.path.join(BUILD, 'dict.json')
    j = json.loads(io.open(src, 'r', encoding='utf-8').read())
    reagents = j.get('reagents') or []
    failed = j.get('failed') or []
    by_zh = {r.get('zh'): i for i, r in enumerate(reagents)}
    print(f'输入: dict.json  共 {len(reagents)} 条，其中缺 CAS 的 {sum(1 for r in reagents if not r.get("cas"))} 条')

    # 1) 别名补丁：把指向已有条目的名字加进它的 alias
    for alias, target in ALIAS_PATCH.items():
        idx = by_zh.get(target)
        if idx is not None:
            al = reagents[idx].setdefault('alias', [])
            if alias not in al: al.append(alias)
            print(f'别名补丁: {alias} -> {target}')

    # 2) CAS 补丁：★ 同名条目是"替换"不是"追加"（失败条目本身也在 reagents 里）
    patched, still = 0, []
    todo = [f for f in failed if f.get('zh') in PATCH]
    print(f'\n待补 {len(todo)} 条\n')
    for i, f in enumerate(todo, 1):
        zh = f['zh']
        cas = PATCH[zh]
        if not cas_ok(cas):
            print(f'  [{i:>2}] {zh:<26} CAS {cas} 校验位不通过，跳过')
            still.append(f); continue
        p = None
        try:
            p = gj("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/" + urllib.parse.quote(cas) +
                   "/property/MolecularFormula,Title/JSON")['PropertyTable']['Properties'][0]
        except Exception:
            alt = NAME_FALLBACK.get(zh)
            if alt:
                try:
                    p = gj("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/" + urllib.parse.quote(alt) +
                           "/property/MolecularFormula,Title/JSON")['PropertyTable']['Properties'][0]
                    print(f'  [{i:>2}] {zh:<26} CAS {cas} 查不到，改用英文名 "{alt}" 命中')
                except Exception:
                    p = None
        if p is None:
            print(f'  [{i:>2}] {zh:<26} CAS {cas} PubChem 查不到，跳过')
            still.append(f); continue
        cid = p.get('CID')
        formula = clean_formula(p.get('MolecularFormula'))
        title = p.get('Title')
        mw = mw_of(formula) if formula else None
        ex = exact_of(formula) if formula else None
        dens = density_of(cid)
        hz = ghs_of(cid)
        rec = {"zh": zh, "alias": [], "en": title, "cas": cas,
               "formula": formula, "cid": cid, "mw": round(mw, 3) if mw else None,
               "exact": round(ex, 4) if ex else None,
               "density": dens, "bp": None, "hazard": hz}
        idx = by_zh.get(zh)
        if idx is not None:
            reagents[idx] = rec          # 替换原来那条缺 CAS 的
        else:
            by_zh[zh] = len(reagents)
            reagents.append(rec)
        patched += 1
        print(f'  [{i:>2}] {zh:<26} CAS {cas}  {formula:<14} MW={rec["mw"]}  d={dens}  GHS={"Y" if hz else "-"}')
        time.sleep(0.2)

    # 3) 手工条目 + 删除已并入别名的空壳
    for rec in MANUAL:
        if rec.get("hazard") is None and rec.get("cid"):
            rec["hazard"] = ghs_of(rec["cid"])
        idx = by_zh.get(rec["zh"])
        if idx is not None: reagents[idx] = rec
        else:
            by_zh[rec["zh"]] = len(reagents); reagents.append(rec)
        print(f'  手工条目: {rec["zh"]} CAS={rec["cas"]} {rec["formula"]} GHS={"Y" if rec["hazard"] else "-"}')
    for name in DROP:
        if name in by_zh:
            reagents = [r for r in reagents if r.get("zh") != name]
            by_zh = {r.get("zh"): i for i, r in enumerate(reagents)}
            print(f'  删除空壳: {name}（已并入其它条目的别名）')

    j['reagents'] = reagents
    # 重新统计真正还缺 CAS 的
    missing = [{"zh": r.get("zh"), "reason": "无 CAS"} for r in reagents if not r.get("cas")]
    j['failed'] = missing
    j['count'] = len(reagents)
    j['patched'] = patched
    out = os.path.join(BUILD, 'dict.patched.json')
    io.open(out, 'w', encoding='utf-8').write(json.dumps(j, ensure_ascii=False, separators=(',', ':')))
    print(f'\n补入/替换 {patched} 条')
    print(f'合计 {len(reagents)} 条，仍缺 CAS {len(missing)} 条 -> {out}  ({os.path.getsize(out):,} B)')
    if missing:
        print('   仍缺:', '、'.join(x['zh'] for x in missing))

main()
