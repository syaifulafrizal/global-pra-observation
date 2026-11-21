/* Browser integration: project-subpath scope, fresh API and labeled offline data. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=(process.argv[2] || 'http://127.0.0.1:5004/global-pra-observation/').replace(/\/?$/,'/');
const output=path.resolve(process.argv[3] || 'output/dogfood/pwa-smoke');
fs.mkdirSync(output,{recursive:true});
(async()=>{
    const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-win64/chrome-headless-shell.exe')});
    const context=await browser.newContext();
    await context.addInitScript(()=>{
        window.permissionPrompts=0;
        const original=Notification.requestPermission.bind(Notification);
        Notification.requestPermission=(...args)=>{window.permissionPrompts++;return original(...args);};
    });
    const page=await context.newPage(), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    try {
        await page.goto(base,{waitUntil:'networkidle'});
        const manifest=await (await context.request.get(base+'manifest.webmanifest')).json();
        assert.equal(manifest.start_url,'./');assert.equal(manifest.display,'standalone');
        await page.evaluate(()=>navigator.serviceWorker.ready);
        await page.waitForFunction(()=>navigator.serviceWorker.controller);
        const scope=await page.evaluate(async()=> (await navigator.serviceWorker.ready).scope);
        assert.equal(scope,base);
        const status=await (await context.request.get(base+'api/v1/status.json')).json();
        const latest=await (await context.request.get(base+'api/v1/latest.json')).json();
        const metadata=await (await context.request.get(base+'data/stations.json')).json();
        assert.equal(status.latest_observation_date,metadata.most_recent_date);
        const aggregate=await (await context.request.get(base+`data/aggregated_${metadata.most_recent_date}.json`)).json();
        assert.deepEqual(latest.stations,aggregate.stations);
        for(const icon of manifest.icons) {
            const response=await context.request.get(base+icon.src);
            assert.ok((await response.body()).subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
        }
        assert.equal(await page.evaluate(()=>window.permissionPrompts),0);
        await page.reload({waitUntil:'networkidle'});
        await page.waitForFunction(()=>Object.keys(allStationsData).length && charts.magnitude);
        const selected=await page.locator('#date-selector').inputValue();
        await context.setOffline(true);
        // Chromium's context offline emulation can leave worker networking online.
        await context.route(base+'**',route=>route.abort('internetdisconnected'));
        await page.reload({waitUntil:'domcontentloaded'});
        await page.waitForFunction(()=>Object.keys(allStationsData).length && charts.magnitude);
        await page.locator('#offline-status').waitFor({state:'visible'});
        assert.equal(await page.locator('#date-selector').inputValue(),selected);
        const cached=await page.evaluate(async()=>{
            const response=await fetch('api/v1/status.json');
            return {offline:response.headers.get('X-GEMPRA-Offline'),body:await response.json()};
        });
        assert.equal(cached.offline,'1');assert.deepEqual(cached.body,status);
        await page.screenshot({path:path.join(output,'offline.png'),fullPage:true});
        await context.setOffline(false);
        await context.unroute(base+'**');
        await page.reload({waitUntil:'networkidle'});
        await page.locator('#offline-status').waitFor({state:'hidden'});
        const online=await page.evaluate(async()=> (await fetch('api/v1/status.json')).headers.get('X-GEMPRA-Offline'));
        assert.equal(online,null);assert.deepEqual(errors,[]);
        const report={status:'pass',base,scope,latest:metadata.most_recent_date,offlineRetainedDate:selected,apiMatchesDashboard:true,permissionUnrequested:true,errors};
        fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));
        console.log(JSON.stringify(report));
    } catch(error) {
        console.error(await page.evaluate(async()=>({ready:document.readyState,onLine:navigator.onLine,
            app:typeof window.GempraApp,status:document.getElementById('offline-status')?.outerHTML,
            caches:await Promise.all((await caches.keys()).map(async name=>({name,keys:(await (await caches.open(name)).keys()).map(r=>r.url)})))})));
        throw error;
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
