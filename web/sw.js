/* 分享助手 · Service Worker
   只做最小的离线壳缓存；数据接口一律走网络，保证内容永远是最新的。 */
const SHELL = 'sharemate-shell-v2';
const ASSETS = ['/', '/static/style.css', '/static/app.js', '/icon.svg', '/manifest.json'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).catch(() => {}));
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;                 // 上传等一律直连
  if (url.pathname.startsWith('/api/')) return;           // 接口不缓存
  if (url.pathname.startsWith('/f/') || url.pathname.startsWith('/zip')
      || url.pathname.startsWith('/thumb/')) return;      // 内容实时取

  if (ASSETS.includes(url.pathname)) {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(e.request);
        const cache = await caches.open(SHELL);
        cache.put(e.request, fresh.clone());
        return fresh;
      } catch (err) {
        const hit = await caches.match(e.request);
        return hit || Response.error();
      }
    })());
  }
});
