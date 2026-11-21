/* Optional app installation and consent-based open-dashboard observation alerts. */
(function () {
    'use strict';
    const base = new URL('./',document.baseURI);
    const key = `gempra:alerts:${base.pathname}`;
    let registration, installPrompt, polling = false;
    let state = {enabled:false,date:null,seen:[]};
    try { state = {...state,...JSON.parse(localStorage.getItem(key) || '{}')}; } catch (_) {}
    const status = message => { const el=document.getElementById('app-status'); if(el) el.textContent=message; };
    const persist = () => { try {localStorage.setItem(key,JSON.stringify(state));} catch (_) {} };
    function offline(cached) {
        const el=document.getElementById('offline-status');
        if(el) {el.hidden=!cached;el.textContent=cached ? 'Offline / cached observations — recorded dates are retained. Map tiles may be unavailable.' : '';}
        document.body.classList.toggle('offline-mode',cached);
    }
    function buttonState() {
        const button=document.getElementById('enable-alerts-btn');
        if(button) {button.textContent=state.enabled?'Disable alerts':'Enable alerts';button.setAttribute('aria-pressed',String(state.enabled));}
    }
    async function checkAlerts(seed=false) {
        if(polling || !state.enabled) return;
        polling=true;
        try {
            const response=await fetch(new URL('api/v1/status.json',base),{cache:'no-cache'});
            if(!response.ok) throw new Error(`HTTP ${response.status}`);
            if(response.headers.get('X-GEMPRA-Offline')==='1') {offline(true);return;}
            const snapshot=await response.json();
            if(!snapshot.latest_observation_date || !Array.isArray(snapshot.anomalies)) throw new Error('Status unavailable');
            if(state.date && snapshot.latest_observation_date < state.date) return;
            const seen=new Set(state.seen);
            const fresh=snapshot.anomalies.filter(item=>!seen.has(item.id));
            const newDate=Boolean(state.date && snapshot.latest_observation_date > state.date);
            if(!seed && state.date && (fresh.length || newDate) && registration && Notification.permission==='granted') {
                await registration.showNotification(fresh.length ? 'New geomagnetic anomaly observations' : 'New GEMPRA observations',{
                    body:fresh.length ? fresh.slice(0,5).map(item=>`${item.station} · ${item.observation_date || item.id.split('|')[1]}`).join('; ') + (fresh.length>5 ? `; +${fresh.length-5} more` : '') : `New observation date: ${snapshot.latest_observation_date}`,
                    icon:new URL('static/assets/gempra-icon-192.png',base).href,
                    badge:new URL('static/assets/gempra-favicon-32.png',base).href,
                    tag:`gempra-${snapshot.latest_observation_date}`,data:{url:base.href},
                });
            }
            state.date=snapshot.latest_observation_date;
            snapshot.anomalies.forEach(item=>seen.add(item.id));
            state.seen=Array.from(seen).slice(-500);persist();
            status('Alerts enabled · checks run while this dashboard is open.');
        } catch (_) {status('Alerts enabled · unable to check for updates right now.');}
        finally {polling=false;}
    }
    async function init() {
        const install=document.getElementById('install-app-btn');
        const alerts=document.getElementById('enable-alerts-btn');
        const installed=window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone;
        if(install) {install.hidden=Boolean(installed);install.addEventListener('click',async()=>{
            if(installPrompt) {await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;}
            else status('To install, use your browser’s Install app or Add to Home Screen menu.');
        });}
        window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;if(install) install.hidden=false;});
        window.addEventListener('appinstalled',()=>{if(install) install.hidden=true;status('GEMPRA installed. Alerts remain optional.');});
        offline(!navigator.onLine);
        window.addEventListener('offline',()=>offline(true));
        window.addEventListener('online',()=>{offline(false);checkAlerts();});
        if('serviceWorker' in navigator && window.isSecureContext) {
            navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='GEMPRA_CACHED_DATA') offline(true);});
            try {registration=await navigator.serviceWorker.register(new URL('service-worker.js',base),{scope:base.href,updateViaCache:'none'});}
            catch (_) {status('App installation is unavailable in this browser session. The dashboard remains available.');}
        }
        if(!('Notification' in window) || !registration) {
            state.enabled=false;persist();buttonState();
            if(alerts) {alerts.disabled=true;alerts.textContent='Alerts unavailable';}
            return;
        }
        if(Notification.permission==='denied') state.enabled=false;
        buttonState();
        alerts?.addEventListener('click',async()=>{
            try {
            if(state.enabled) {state.enabled=false;persist();buttonState();status('Alerts disabled.');return;}
            const permission=Notification.permission==='default' ? await Notification.requestPermission() : Notification.permission;
            if(permission!=='granted') {status('Alerts are blocked. You can change notification permission in browser settings.');return;}
            registration=await navigator.serviceWorker.ready;
            state.enabled=true;persist();buttonState();await checkAlerts(true);
            } catch (_) {status('Unable to enable alerts in this browser session.');}
        });
        if(state.enabled) await checkAlerts();
        setInterval(()=>checkAlerts(),300000);
        document.addEventListener('visibilitychange',()=>{if(!document.hidden) checkAlerts();});
    }
    window.GempraApp={checkAlerts};
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
    else init();
})();
