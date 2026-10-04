# -*- coding: utf-8 -*-
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_lib import http_get_json, PUG_GHS   # noqa

obj = http_get_json(PUG_GHS.format(241))
raw = json.dumps(obj, ensure_ascii=False)
open(os.path.join(HERE, 'ghs_probe.json'), 'w', encoding='utf-8').write(raw)
print('总长度', len(raw))
import re
print('--- 含 ghs 的片段 ---')
for m in re.finditer(r'.{60}ghs.{60}', raw, re.I):
    print(repr(m.group(0)))
print('--- 含 Danger 的片段 ---')
for m in re.finditer(r'.{40}Danger.{40}', raw):
    print(repr(m.group(0)))
print('--- 含 % 的片段 ---')
for m in re.finditer(r'.{50}%\).{20}', raw):
    print(repr(m.group(0)))
