const cacheName = 'journal-cache-v1';
const assetsToCache = [
  '/',
  '/static/manifest.json',
  // ajoute ici tes fichiers CSS, JS, images à mettre en cache
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(cacheName).then(cache => cache.addAll(assetsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(resp => resp || fetch(event.request))
  );
});
