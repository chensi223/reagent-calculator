# -*- coding: utf-8 -*-
"""
给 dict.patched.json 的试剂补 reactTags 字段（PubChem "Reactivity Alerts"）。

用法：
    python enrich_reactivity.py --batch 70      # 只处理 70 条，然后退出并保存

设计要点：
  * 幂等：已经有 reactTags 的不再请求；无标签的 CID 记进状态文件，重跑时跳过
    （否则「无标签」条目会永远排在最前面，导致死循环）。
  * 增量保存：每处理 60 条立即把整个 JSON + 状态文件写回磁盘。
  * 限流：429/503 等 4 秒重试，最多 4 次；仍失败则记为该条失败并继续下一条。
"""
import sys, os, io, json, re, time, urllib.request, urllib.parse, urllib.error, argparse

sys.stdout.reconfigure(encoding='utf-8')

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}
BUILD = os.path.dirname(os.path.abspath(__file__))
DICT_PATH = os.path.join(BUILD, 'dict.patched.json')
STATE_PATH = os.path.join(BUILD, 'reactivity_state.json')

SAVE_EVERY = 60          # 每处理多少条落一次盘
TIMEOUT = 25             # 单条请求超时（秒）
SLEEP = 0.35             # 请求间隔
MAX_ATTEMPTS = 2         # 同一 CID 最多尝试的「轮次」，超过则不再重试

# 必须与 src/tables.js 里的 REACTIVITY_TAG_RE 完全一致
TAG_RE = re.compile(
    r'^(water[\s-]?reactive|air[\s-]?reactive|moisture[\s-]?reactive|pyrophoric|self[\s-]?heating'
    r'|strong\s+(reducing|oxidizing)\s+agent|oxidizer|peroxidizable|polymerizable|self[\s-]?reactive'
    r'|heat[\s-]?reactive|light[\s-]?sensitive|shock[\s-]?sensitive|known\s+catalytic\s+activity'
    r'|incompatible\s+with)', re.I)


def http_json(url, timeout=TIMEOUT, retry=4):
    """返回解析后的 JSON；404 返回 None（该物质没有这个 heading，属正常情况）。"""
    last = None
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
            if e.code in (429, 503):
                time.sleep(4)
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def tags_of(cid):
    """返回标签列表（可能为空列表），或 None 表示 404 无此数据。"""
    url = ('https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/'
           + str(cid) + '/JSON?heading=' + urllib.parse.quote('Reactivity Alerts'))
    d = http_json(url)
    if not d:
        return None
    out = []

    def walk(o):
        if isinstance(o, dict):
            swm = o.get('StringWithMarkup')
            if isinstance(swm, list):
                for s in swm:
                    if isinstance(s, dict) and isinstance(s.get('String'), str):
                        x = s['String'].strip()
                        if x and len(x) <= 60 and TAG_RE.match(x) and x not in out:
                            out.append(x)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    return out


def save_dict(j):
    """原子写回，避免中途被 kill 造成文件损坏。"""
    tmp = DICT_PATH + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(j, ensure_ascii=False, separators=(',', ':')))
    os.replace(tmp, DICT_PATH)


def save_state(st):
    tmp = STATE_PATH + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def load_state():
    if os.path.exists(STATE_PATH):
        with io.open(STATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'noTags': [], 'attempts': {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', type=int, default=70, help='本次最多处理多少条')
    args = ap.parse_args()

    with io.open(DICT_PATH, 'r', encoding='utf-8') as f:
        j = json.loads(f.read())
    rs = j['reagents']
    st = load_state()
    no_tags = set(st.get('noTags', []))
    attempts = {int(k): v for k, v in st.get('attempts', {}).items()}

    def done(r):
        if r.get('reactTags'):
            return True
        cid = r.get('cid')
        if not cid:
            return True
        if cid in no_tags:
            return True
        if attempts.get(cid, 0) >= MAX_ATTEMPTS:
            return True
        return False

    todo = [r for r in rs if not done(r)]
    print('词典 %d 条 | 已有 cid 且无 reactTags 且未查过 = %d 条待处理' % (len(rs), len(todo)))
    if not todo:
        print('没有待处理条目。')
        return

    n = min(args.batch, len(todo))
    ok = none = fail = 0
    t0 = time.time()
    processed = 0

    for r in todo[:n]:
        cid = r['cid']
        try:
            t = tags_of(cid)
        except Exception as e:
            fail += 1
            attempts[cid] = attempts.get(cid, 0) + 1
            print('  [!] %s (CID %s) 失败: %s %s  第%d次' %
                  (r.get('zh'), cid, type(e).__name__, str(e)[:60], attempts[cid]), flush=True)
        else:
            if t:
                r['reactTags'] = t
                ok += 1
                print('  [%d] %s -> %s' % (processed + 1, r.get('zh'), '/'.join(t)), flush=True)
            else:
                none += 1
                no_tags.add(cid)

        processed += 1
        if processed % SAVE_EVERY == 0:
            j['reactivityEnriched'] = {'withTags': sum(1 for x in rs if x.get('reactTags')),
                                       'noTags': len(no_tags),
                                       'failedDistinct': sum(1 for v in attempts.values() if v)}
            save_dict(j)
            save_state({'noTags': sorted(no_tags),
                        'attempts': {str(k): v for k, v in attempts.items()}})
            print('  === 已保存（累计处理 %d 条，用时 %.0fs）===' % (processed, time.time() - t0), flush=True)
        time.sleep(SLEEP)

    j['reactivityEnriched'] = {'withTags': sum(1 for x in rs if x.get('reactTags')),
                               'noTags': len(no_tags),
                               'failedDistinct': sum(1 for v in attempts.values() if v)}
    save_dict(j)
    save_state({'noTags': sorted(no_tags),
                'attempts': {str(k): v for k, v in attempts.items()}})

    remaining = len([r for r in rs if not done(r)])
    print('本批：处理 %d 条 | 有标签 %d | 无标签 %d | 失败 %d | 用时 %.0fs' %
          (processed, ok, none, fail, time.time() - t0))
    print('剩余待处理 %d 条 | 文件 %s (%s B)' % (remaining, DICT_PATH, format(os.path.getsize(DICT_PATH), ',')))


main()
