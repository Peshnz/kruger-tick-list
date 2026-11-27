// Offline shell: cache the app files; map tiles and stop data stay live.
const CACHE = 'sgt-v5';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('sgt-') && k !== CACHE && k !== CACHE + '-tiles').map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = e.request.url;
  if (e.request.method !== 'GET') return;                 // Overpass queries are POST: always live
  if (/tile\.openstreetmap|arcgisonline/.test(url)) {     // tiles: network first, keep a copy for offline
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone(); caches.open(CACHE + '-tiles').then(async c => { await c.put(e.request, copy); const k = await c.keys(); for (const x of k.slice(0, Math.max(0, k.length - 600))) c.delete(x); }); return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  // app shell: cache first, refresh in the background
  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(r => { if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); } return r; }).catch(() => hit);
    return hit || net;
  }));
});
