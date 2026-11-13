// 서비스 워커: 홈 화면에 추가했을 때 빠르게 뜨고, 인터넷이 끊겨도 마지막으로 본 화면은 보이게 한다.
// 항상 최신을 먼저 받고(네트워크 우선), 실패하면 저장해 둔 것을 쓴다.
const CACHE = 'gnbg-apt-v1';
const SHELL = ['./', 'index.html', 'css/app.css', 'js/app.js', 'js/core.js', 'manifest.webmanifest', 'icons/icon.svg'];

self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.hostname.includes('tile.openstreetmap.org')) return;   // 지도 타일은 저장하지 않는다
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok && (url.origin === location.origin || url.hostname === 'cdn.jsdelivr.net')) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then(hit => hit || (req.mode === 'navigate' ? caches.match('index.html') : Response.error())))
  );
});
