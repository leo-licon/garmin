// Service Worker — Garmin Sync Hub
const CACHE = 'garmin-sync-v1';
const STATIC = [
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/manifest.json',
];

// Instalar: cachea assets estáticos
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC))
  );
  self.skipWaiting();
});

// Activar: limpia caches viejos
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first para páginas, cache-first para estáticos
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Siempre red para las páginas HTML y la API
  if (e.request.mode === 'navigate' || url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request));
    return;
  }

  // Cache-first para CSS/JS/icons
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
