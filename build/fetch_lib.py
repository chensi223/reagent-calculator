# -*- coding: utf-8 -*-
"""化学投料计算器 —— 内置试剂词典抓取共享库"""
import sys, re, json, time, urllib.parse, urllib.request

sys.stdout.reconfigure(encoding='utf-8')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

# ---------------------------------------------------------------- 原子量
AW = {
    'H': 1.008, 'He': 4.002602, 'Li': 6.94, 'B': 10.81, 'C': 12.011,
    'N': 14.007, 'O': 15.999, 'F': 18.998403163, 'Na': 22.98976928,
    'Mg': 24.305, 'Al': 26.9815385, 'Si': 28.085, 'P': 30.973761998,
    'S': 32.06, 'Cl': 35.45, 'K': 39.0983, 'Ca': 40.078, 'Ti': 47.867,
    'Cr': 51.9961, 'Mn': 54.938044, 'Fe': 55.845, 'Co': 58.933194,
    'Ni': 58.6934, 'Cu': 63.546, 'Zn': 65.38, 'Ga': 69.723, 'Ge': 72.630,
    'As': 74.921595, 'Se': 78.971, 'Br': 79.904, 'Rb': 85.4678,
    'Sr': 87.62, 'Zr': 91.224, 'Mo': 95.95, 'Ru': 101.07, 'Rh': 102.9055,
    'Pd': 106.42, 'Ag': 107.8682, 'Cd': 112.414, 'In': 114.818,
    'Sn': 118.71, 'Sb': 121.76, 'Te': 127.6, 'I': 126.90447,
    'Cs': 132.90545196, 'Ba': 137.327, 'La': 138.90547, 'Ce': 140.116,
    'W': 183.84, 'Pt': 195.084, 'Au': 196.966569, 'Hg': 200.592,
    'Pb': 207.2, 'Bi': 208.9804, 'U': 238.02891,
}
EM = {
    'H': 1.0078250319, 'Li': 7.016004, 'B': 11.0093055, 'C': 12.0,
    'N': 14.0030740052, 'O': 15.9949146221, 'F': 18.99840320,
    'Na': 22.98976928, 'Mg': 23.9850417, 'Al': 26.9815385,
    'Si': 27.9769265, 'P': 30.97376151, 'S': 31.97207069, 'Cl': 34.96885271,
    'K': 38.96370649, 'Ca': 39.9625909, 'Ti': 47.9479463, 'Cr': 51.9405062,
    'Mn': 54.938044, 'Fe': 55.9349363, 'Ni': 57.9353429, 'Cu': 62.9295975,
    'Zn': 63.9291422, 'Br': 78.9183376, 'Pd': 105.903486, 'Ag': 106.905097,
    'I': 126.904468, 'Cs': 132.90545196, 'Ba': 137.905247,
    'Pt': 194.9647911, 'Au': 196.966565, 'Hg': 201.970627,
    'Pb': 207.976652,
}

# ---------------------------------------------------------------- 清洗工具
def strip_tags(s):
    if s is None:
        return ''
    s = str(s)
    s = re.sub(r'<sup>.*?</sup>', '', s, flags=re.S)   # 引用上标连内容删掉
    s = re.sub(r'<[^>]+>', '', s)
    return s.replace('&nbsp;', ' ').strip()

CAS_LOOSE = re.compile(r'(\d{2,7}-\d{2}-\d)')   # 宽松匹配，不加负向前瞻

def cas_ok(c):
    d = c.replace('-', '')
    if not (5 <= len(d) <= 10):
        return False
    body, chk = d[:-1], int(d[-1])
    return sum(int(x) * (i + 1) for i, x in enumerate(reversed(body))) % 10 == chk

def extract_cas(raw):
    if not raw:
        return None
    s = strip_tags(raw)
    for c in CAS_LOOSE.findall(s):
        if cas_ok(c):
            return c
    return None

FORMULA_RE = re.compile(r'(?:[A-Z][a-z]?\d*)+')
def clean_formula(raw):
    if not raw:
        return None
    s = strip_tags(str(raw))
    m = FORMULA_RE.match(s)
    if not m:
        return None
    f = m.group(0)
    return f or None

_FF = re.compile(r'([A-Z][a-z]?)(\d*)')
def calc_mw(formula):
    if not formula:
        return None
    total = 0.0
    for el, n in _FF.findall(formula):
        if el not in AW:
            return None
        total += AW[el] * (int(n) if n else 1)
    return round(total, 3)

def calc_exact(formula):
    if not formula:
        return None
    total = 0.0
    for el, n in _FF.findall(formula):
        if el not in EM:
            return None
        total += EM[el] * (int(n) if n else 1)
    return round(total, 4)

DENS_RE = re.compile(r'([\d.]+)\s*g\s*/\s*(?:cm³|cm3|mL|ml)')
DENS_RE2 = re.compile(r'([\d.]+)\s*g\s*/\s*(?:cm|ml|mL)\b', re.I)

def extract_density(raw):
    if not raw:
        return None
    s = strip_tags(str(raw))
    for rx in (DENS_RE, DENS_RE2):
        m = rx.search(s)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None

MOLE_RE = re.compile(r'\d+(?:\.\d+)?')
def mole_from_baike_moleculenum(raw):
    if not raw:
        return None
    s = strip_tags(str(raw))
    # 百科“分子量”字段可能写成 106.12 或 106.12（...）
    m = MOLE_RE.search(s)
    if m:
        try:
            v = float(m.group(0))
            if 1 < v < 20000:
                return round(v, 3)
        except ValueError:
            pass
    return None

SPLIT_RE = re.compile(r'[、；;,，\s]+')
def split_alias(raw, zh):
    if not raw:
        return []
    s = strip_tags(str(raw))
    out = []
    for p in SPLIT_RE.split(s):
        p = p.strip()
        if not p or p == zh:
            continue
        if p not in out:
            out.append(p)
    return out

def clean_en(raw):
    if not raw:
        return None
    s = strip_tags(str(raw))
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'[\d\s,，、]+$', '', s).strip()   # 去掉尾部粘的引用数字
    return s or None

# ---------------------------------------------------------------- HTTP
def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def http_get_json(url, timeout=25):
    return json.loads(http_get(url, timeout))

# ---------------------------------------------------------------- 百度百科
BAIKE = ('https://baike.baidu.com/api/openapi/BaikeLemmaCardApi'
         '?scope=103&format=json&appid=379020&bk_key={}&bk_length=2000')

def baike_lookup(zh):
    """返回 (card_dict, raw_json) ; card_dict 为 字段名 -> 值字符串"""
    url = BAIKE.format(urllib.parse.quote(zh))
    obj = http_get_json(url)
    card = {}
    for it in (obj.get('card') or []):
        k = it.get('key')
        v = it.get('value')
        if isinstance(v, list):
            v = ' / '.join(str(x) for x in v)
        if k:
            card[k] = v
    return card, obj

# ---------------------------------------------------------------- PubChem
PUG_PROP = ('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/'
            'property/MolecularFormula,MolecularWeight/JSON')
PUG_GHS = ('https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{}/'
           'JSON?heading=GHS+Classification')

def pubchem_prop(cas):
    """返回 (cid, formula)"""
    url = PUG_PROP.format(urllib.parse.quote(cas))
    try:
        obj = http_get_json(url)
    except Exception:
        return None, None
    props = ((obj.get('PropertyTable') or {}).get('Properties') or [])
    if not props:
        return None, None
    p = props[0]
    cid = p.get('CID')
    formula = clean_formula(p.get('MolecularFormula'))
    return cid, formula

def _collect_strings(node, out):
    """收集 JSON 中所有字符串值（含 String 与 URL 键，象形图 URL 存在 URL 键里）"""
    if isinstance(node, dict):
        for v in node.values():
            if isinstance(v, str):
                out.append(v)
            else:
                _collect_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_strings(v, out)

H_PCT = re.compile(r'\b(H\d{3})\s*\((\d+(?:\.\d+)?)%\)')
H_PLAIN = re.compile(r'\b(H\d{3})\s*[:\[]')
GHS_URL = re.compile(r'/images/ghs/(GHS\d{2})\.svg')
DANGER = re.compile(r'\bDanger\b')
WARNING = re.compile(r'\bWarning\b')

def pubchem_ghs(cid):
    """CID -> hazard dict 或 None（无数据）"""
    if not cid:
        return None
    url = PUG_GHS.format(cid)
    try:
        obj = http_get_json(url)
    except Exception:
        return None
    strs = []
    _collect_strings(obj, strs)
    text = ' || '.join(strs)
    if not text:
        return None

    signal = 'Danger' if DANGER.search(text) else ('Warning' if WARNING.search(text) else None)

    hpct = {}
    for code, pct in H_PCT.findall(text):
        v = float(pct)
        if code not in hpct or (hpct[code] is None or v > hpct[code]):
            hpct[code] = v
    for code in H_PLAIN.findall(text):
        if code not in hpct:
            hpct[code] = None

    pict = []
    for g in GHS_URL.findall(text):
        if g not in pict:
            pict.append(g)
    pict.sort()

    if not hpct and not pict and not signal:
        return None

    h = sorted(hpct.items(), key=lambda kv: (kv[1] is None, -(kv[1] or 0), kv[0]))
    return {
        'signal': signal,
        'pict': pict,
        'h': [[c, p] for c, p in h],
    }

# ---------------------------------------------------------------- 单条处理
def process_one(zh):
    """返回 (reagent_dict_or_None, failed_dict_or_None)"""
    card, _raw = baike_lookup(zh)
    if card:
        cas = extract_cas(card.get('m38_CAS'))
    else:
        card = {}
        cas = None

    en = clean_en(card.get('m38_foreignName'))
    alias = split_alias(card.get('m38_othername'), zh)
    if en and en in alias:
        alias = [a for a in alias if a != en]
    density = extract_density(card.get('m38_density'))
    bp = strip_tags(card.get('m38_boilingpoint')) or None

    cid = None
    formula = None
    if cas:
        cid, formula = pubchem_prop(cas)

    mw = calc_mw(formula)
    exact = calc_exact(formula)
    if mw is None:
        mw = mole_from_baike_moleculenum(card.get('m38_moleculenum'))
    if exact is None and not formula:
        exact = None

    hazard = None
    if cid:
        hazard = pubchem_ghs(cid)

    rec = {
        'zh': zh,
        'alias': alias,
        'en': en,
        'cas': cas,
        'formula': formula,
        'cid': cid,
        'mw': mw,
        'exact': exact,
        'density': density,
        'bp': bp,
        'hazard': hazard,
    }
    if cas is None:
        reason = '百科无 CAS' if card else '百科无词条'
        return rec, {'zh': zh, 'reason': reason}
    return rec, None
