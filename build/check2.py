# -*- coding: utf-8 -*-
"""补充检查：h 排序、en 清洗、alias 卫生、样例输出"""
import sys, os, json, re
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
doc = json.load(open(os.path.join(HERE, 'dict.json'), 'r', encoding='utf-8'))
R = doc['reagents']

print('=== h 数组排序检查（百分比降序、null 最后）===')
bad = []
for r in R:
    h = (r['hazard'] or {}).get('h') or []
    pcts = [x[1] for x in h]
    key = [(p is None, -(p or 0)) for p in pcts]
    if key != sorted(key):
        bad.append(r['zh'])
print('排序异常: %d %s' % (len(bad), bad[:5]))

print('\n=== en 清洗检查 ===')
tail_digit = [r['zh'] for r in R if r['en'] and re.search(r'\d$', r['en'])]
print('en 以数字结尾: %d %s' % (len(tail_digit), tail_digit[:8]))
sep = [r['en'] for r in R if r['en'] and re.search(r'[;；,，、]', r['en'])]
print('en 含分隔符(未分割, 规则未要求): %d 例:' % len(sep))
for s in sep[:6]:
    print('   ', s)

print('\n=== alias 卫生检查 ===')
b1 = [r['zh'] for r in R if r['zh'] in r['alias']]
b2 = [r['zh'] for r in R if len(r['alias']) != len(set(r['alias']))]
b3 = [r['zh'] for r in R if any(len(a) > 30 for a in r['alias'])]
print('alias 含自身: %d %s' % (len(b1), b1[:5]))
print('alias 内部重复: %d %s' % (len(b2), b2[:5]))
print('alias 超长(>30字): %d %s' % (len(b3), b3[:5]))
longs = [(r['zh'], a) for r in R for a in r['alias'] if len(a) > 20]
print('示例长别名:', longs[:5])

print('\n=== 样例条目 ===')
for zh in ['苯甲醛', '正丁基锂', '氢化钠', '石油醚', '四氧化锇']:
    for r in R:
        if r['zh'] == zh:
            print(json.dumps(r, ensure_ascii=False)[:600])
            print('---')
            break
