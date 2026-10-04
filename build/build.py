import sys, os, io, re, json, datetime
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
DIST = os.path.join(ROOT, 'dist')
os.makedirs(DIST, exist_ok=True)

def read(p):
    with io.open(p, 'r', encoding='utf-8') as f:
        return f.read()

tpl = read(os.path.join(SRC, 'index.html'))
css = read(os.path.join(SRC, 'styles.css'))
picto = read(os.path.join(SRC, 'pictograms.js'))
tables = read(os.path.join(SRC, 'tables.js'))
engine = read(os.path.join(SRC, 'engine.js'))
hazard = read(os.path.join(SRC, 'hazard.js'))
net = read(os.path.join(SRC, 'net.js'))
app = read(os.path.join(SRC, 'app.js'))
appui = read(os.path.join(SRC, 'app-ui.js'))

dict_path = os.path.join(ROOT, 'build', 'dict.patched.json')
if not os.path.exists(dict_path):
    dict_path = os.path.join(ROOT, 'build', 'dict.json')
if not os.path.exists(dict_path):
    dict_path = os.path.join(SRC, 'dict.json')
if not os.path.exists(dict_path):
    print('!! 找不到 dict.json，用空词典构建')
    dict_js = '{"version":"0","count":0,"reagents":[]}'
else:
    d = json.loads(read(dict_path))
    n = len(d.get('reagents') or [])
    print(f'dict.json: {n} 条试剂')
    dict_js = json.dumps(d, ensure_ascii=False, separators=(',', ':'))

def guard(s):
    # 防止脚本内容里出现 </script> 提前闭合
    return s.replace('</script', '<\\/script')

parts = {
    '/*__CSS__*/': css,
    '/*__PICTO__*/': picto,
    '/*__TABLES__*/': tables,
    '/*__DICT__*/': guard(dict_js),
    '/*__ENGINE__*/': guard(engine),
    '/*__HAZARD__*/': guard(hazard),
    '/*__NET__*/': guard(net),
    '/*__APP__*/': guard(app),
    '/*__APPUI__*/': guard(appui),
}
out = tpl
for k, v in parts.items():
    if k not in out:
        print('!! 模板缺少占位符 ' + k)
    out = out.replace(k, v)

stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
out = out.replace('<title>投料计算器</title>',
                  '<title>投料计算器</title>\n<!-- 由 build.py 生成于 ' + stamp + ' -->')

target = os.path.join(DIST, '投料计算器.html')
with io.open(target, 'w', encoding='utf-8', newline='\n') as f:
    f.write(out)

size = os.path.getsize(target)
print(f'\n=> {target}')
print(f'   {size:,} B  ({size/1024:.1f} KB)')
for name, s in [('CSS', css), ('象形图', picto), ('映射表', tables), ('词典', dict_js),
                ('引擎', engine), ('危险', hazard), ('查询', net), ('界面', app), ('交互', appui)]:
    print(f'   {name:<6} {len(s):>9,} 字符')

# ---------------- 生成 PWA 部署包 ----------------
pwa_dir = os.path.join(DIST, 'pwa')
os.makedirs(pwa_dir, exist_ok=True)
io.open(os.path.join(pwa_dir, 'index.html'), 'w', encoding='utf-8', newline='\n').write(out)

MANIFEST = {
    "name": "投料计算器",
    "short_name": "投料计算器",
    "description": "实验室反应投料量计算：输入中文名或 CAS 自动取分子量，填一部分数据自动补全整张投料表，并汇总危险提醒与淬灭提示。",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "any",
    "background_color": "#f4f6f8",
    "theme_color": "#1668c1",
    "lang": "zh-CN",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
    ]
}
io.open(os.path.join(pwa_dir, 'manifest.json'), 'w', encoding='utf-8', newline='\n').write(
    json.dumps(MANIFEST, ensure_ascii=False, indent=2))

SW = r'''/* 投料计算器 Service Worker
   策略：同源静态资源走 cache-first（离线可开），外部接口（PubChem / 百度百科）一律走网络不缓存。 */
const CACHE = 'clc-v1';
const ASSETS = ['./', './index.html', './manifest.json',
                './icon-192.png', './icon-512.png', './apple-touch-icon.png', './favicon.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;   // 外部 API：交给浏览器，不拦
  e.respondWith(
    caches.match(req).then(hit => {
      if (hit) return hit;
      return fetch(req).then(res => {
        if (res && res.status === 200 && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match('./index.html'));
    })
  );
});
'''
io.open(os.path.join(pwa_dir, 'sw.js'), 'w', encoding='utf-8', newline='\n').write(SW)

print(f'\n--- PWA 部署包  {pwa_dir} ---')
for f in sorted(os.listdir(pwa_dir)):
    p = os.path.join(pwa_dir, f)
    if os.path.isfile(p):
        print(f'   {f:<24} {os.path.getsize(p):>9,} B')
