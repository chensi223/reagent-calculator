# -*- coding: utf-8 -*-
"""批处理：run_batch.py <start> <end>
对去重后的种子清单 [start, end) 区间处理，结果写入
  build/parts/prog_<start>_<end>.jsonl   逐条进度（断点续跑）
  build/parts/part_<start>_<end>.json    本批汇总
"""
import sys, os, re, json, time

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_lib import process_one   # noqa: E402

SEED = os.path.join(HERE, 'seed_list.txt')
PARTS = os.path.join(HERE, 'parts')
os.makedirs(PARTS, exist_ok=True)

start = int(sys.argv[1])
end = int(sys.argv[2])

# ---- 解析种子清单（跳过注释行，去重保序）
items = []
seen = set()
with open(SEED, 'r', encoding='utf-8') as f:
    for line in f:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s in seen:
            continue
        seen.add(s)
        items.append(s)

chunk = items[start:end]
prog_path = os.path.join(PARTS, 'prog_%d_%d.jsonl' % (start, end))
part_path = os.path.join(PARTS, 'part_%d_%d.json' % (start, end))

done = {}
if os.path.exists(prog_path):
    with open(prog_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            done[rec.get('zh')] = rec

print('批次 [%d, %d)  条目数 %d  已完成 %d' % (start, end, len(chunk), len(done)))
t0 = time.time()
pf = open(prog_path, 'a', encoding='utf-8')

for i, zh in enumerate(chunk, 1):
    if zh in done:
        continue
    try:
        rec, failed = process_one(zh)
    except Exception as e:
        rec = {
            'zh': zh, 'alias': [], 'en': None, 'cas': None, 'formula': None,
            'cid': None, 'mw': None, 'exact': None, 'density': None,
            'bp': None, 'hazard': None,
        }
        failed = {'zh': zh, 'reason': '抓取异常: %s' % type(e).__name__}
    rec['_failed'] = failed
    pf.write(json.dumps(rec, ensure_ascii=False) + '\n')
    pf.flush()
    done[zh] = rec
    print('  [%d/%d] %s cas=%s mw=%s dens=%s ghs=%s' % (
        i, len(chunk), zh, rec['cas'], rec['mw'], rec['density'],
        'Y' if rec['hazard'] else '-'))
    time.sleep(0.12)

pf.close()

reagents = []
failed = []
for zh in chunk:
    rec = done.get(zh)
    if rec is None:
        failed.append({'zh': zh, 'reason': '未处理'})
        continue
    f = rec.pop('_failed', None)
    if f:
        failed.append(f)
    reagents.append(rec)

with open(part_path, 'w', encoding='utf-8') as f:
    json.dump({'reagents': reagents, 'failed': failed}, f,
              ensure_ascii=False, indent=1)

print('批次完成: %d 条, 耗时 %.1f s -> %s' % (len(reagents), time.time() - t0, part_path))
