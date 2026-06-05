// Service worker for the Global Paper Research Assistant PWA.
// App shell is precached; navigations are network-first (fresh model/cap when
// online, cached shell when offline); static assets are stale-while-revalidate;
// live API calls always hit the network and are never cached.
const VERSION = 'v1';
const CACHE = 'papers-ai-' + VERSION;
const SHELL = [
  '/', '/static/styles.css', '/static/app.js', '/manifest.webmanifest',
  '/static/icon-192.png', '/static/icon-512.png', '/static/icon-maskable-512.png',
  '/static/apple-touch-icon.png', '/static/favicon.png',
];
const API = ['/build', '/status', '/ask', '/suggest', '/metrics'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.allSettled(SHELL.map(u => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                  // never touch writes
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // let cross-origin pass (Wikipedia etc.)
  if (API.includes(url.pathname)) return;            // live data: always network

  if (req.mode === 'navigate') {                     // pages: network-first
    e.respondWith(
      fetch(req)
        .then(r => { caches.open(CACHE).then(c => c.put('/', r.clone())); return r; })
        .catch(() => caches.match('/'))
    );
    return;
  }

  e.respondWith(                                      // assets: stale-while-revalidate
    caches.match(req).then(cached => {
      const net = fetch(req).then(r => {
        if (r && r.status === 200) caches.open(CACHE).then(c => c.put(req, r.clone()));
        return r;
      }).catch(() => cached);
      return cached || net;
    })
  );
});
