import sys, os, io, csv, json, re, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}
BUILD = os.path.dirname(os.path.abspath(__file__))
BASE = 'https://cdn.jsdelivr.net/gh/Huozqi/Reagent-Mass-Calculator@main/'

def dl(name):
    dst = os.path.join(BUILD, name)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f'{name}: 已存在 {os.path.getsize(dst):,} B')
        return dst
    with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=60) as r:
        b = r.read()
    io.open(dst, 'wb').write(b)
    print(f'{name}: 下载 {len(b):,} B')
    return dst

dbp = dl('reagents_db.csv')
dl('RMC.py')

# ---- 分析 CSV ----
raw = io.open(dbp, 'r', encoding='utf-8-sig', errors='replace').read()
rows = list(csv.DictReader(io.StringIO(raw)))
print(f'\n=== reagents_db.csv ===')
print(f'总行数 {len(rows):,}')
print('字段:', list(rows[0].keys()) if rows else '-')

def cnt(col, pred=lambda v: v and v.strip() and v.strip() != '-'):
    return sum(1 for r in rows if pred(r.get(col)))

print(f'有 CAS       {cnt("CAS"):,}')
print(f'有 Name      {cnt("Name"):,}')
print(f'有 SMILES    {cnt("SMILES"):,}')
print(f'有 Density   {cnt("Density"):,}')
print(f'有 MW        {cnt("MW"):,}')

# 与我词典的重合
d = json.loads(io.open(os.path.join(BUILD, 'dict.patched.json'), 'r', encoding='utf-8').read())
mine = {r['cas']: r for r in d['reagents'] if r.get('cas')}
db = {}
for r in rows:
    c = (r.get('CAS') or '').strip()
    if c and c != '-':
        db.setdefault(c, r)
print(f'\n我词典 {len(d["reagents"])} 条，其中带 CAS {len(mine)} 条')
print(f'CSV 唯一 CAS {len(db):,} 条')
inter = [c for c in mine if c in db]
print(f'★ 与我词典重合 {len(inter)} 条（占我词典 CAS 的 {len(inter)/max(len(mine),1)*100:.0f}%）')

# 重合条目里，CSV 有密度而我词典没有的
gain_d = [c for c in inter if (db[c].get('Density') or '').strip() not in ('', '-')
          and mine[c].get('density') is None]
print(f'★ 可从 CSV 补到密度的 {len(gain_d)} 条')
print('   示例:', [(mine[c]['zh'], db[c]['Density']) for c in gain_d[:8]])

# 密度差异对比
print('\n密度一致性抽查（我词典 vs CSV）：')
n_big = 0; n_cmp = 0
for c in inter:
    m = mine[c].get('density'); v = (db[c].get('Density') or '').strip()
    if m is None or v in ('', '-'): continue
    try: dv = float(v)
    except: continue
    if dv <= 0: continue
    n_cmp += 1
    diff = abs(m - dv) / dv
    if diff >= 0.03:
        n_big += 1
        if n_big <= 14:
            flag = '⚠ ' if diff < 0.10 else '✗ '
            print(f'   {flag}{mine[c]["zh"]:<12} 我={m:<9} CSV={dv:<9} 差 {diff*100:.1f}%')
print(f'   比对 {n_cmp} 条，差异 >3% 的 {n_big} 条')

# MW 交叉验证
print('\nMW 交叉验证（CSV 的 MW vs 我本地算的）：')
bad = 0; chk = 0
for c in inter[:400]:
    try: csvmw = float(db[c]['MW'])
    except: continue
    m = mine[c].get('mw')
    if m is None: continue
    chk += 1
    if abs(m - csvmw) > 0.05:
        bad += 1
        if bad <= 10:
            print(f'   差 {abs(m-csvmw):6.2f}  {mine[c]["zh"]:<14} 我={m:<10} CSV={csvmw}')
print(f'   比对 {chk} 条，偏差 >0.05 的 {bad} 条')
