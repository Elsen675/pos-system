// Service worker: menyuya offline BAXIŞ üçün.
// Yalnız GET sorğuları və yalnız /r/ (menyu) və /media/ (şəkillər) keşlənir.
// Strategiya: əvvəl şəbəkə, alınmasa keş. Sifariş (POST) keşlənmir, internet tələb edir.
const CACHE = 'menu-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Panel bildirişinə toxunanda paneli ön plana gətir (və ya aç).
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      const panel = list.find((c) => new URL(c.url).pathname.startsWith('/panel/'));
      return panel ? panel.focus() : self.clients.openWindow('/panel/');
    })
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/r/') && !url.pathname.startsWith('/media/')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
