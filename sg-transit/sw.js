// SG Transit service worker.
// App files and data: network first (so updates show straight away), saved copy when offline.
// Map tiles: network first, last 600 kept for offline. Overpass/data.gov.sg calls are never touched.
const CACHE = 'sgt-v6';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './data.json',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'];

self.addEventListener('install', e => {
  // cache: 'reload' skips the browser's HTTP cache, so a new version never saves an old page
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(SHELL.map(u =>
    fetch(new Request(u, {cache: 'reload'})).then(r => r.ok && c.put(u, r)).catch(() => {}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks
    .filter(k => k.startsWith('sgt-') && k !== CACHE && k !== CACHE + '-tiles')
    .map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

const save = (name, req, res, limit) => caches.open(name).then(async c => {
  await c.put(req, res);
  if (limit) { const k = await c.keys(); for (const x of k.slice(0, Math.max(0, k.length - limit))) c.delete(x); }
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const tile = /tile\.openstreetmap\.org|arcgisonline\.com/.test(url.hostname);
  const mine = url.origin === location.origin;
  const lib = url.hostname === 'cdnjs.cloudflare.com' || url.hostname.endsWith('googleapis.com') || url.hostname.endsWith('gstatic.com');
  if (!tile && !mine && !lib) return;
  e.respondWith(fetch(mine ? new Request(req, {cache: 'no-cache'}) : req).then(res => {
    if (res.ok || res.type === 'opaque') save(tile ? CACHE + '-tiles' : CACHE, req, res.clone(), tile ? 600 : 0);
    return res;
  }).catch(() => caches.match(req, {ignoreSearch: true})
    .then(hit => hit || (req.mode === 'navigate' ? caches.match('./index.html') : Response.error()))));
});
