const CACHE = 'altra-v8-14';
const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './sw.js',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (/^\/(api|file|lib|health|dashboard|admin|control)(\/|$)/.test(url.pathname) || e.request.headers.has('range')) return;
  // الصفحة نفسها: الشبكة أولاً حتى تصل التحديثات فوراً، ثم الذاكرة عند انقطاع الإنترنت
  if (e.request.mode === 'navigate' || /\.html$/.test(url.pathname)) {
    e.respondWith(
      fetch(e.request).then(res => {
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(c => c || caches.match('./index.html')))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(cached => {
      const net = fetch(e.request).then(res => {
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => cached || caches.match('./index.html'));
      return cached || net;
    })
  );
});
