/* 投料计算器 Service Worker
   策略：
     页面导航      -> network-first（联网时永远拿最新版，断网时用缓存兜底）
     其它同源资源  -> cache-first
     外部接口      -> 一律放行，不拦截、不缓存

   ★ CACHE 必须带内容指纹。否则 sw.js 自身的字节没变时，浏览器不会重新安装
     Service Worker，cache-first 会让用户永远停在旧版本上（服务器改了也白改）。 */
const CACHE = 'clc-1325cdf983';
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
