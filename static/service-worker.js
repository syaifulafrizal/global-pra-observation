/* Scope-relative offline support; observation data always tries the network first. */
const SCOPE = self.registration.scope;
const PREFIX = `gempra:${new URL(SCOPE).pathname}:`;
const SHELL = `${PREFIX}shell:v1`;
const DATA = `${PREFIX}data:v1`;
const LIMIT = 32;
const local = name => new URL(name, SCOPE).href;
const SHELL_FILES = ['./', 'manifest.webmanifest', 'static/style.css', 'static/app.js', 'static/pwa.js',
    'static/vendor/leaflet/leaflet.js', 'static/vendor/leaflet/leaflet.css', 'static/vendor/chart/chart.umd.min.js',
    'static/assets/gempra-emblem-96.png', 'static/assets/gempra-favicon-32.png',
    'static/assets/gempra-icon-192.png', 'static/assets/gempra-icon-512.png', 'static/assets/gempra-maskable-512.png'];

self.addEventListener('install', event => event.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    await cache.addAll(SHELL_FILES.map(local));
    // Warm recorded observations even if the initial page loaded before activation.
    try {
        const response = await fetch(local('data/stations.json'),{cache:'no-cache'});
        if(response.ok) {
            await save(DATA,local('data/stations.json'),response);
            const metadata = await response.json();
            const dates = (metadata.available_dates || []).slice(0,7);
            const resources = ['api/v1/status.json',
                ...dates.map(day=>`data/aggregated_${day}.json`),
                ...dates.slice(0,1).flatMap(day=>[`data/earthquake_stats_${day}.json`,`data/recent_earthquakes_${day}.csv`])];
            await Promise.allSettled(resources.map(async name=>{
                const resource=await fetch(local(name),{cache:'no-cache'});
                await save(DATA,local(name),resource);
            }));
        }
    } catch (_) { /* The shell can still install during an upstream data outage. */ }
    await self.skipWaiting();
})()));

self.addEventListener('activate', event => event.waitUntil((async () => {
    for (const name of await caches.keys()) {
        if (name.startsWith(PREFIX) && ![SHELL, DATA].includes(name)) await caches.delete(name);
    }
    await self.clients.claim();
})()));

async function save(cacheName, request, response) {
    if (!response.ok || response.type === 'opaque') return;
    if ((await response.clone().arrayBuffer()).byteLength > 2 * 1024 * 1024) return;
    const cache = await caches.open(cacheName);
    await cache.put(request, response.clone());
    const keys = await cache.keys();
    for (const key of keys.slice(0, Math.max(0, keys.length - LIMIT))) await cache.delete(key);
}

async function offlineNotice(url) {
    for (const client of await self.clients.matchAll({type:'window',includeUncontrolled:true})) {
        if (client.url.startsWith(SCOPE)) client.postMessage({type:'GEMPRA_CACHED_DATA',url});
    }
}

async function networkFirst(request, isData) {
    const cacheName = isData ? DATA : SHELL;
    try {
        const response = await fetch(request);
        if (response.status >= 500) throw new Error(`Temporary HTTP ${response.status}`);
        try { await save(cacheName, request, response); } catch (_) { /* Storage eviction must not break live data. */ }
        return response;
    } catch (error) {
        const cache = await caches.open(cacheName);
        const cached = await cache.match(request) || (!isData && request.mode === 'navigate' ? await cache.match(local('./')) : null);
        if (!cached) return new Response('Offline resource unavailable', {status:503,headers:{'Content-Type':'text/plain'}});
        if (!isData) return cached;
        await offlineNotice(request.url);
        const headers = new Headers(cached.headers);
        headers.set('X-GEMPRA-Offline','1');
        headers.set('Cache-Control','no-store');
        return new Response(await cached.arrayBuffer(),{status:cached.status,statusText:cached.statusText,headers});
    }
}

self.addEventListener('fetch', event => {
    const request = event.request, url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin || !url.href.startsWith(SCOPE)) return;
    const relative = url.pathname.slice(new URL(SCOPE).pathname.length);
    const isData = relative.startsWith('data/') || relative.startsWith('api/v1/');
    const isShell = request.mode === 'navigate' || relative === 'manifest.webmanifest' ||
        relative.startsWith('static/') && !relative.endsWith('gempra-field-emblem.png');
    if (isData || isShell) event.respondWith(networkFirst(request,isData));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil((async () => {
        const requested = new URL(event.notification.data?.url || './',SCOPE);
        const target = requested.href.startsWith(SCOPE) ? requested.href : SCOPE;
        for (const client of await self.clients.matchAll({type:'window',includeUncontrolled:true})) {
            if (client.url.startsWith(SCOPE)) { await client.focus(); return; }
        }
        await self.clients.openWindow(target);
    })());
});
