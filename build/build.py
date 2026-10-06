import sys, os, io, re, json, datetime, hashlib
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

# 内容指纹：只跟 src / 词典有关（下面那行构建时间戳不算进来）。
# 用作 Service Worker 的缓存名 —— 源码没变时缓存名不变，不会让客户端白下载一遍。
content_ver = hashlib.md5(out.encode('utf-8')).hexdigest()[:10]

# 注释里写内容指纹而不是构建时间：源码没变时产物字节完全一致，
# 就不会因为「只是重新构建了一次」而凭空产生 diff。
out = out.replace('<title>投料计算器</title>',
                  '<title>投料计算器</title>\n<!-- 由 build.py 生成，内容指纹 ' + content_ver + ' -->')

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
   策略：
     页面导航      -> network-first（联网时永远拿最新版，断网时用缓存兜底）
     其它同源资源  -> cache-first
     外部接口      -> 一律放行，不拦截、不缓存

   ★ CACHE 必须带内容指纹。否则 sw.js 自身的字节没变时，浏览器不会重新安装
     Service Worker，cache-first 会让用户永远停在旧版本上（服务器改了也白改）。 */
const CACHE = 'clc-__VER__';
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

  // 页面导航：先走网络拿最新版，失败（断网 / 服务器挂）再回落到缓存
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then(res => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req).then(hit => hit || caches.match('./index.html')))
    );
    return;
  }

  // 图标 / manifest 这类静态资源：缓存优先
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
io.open(os.path.join(pwa_dir, 'sw.js'), 'w', encoding='utf-8', newline='\n').write(
    SW.replace('__VER__', content_ver))

print(f'\n--- PWA 部署包  {pwa_dir} ---')
for f in sorted(os.listdir(pwa_dir)):
    p = os.path.join(pwa_dir, f)
    if os.path.isfile(p):
        print(f'   {f:<24} {os.path.getsize(p):>9,} B')
