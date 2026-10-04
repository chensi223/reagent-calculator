# -*- coding: utf-8 -*-
"""读回 dict.json 做四项自检"""
import sys, os, json, re

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.path.join(HERE, 'dict.json')

raw_bytes = open(DICT, 'rb').read()
print('BOM 检测:', '有 BOM(!!)' if raw_bytes[:3] == b'\xef\xbb\xbf' else '无 BOM ✓')
doc = json.loads(raw_bytes.decode('utf-8'))
reagents = doc['reagents']
failed = doc['failed']

ok = True
print('\n=== 1. 结构自检 ===')
print('count 字段 = %d, 实际数组长度 = %d -> %s'
      % (doc['count'], len(reagents), '一致 ✓' if doc['count'] == len(reagents) else '不一致 ✗'))
if doc['count'] != len(reagents):
    ok = False

ORDER = {'zh', 'alias', 'en', 'cas', 'formula', 'cid', 'mw', 'exact', 'density', 'bp', 'hazard'}
bad_keys = [r['zh'] for r in reagents if set(r.keys()) != ORDER]
print('字段集异常条目: %d %s' % (len(bad_keys), bad_keys[:5]))

zhs = [r['zh'] for r in reagents]
dup = {z for z in zhs if zhs.count(z) > 1}
print('中文名重复: %d %s' % (len(dup), sorted(dup)[:5]))

# hazard 结构
hb = []
for r in reagents:
    hz = r['hazard']
    if hz is None:
        continue
    if set(hz.keys()) != {'signal', 'pict', 'h'}:
        hb.append((r['zh'], 'keys'))
        continue
    if hz['signal'] not in (None, 'Danger', 'Warning'):
        hb.append((r['zh'], 'signal=%r' % hz['signal']))
    for it in hz['h']:
        if not (isinstance(it, list) and len(it) == 2 and re.fullmatch(r'H\d{3}', it[0])):
            hb.append((r['zh'], 'h item %r' % (it,)))
    for g in hz['pict']:
        if not re.fullmatch(r'GHS\d{2}', g):
            hb.append((r['zh'], 'pict %r' % g))
print('hazard 结构异常: %d %s' % (len(hb), hb[:5]))
if hb:
    ok = False

# formula 规范
fb = [r['zh'] for r in reagents
      if r['formula'] and not re.fullmatch(r'(?:[A-Z][a-z]?\d*)+', r['formula'])]
print('分子式格式异常: %d %s' % (len(fb), fb[:5]))

# mw / exact 一致性
from fetch_lib import calc_mw, calc_exact, cas_ok   # noqa: E402
mwb = [r['zh'] for r in reagents
       if r['formula'] and r['formula'] in (None, '') ]
mwb = [r['zh'] for r in reagents if r['formula'] and r['mw'] is None]
print('有分子式但无分子量: %d %s' % (len(mwb), mwb[:8]))
rec_mw = [r['zh'] for r in reagents
          if r['formula'] and r['mw'] is not None
          and calc_mw(r['formula']) is not None
          and abs(calc_mw(r['formula']) - r['mw']) > 1e-9]
print('mw 与本地重算不符: %d %s' % (len(rec_mw), rec_mw[:5]))
if rec_mw:
    ok = False
# 元素表未收录导致的空值
nomw = [r['zh'] for r in reagents if r['formula'] and calc_mw(r['formula']) is None]
print('因元素不在原子量表内而 mw=null: %d %s' % (len(nomw), nomw))
noex = [r['zh'] for r in reagents if r['formula'] and calc_exact(r['formula']) is None]
print('因元素不在精确质量表内而 exact=null: %d %s' % (len(noex), noex[:12]))
rec_ex = [r['zh'] for r in reagents
          if r['formula'] and r['exact'] is not None
          and calc_exact(r['formula']) is not None
          and abs(calc_exact(r['formula']) - r['exact']) > 1e-9]
print('exact 与本地重算不符: %d %s' % (len(rec_ex), rec_ex[:5]))
if rec_ex:
    ok = False

# mw 兜底（无 formula 但有 mw）来源审查
fallback = [r for r in reagents if not r['formula'] and r['mw'] is not None]
print('\n无分子式但填了 mw（百科兜底）: %d 条' % len(fallback))
for r in fallback:
    print('  %-14s mw=%-9s cas=%s' % (r['zh'], r['mw'], r['cas']))

print('\n=== 2. CAS 校验位逐条复核 ===')
bad = []
n_cas = 0
for r in reagents:
    c = r['cas']
    if c is None:
        continue
    n_cas += 1
    if not re.fullmatch(r'\d{2,7}-\d{2}-\d', c) or not cas_ok(c):
        bad.append((r['zh'], c))
print('有 CAS 条目 %d 条, 校验位不通过 %d 条 %s'
      % (n_cas, len(bad), bad[:10]))
if bad:
    ok = False
else:
    print('全部通过 ✓')

print('\n=== 3. 已知答案抽查 ===')
checks = [
    ('苯甲醛',    '100-52-7',  'C7H6O',    106.124),
    ('甲醇',      '67-56-1',   'CH4O',     32.042),
    ('二氯甲烷',  '75-09-2',   'CH2Cl2',   84.927),
    ('正丁基锂',  '109-72-8',  'C4H9Li',   64.056),
    ('三氟乙酸',  '76-05-1',   'C2HF3O2',  114.023),
    ('四氢呋喃',  '109-99-9',  'C4H8O',    72.107),
    ('对甲苯磺酰氯', '98-59-9', 'C7H7ClO2S', 190.641),
    ('乙酸乙酯',  '141-78-6',  'C4H8O2',   88.106),
]
idx = {r['zh']: r for r in reagents}
allpass = True
for zh, cas, formula, mw in checks:
    r = idx.get(zh)
    if r is None:
        print('  %-12s 缺条目 ✗' % zh)
        allpass = False
        continue
    c_ok = (r['cas'] == cas)
    f_ok = (r['formula'] == formula)
    m_ok = (r['mw'] is not None and abs(r['mw'] - mw) <= 0.01)
    tag = '✓' if (c_ok and f_ok and m_ok) else '✗'
    if tag == '✗':
        allpass = False
    print('  %-12s %s cas=%-11s(期望 %-10s %s) formula=%-10s(期望 %-9s %s) mw=%-8s(期望 %.3f %s)'
          % (zh, tag, r['cas'], cas, 'ok' if c_ok else 'ERR',
             r['formula'], formula, 'ok' if f_ok else 'ERR',
             r['mw'], mw, 'ok' if m_ok else 'ERR'))
print('抽查结论: %s' % ('全部通过 ✓' if allpass else '存在不符 ✗'))
if not allpass:
    ok = False

print('\n=== 4. 错误字段抽查 ===')
for zh in ['苯甲醛', '四氢呋喃', '正丁基锂', '氢化钠', 'N-溴代丁二酰亚胺']:
    r = idx.get(zh)
    if not r:
        print('  %s 缺' % zh)
        continue
    hz = r['hazard']
    print('  %-14s signal=%s pict=%s h(前3)=%s'
          % (zh, (hz or {}).get('signal'), (hz or {}).get('pict'),
             ((hz or {}).get('h') or [])[:3]))

print('\n=== 总判定: %s ===' % ('通过' if ok else '有问题'))
print('dict 文件: %s  (%.1f KB)' % (DICT, os.path.getsize(DICT) / 1024))
print('失败条目 %d 条' % len(failed))
