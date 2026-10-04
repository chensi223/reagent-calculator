# -*- coding: utf-8 -*-
"""合并 parts -> dict.json 并打印统计"""
import sys, os, json, datetime, re

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(HERE, 'parts')
OUT = os.path.join(HERE, 'dict.json')

BATCHES = [(0, 66), (66, 132), (132, 198), (198, 264), (264, 326)]

reagents = []
failed = []
for a, b in BATCHES:
    p = os.path.join(PARTS, 'part_%d_%d.json' % (a, b))
    with open(p, 'r', encoding='utf-8') as f:
        obj = json.load(f)
    reagents.extend(obj['reagents'])
    failed.extend(obj['failed'])

# 字段顺序规范化
ORDER = ['zh', 'alias', 'en', 'cas', 'formula', 'cid', 'mw', 'exact',
         'density', 'bp', 'hazard']
norm = []
for r in reagents:
    norm.append({k: r.get(k) for k in ORDER})

doc = {
    'version': '1.0',
    'generated': datetime.date.today().isoformat(),
    'count': len(norm),
    'reagents': norm,
    'failed': failed,
}
with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)

# ---------------- 统计 ----------------
n = len(norm)
def cnt(f):
    return sum(1 for r in norm if f(r))

cas_n = cnt(lambda r: r['cas'])
formula_n = cnt(lambda r: r['formula'])
mw_n = cnt(lambda r: r['mw'] is not None)
dens_n = cnt(lambda r: r['density'] is not None)
ghs_n = cnt(lambda r: r['hazard'])
alias_n = cnt(lambda r: r['alias'])
en_n = cnt(lambda r: r['en'])
exact_n = cnt(lambda r: r['exact'] is not None)
bp_n = cnt(lambda r: r['bp'])

print('=== 统计 ===')
print('输出: %s  (%.1f KB)' % (OUT, os.path.getsize(OUT) / 1024))
print('总条目数           : %d' % n)
print('有 CAS             : %d  (%.1f%%)' % (cas_n, cas_n * 100.0 / n))
print('有分子式           : %d  (%.1f%%)' % (formula_n, formula_n * 100.0 / n))
print('有分子量 mw        : %d  (%.1f%%)' % (mw_n, mw_n * 100.0 / n))
print('有精确质量 exact   : %d' % exact_n)
print('有密度 density     : %d  (%.1f%%)' % (dens_n, dens_n * 100.0 / n))
print('有沸点 bp          : %d' % bp_n)
print('有 GHS 危险数据    : %d  (%.1f%%)' % (ghs_n, ghs_n * 100.0 / n))
print('有别名 alias       : %d' % alias_n)
print('有英文名 en        : %d' % en_n)
print('有 CID             : %d' % cnt(lambda r: r['cid']))
print('失败条目数         : %d' % len(failed))
for f in failed:
    print('  - %s : %s' % (f['zh'], f['reason']))
