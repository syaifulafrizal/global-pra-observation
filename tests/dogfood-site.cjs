/* Live, read-only browser dogfooding. Fault fixtures intercept only this browser. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.argv[2] || 'https://syaifulafrizal.github.io/global-pra-observation/';
const output = path.resolve(process.argv[3] || 'output/dogfood');
fs.mkdirSync(output, { recursive: true });
const results = [], browserErrors = [], networkFailures = [];
let browser, context, page, metadata;
const snapshots = {};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function check(name, operation, mode = 'live') {
    if (process.env.DOGFOOD_ONLY && !name.startsWith('Initial published') && !new RegExp(process.env.DOGFOOD_ONLY).test(name)) return;
    const started = Date.now();
    try {
        const evidence = await operation();
        results.push({ name, mode, status: 'pass', milliseconds: Date.now() - started, evidence });
        console.log('PASS', name);
    } catch (error) {
        results.push({ name, mode, status: 'fail', milliseconds: Date.now() - started, error: error.message });
        console.log('FAIL', name, error.message.slice(0, 220));
    }
}
async function ready(target = page) {
    await target.waitForFunction(() => document.querySelectorAll('.station-marker').length > 0 &&
        document.getElementById('station-ratio-chart') && charts.magnitude && Array.isArray(markers.earthquakes), null, { timeout: 25000 });
}
async function waitDate(date, target = page) {
    await target.waitForFunction(day => selectedDate === day && document.querySelector('.health-item:last-child .health-value')?.textContent === formatDate(day), date, { timeout: 15000 });
    await target.waitForTimeout(800);
}
async function tooltip(target, chartExpression) {
    await target.evaluate(expression => eval(expression).canvas.scrollIntoView({ block: 'center', behavior: 'instant' }), chartExpression);
    await target.waitForTimeout(300);
    const geometry = await target.evaluate(expression => {
        const chart = eval(expression);
        const point = chart.getDatasetMeta(0).data[0].getCenterPoint();
        const box = chart.canvas.getBoundingClientRect();
        return { x: box.left + point.x, y: box.top + point.y };
    }, chartExpression);
    await target.mouse.move(geometry.x, geometry.y);
    await target.waitForTimeout(150);
    return target.evaluate(expression => {
        const chart = eval(expression);
        return chart.tooltip?.dataPoints?.map(point => ({ label: point.label, raw: point.raw })) || [];
    }, chartExpression);
}
async function fixturePage(overrides = {}, options = {}) {
    const isolated = await browser.newContext({ viewport: options.viewport || { width: 1440, height: 1100 }, hasTouch: options.hasTouch || false,
        ignoreHTTPSErrors: true, timezoneId: options.timezoneId || 'Asia/Kuala_Lumpur', acceptDownloads: true });
    const target = await isolated.newPage();
    const errors = [];
    target.on('pageerror', error => errors.push(error.message));
    if (overrides.route) await overrides.route(target);
    if (overrides.snapshot) await target.route('**/data/aggregated_*.json', route => {
        const date = /aggregated_(.*?)\.json/.exec(new URL(route.request().url()).pathname)[1];
        const copy = structuredClone(snapshots[date] || snapshots[metadata.available_dates[0]]);
        overrides.snapshot(copy, date);
        return route.fulfill({ json: copy });
    });
    await target.goto(base, { waitUntil: 'networkidle', timeout: 60000 });
    return { target, isolated, errors };
}
async function main() {
    const bundledBrowser = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-win64/chrome-headless-shell.exe');
    const executablePath = process.env.CHROMIUM_EXECUTABLE_PATH || (fs.existsSync(bundledBrowser) ? bundledBrowser : undefined);
    browser = await chromium.launch({ headless: true, executablePath });
    context = await browser.newContext({ viewport: { width: 1536, height: 1100 },
        ignoreHTTPSErrors: true, acceptDownloads: true, timezoneId: 'Asia/Kuala_Lumpur' });
    await context.addInitScript(() => {
        const original = window.setInterval;
        window.__refreshHandlers = [];
        window.setInterval = function (callback, delay, ...arguments_) {
            if (delay === 300000) window.__refreshHandlers.push(callback);
            return original(callback, delay, ...arguments_);
        };
    });
    page = await context.newPage();
    page.on('pageerror', error => browserErrors.push(error.message));
    page.on('response', response => {
        if (response.url().startsWith(base) && response.status() >= 400)
            networkFailures.push({ url: response.url(), status: response.status() });
    });
    await check('Initial published page, logo, six charts and 51 station markers', async () => {
        const response = await page.goto(base, { waitUntil: 'networkidle', timeout: 60000 });
        assert.equal(response.status(), 200);
        await ready();
        metadata = await (await context.request.get(base + 'data/stations.json')).json();
        for (const day of metadata.available_dates)
            snapshots[day] = await (await context.request.get(base + `data/aggregated_${day}.json`)).json();
        assert.equal(await page.locator('.station-marker').count(), metadata.stations.length);
        assert.equal(await page.locator('canvas').count(), 6);
        assert.ok(await page.locator('.brand-emblem img').evaluate(image => image.complete && image.naturalWidth > 0));
        return { dates: metadata.available_dates, stations: metadata.stations.length };
    });
    await check('Station observation labels use completeness rather than SYM-H verification', async () => {
        assert.doesNotMatch(await page.locator('.method-strip').innerText(), /SYM-H/);
        assert.doesNotMatch(await page.locator('body').innerText(), /unverified/i);
        assert.doesNotMatch(await page.locator('#station-selector').innerText(), /unverified/i);
        const popupLabels = await page.evaluate(() => allStations.map(code=>markers[code].getPopup().getContent()).join('\n'));
        assert.doesNotMatch(popupLabels, /unverified/i);
        assert.doesNotMatch(await page.locator('#run-health').innerText(), /unverified|SYM-H/i);
        await page.locator('#station-selector').selectOption('KAK');
        assert.match(await page.locator('.observation-tag').innerText(), /Historical observation/);
        assert.doesNotMatch(await page.locator('#selected-station-plot').innerText(), /unverified|SYM-H/i);
        const fixture = await fixturePage({snapshot:data=>{
            data.stations.KAK.data_quality = {status:'complete',symh_verified:false};
            data.station_quality.KAK = 'complete';
            data.stations.HON.data_quality = {status:'partial',symh_verified:true};
            data.station_quality.HON = 'partial';
        }});
        try {
            await ready(fixture.target);
            await fixture.target.locator('#station-selector').selectOption('KAK');
            assert.equal(await fixture.target.locator('.observation-tag').innerText(),'Complete observation · no anomaly recorded');
            await fixture.target.locator('#station-selector').selectOption('HON');
            assert.equal(await fixture.target.locator('.observation-tag').innerText(),'Partial observation · no anomaly recorded');
            assert.match(await fixture.target.locator('#run-health').innerText(), /1 complete.*1 partial/s);
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'live and browser-only quality fixtures');
    for (const date of metadata.available_dates) {
        await check(`All 51 station selections and chart values on ${date}`, async () => {
            await page.locator('#date-selector').selectOption(date);
            await waitDate(date);
            const expected = snapshots[date];
            for (const station of metadata.stations) {
                await page.locator('#station-selector').selectOption(station);
                await page.waitForFunction(code => document.getElementById('selected-station-plot')?.textContent.includes(code), station);
                const result = expected.stations[station];
                if (!result) {
                    assert.match(await page.locator('#selected-station-plot').innerText(), /unavailable/i);
                    assert.equal(await page.locator('#station-ratio-chart').count(), 0);
                } else {
                    await page.waitForFunction(code => document.querySelector('.station-identity h3 b')?.textContent === code && stationCharts.length === 2, station);
                    const values = await page.evaluate(() => ({ P: stationCharts[0].data.datasets[0].data,
                        nZ: stationCharts[1].data.datasets[0].data, nG: stationCharts[1].data.datasets[1].data }));
                    assert.deepEqual(values.P, result.P);
                    assert.deepEqual(values.nZ, result.nZ);
                    assert.deepEqual(values.nG, result.nG);
                }
            }
            const categories = await page.evaluate(() => charts.distribution.data.datasets[0].data);
            assert.equal(categories.reduce((sum, value) => sum + value, 0), metadata.stations.length);
            return { tested: metadata.stations.length, usable: Object.keys(expected.stations).length };
        });
    }
    await page.locator('#date-selector').selectOption(metadata.available_dates[0]);
    await waitDate(metadata.available_dates[0]);
    await page.locator('#station-selector').selectOption('KAK');
    await check('Summary metrics, quality coverage and diagnostic charts match all five daily payloads', async () => {
        const history = await (await context.request.get(base + 'data/anomaly_history.json')).json();
        const falseNegatives = await (await context.request.get(base + 'data/false_negative_history.json')).json();
        const falsePositives = new Set((history.entries || []).filter(entry => entry.status === 'FP' && entry.has_correlated_eq !== true).map(entry => `${entry.station}_${entry.date}`)).size;
        for (const day of metadata.available_dates) {
            await page.locator('#date-selector').selectOption(day); await waitDate(day);
            const stats = await (await context.request.get(base + `data/earthquake_stats_${day}.json`)).json();
            const csv = await (await context.request.get(base + `data/recent_earthquakes_${day}.csv`)).text();
            const magnitudes = csv.trim().split(/\r?\n/).slice(1).map(row => Number(row.split(',')[4]));
            const bins = [0,0,0,0]; magnitudes.forEach(mag => { if (mag >= 5) bins[mag >= 8 ? 3 : Math.floor(mag) - 5]++; });
            const observed = await page.evaluate(() => ({ metrics: Array.from(document.querySelectorAll('.metric-card .value'), el => Number(el.textContent)),
                distribution: charts.distribution.data.datasets[0].data, magnitude: charts.magnitude.data.datasets[0].data,
                trend: charts.trend.data.datasets[0].data, success: charts.successRate.data.datasets[0].data,
                coverage: document.querySelector('.health-item .health-value').textContent }));
            const usable = Object.keys(snapshots[day].stations).length;
            assert.deepEqual(observed.metrics, [51, 0, stats.global_count, falsePositives, falseNegatives.entries.length]);
            assert.deepEqual(observed.distribution, [usable,0,0,51-usable]);
            assert.deepEqual(observed.magnitude, bins);
            assert.deepEqual(observed.success, [0,0]);
            assert.deepEqual(observed.trend, metadata.available_dates.filter(date => date <= day).slice(0,7).sort().map(date => Object.values(snapshots[date].stations).filter(station => station.date === date && station.is_anomalous).length));
            assert.match(observed.coverage, new RegExp(`${usable} / 51`));
        }
        await page.locator('#date-selector').selectOption(metadata.available_dates[0]); await waitDate(metadata.available_dates[0]);
        await page.locator('#station-selector').selectOption('KAK');
        return { dailyPayloads: 5, summaryCardsPerDate: 5, diagnosticsPerDate: 4 };
    });
    await check('Every original scientific-figure link returns an actual image', async () => {
        const figures = new Set();
        for (const data of Object.values(snapshots)) for (const [station, result] of Object.entries(data.stations))
            figures.add(`figures/${station}/PRA_${station}_${result.date.replaceAll('-', '')}.png`);
        const entries = Array.from(figures);
        const failed = [];
        for (let i = 0; i < entries.length; i += 8) await Promise.all(entries.slice(i, i + 8).map(async name => {
            const response = await context.request.get(base + name);
            if (response.status() !== 200 || !response.headers()['content-type']?.startsWith('image/')) failed.push(name);
            await response.dispose();
        }));
        assert.deepEqual(failed, []);
        return { images: figures.size };
    });
    await check('Original figure opens in a separate browser tab', async () => {
        const tabPromise = context.waitForEvent('page');
        await page.getByRole('link', { name: 'Original figure' }).click();
        const tab = await tabPromise;
        await tab.waitForLoadState('domcontentloaded');
        assert.match(tab.url(), /PRA_KAK_20261017\.png/);
        assert.equal(await tab.locator('img').count(), 1);
        await tab.close();
    });
    await check('Station marker click, popup details and 200 km hover radius', async () => {
        await page.locator('#map-container').scrollIntoViewIfNeeded();
        await page.evaluate(() => { map.closePopup(); map.setView(markers.KAK.getLatLng(), 10, { animate: false }); });
        const point = await page.evaluate(() => { const p = map.latLngToContainerPoint(markers.KAK.getLatLng()); const b = map.getContainer().getBoundingClientRect(); return {x:b.left+p.x,y:b.top+p.y-7}; });
        await page.mouse.move(point.x, point.y);
        assert.ok(await page.evaluate(() => Object.values(map._layers).some(layer => layer instanceof L.Circle && layer.getRadius() === 200000)));
        await page.mouse.click(point.x, point.y);
        await page.waitForSelector('.leaflet-popup-content');
        assert.match(await page.locator('.leaflet-popup-content').innerText(), /Kakioka|KAK/);
        await page.locator('.leaflet-popup-close-button').click();
        await page.mouse.move(10, 10);
    });
    await check('All station popup content reflects usable versus unavailable observations', async () => {
        const problems = await page.evaluate(() => allStations.flatMap(code => {
            const text = markers[code].getPopup().getContent();
            const usable = Boolean(allStationsData[code]);
            return !text.includes(code) || (!usable && !text.includes('Data unavailable or invalid')) ? [code] : [];
        }));
        assert.deepEqual(problems, []);
    });
    await check('Map zoom buttons, drag/pan and keyboard zoom', async () => {
        await page.evaluate(() => { map.closePopup(); map.getContainer().scrollIntoView({block:'center',behavior:'instant'}); map.setView([20,0], 2, {animate:false}); });
        const startZoom = await page.evaluate(() => map.getZoom());
        await page.locator('.leaflet-control-zoom-in').click();
        await page.waitForTimeout(350);
        assert.ok(await page.evaluate(() => map.getZoom()) > startZoom);
        await page.locator('.leaflet-control-zoom-out').click();
        await page.waitForTimeout(350);
        const before = await page.evaluate(() => map.getCenter().lng);
        const box = await page.locator('#map-container').boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down(); await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 20, { steps: 10 }); await page.mouse.up();
        await page.waitForTimeout(500);
        assert.notEqual(await page.evaluate(() => map.getCenter().lng), before);
        await page.locator('#map-container').focus();
        const old = await page.evaluate(() => map.getZoom()); await page.keyboard.press('+'); await page.waitForTimeout(350);
        assert.ok(await page.evaluate(() => map.getZoom()) > old);
    });
    await check('Earthquake popup, magnitude and radius lifecycle', async () => {
        await page.locator('#map-container').scrollIntoViewIfNeeded();
        await page.evaluate(() => { map.closePopup(); map.setView(markers.earthquakes[0].getLatLng(), 8, { animate: false }); });
        const location = await page.evaluate(() => { const p = map.latLngToContainerPoint(markers.earthquakes[0].getLatLng()); const b = map.getContainer().getBoundingClientRect(); return {x:b.left+p.x,y:b.top+p.y}; });
        await page.mouse.click(location.x, location.y);await page.waitForSelector('.leaflet-popup-content');
        const text = await page.locator('.leaflet-popup-content').innerText();
        assert.match(text, /Earthquake M5/);assert.match(text, /UTC/);
        await page.locator('.leaflet-popup-close-button').click();
        assert.equal(await page.evaluate(() => markers.earthquakeCircles.some(circle => map.hasLayer(circle))), false);
        return text;
    });
    await check('Chart hover tooltips expose the recorded numerical values', async () => {
        const stationTip = await tooltip(page, 'stationCharts[0]');
        assert.equal(stationTip[0].raw, snapshots[metadata.available_dates[0]].stations.KAK.P[0]);
        const magnitudeTip = await tooltip(page, 'charts.magnitude');
        assert.equal(typeof magnitudeTip[0]?.raw, 'number');
        return { station: stationTip, magnitude: magnitudeTip };
    });
    await check('Chart legend can hide and restore a station-status series', async () => {
        await page.evaluate(() => charts.distribution.canvas.scrollIntoView({block:'center',behavior:'instant'}));
        await page.waitForTimeout(300);
        const location = await page.evaluate(() => { const chart=charts.distribution, hit=chart.legend.legendHitBoxes[0], box=chart.canvas.getBoundingClientRect(); return {x:box.left+hit.left+hit.width/2,y:box.top+hit.top+hit.height/2}; });
        await page.mouse.click(location.x, location.y);
        await page.waitForTimeout(150);
        assert.equal(await page.evaluate(() => charts.distribution.getDataVisibility(0)), false);
        await page.mouse.click(location.x, location.y);
        await page.waitForTimeout(150);
        assert.equal(await page.evaluate(() => charts.distribution.getDataVisibility(0)), true);
    });
    await check('No-anomaly export displays a clear empty-state message', async () => {
        const dialogPromise = page.waitForEvent('dialog', { timeout: 25000 }).then(async dialog => {
            const message = dialog.message(); await dialog.accept(); return message;
        });
        const [message] = await Promise.all([dialogPromise, page.locator('#download-anomalies-btn').click()]);
        assert.equal(message, 'No anomalies found to download.');
    });
    await check('Anchor navigation, skip link and footer external links', async () => {
        for (const [name, hash] of [['Station network','#network'],['Methodology','#methodology'],['Overview','#overview']]) {
            await page.getByRole('link', { name, exact: true }).click();
            assert.equal(new URL(page.url()).hash, hash);
        }
        await page.reload({ waitUntil:'networkidle' });await ready();
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Skip to observations');
        await page.keyboard.press('Enter');assert.equal(new URL(page.url()).hash,'#overview');
        const links = await page.locator('.data-partners a').evaluateAll(links=>links.map(a=>({href:a.href,target:a.target,rel:a.rel})));
        assert.equal(links.length,3);assert.ok(links.every(link=>link.target==='_blank'&&link.rel.includes('noopener')));
        return links;
    });
    await check('Dark theme, persisted preference and reload', async () => {
        await page.locator('label.toggle-switch').click();
        assert.ok(await page.locator('body').evaluate(body=>body.classList.contains('dark-mode')));
        await page.reload({waitUntil:'networkidle'});await ready();
        assert.ok(await page.locator('#dark-mode-toggle').isChecked());
        assert.equal(await page.evaluate(()=>localStorage.getItem('darkMode')),'true');
        await page.screenshot({path:path.join(output,'live-dark.png'),fullPage:true});
        await page.locator('label.toggle-switch').click();
    });
    await check('Five-minute refresh callback preserves selected date and station', async () => {
        await page.locator('#date-selector').selectOption(metadata.available_dates[1]);await waitDate(metadata.available_dates[1]);
        await page.locator('#station-selector').selectOption('HON');
        await page.evaluate(()=>window.__refreshHandlers[0]());await ready();
        assert.equal(await page.locator('#date-selector').inputValue(),metadata.available_dates[1]);
        assert.equal(await page.locator('#station-selector').inputValue(),'HON');
        assert.equal(await page.locator('.station-marker').count(),51);
    });
    for (const width of [320,390,768,1024,1536]) await check(`Responsive layout and controls at ${width}px`, async () => {
        await page.setViewportSize({width,height:900});await page.waitForTimeout(250);
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
        assert.equal(overflow,false);
        assert.ok(await page.locator('#station-selector').isVisible());
        assert.ok(await page.locator('#date-selector').isVisible());
        assert.ok(await page.locator('#map-container').isVisible());
        if(width===390)await page.screenshot({path:path.join(output,'live-mobile.png'),fullPage:true});
    });
    await check('200% browser zoom equivalent keeps page controls reachable', async () => {
        await page.setViewportSize({width:768,height:550});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    });
    await page.setViewportSize({width:1536,height:1100});
    await page.screenshot({path:path.join(output,'live-desktop.png'),fullPage:true});
    await check('No uncaught JavaScript errors during ordinary user flows',async()=>assert.deepEqual(browserErrors,[]));

    // Browser-local fixtures exercise paths absent from the published zero-anomaly data.
    await check('Injected TP, FP, Pending and Unknown anomaly states',async()=>{
        const codes=['KAK','HON','ASP','API'];
        const fixture=await fixturePage({snapshot:(data,date)=>{
            codes.forEach((code,i)=>{
                const source=structuredClone(data.stations.KAK);
                source.station=code;source.date=date;source.is_anomalous=true;source.nAnomHours=1;
                source.isAnomalous=source.P.map((_,n)=>n===0);
                data.stations[code]=source;
                const status=['TP','FP','Pending','Unknown'][i];
                data.earthquake_correlations[code]=[{status,earthquake_magnitude:status==='TP'?5.5:null,days_after_anomaly:2,earthquake_distance_km:100}];
            });
        }});
        try{
            await ready(fixture.target);
            const colors=await fixture.target.evaluate(()=>['KAK','HON','ASP','API'].map(code=>markers[code].getElement().innerHTML));
            assert.match(colors[0],/eq-reliable/);assert.match(colors[1],/eq-false/);assert.match(colors[2],/gray/);assert.match(colors[3],/gray/);
            assert.doesNotMatch(await fixture.target.locator('body').innerText(), /unverified/i);
            const popupLabels = await fixture.target.evaluate(() => ['KAK','HON','ASP','API'].map(code=>markers[code].getPopup().getContent()).join('\n'));
            assert.doesNotMatch(popupLabels,/unverified/i);
            assert.equal(await fixture.target.evaluate(()=>charts.successRate.data.datasets[0].data[0]),25);
            for(const code of codes){await fixture.target.locator('#station-selector').selectOption(code);await fixture.target.waitForTimeout(70);}
            assert.deepEqual(fixture.errors,[]);
        }finally{await fixture.isolated.close();}
    },'browser-only fixture');
    await check('CSV export preserves zero-valued measurements',async()=>{
        const fixture=await fixturePage({snapshot:data=>{
            const result=data.stations.KAK;result.is_anomalous=true;result.nAnomHours=1;
            result.isAnomalous=result.P.map((_,i)=>i===0);result.P[0]=0;result.nZ[0]=0;result.nG[0]=0;result.threshold=0;
        }});
        try{
            await ready(fixture.target);
            const downloadPromise=fixture.target.waitForEvent('download');
            await fixture.target.locator('#download-anomalies-btn').click();
            const download=await downloadPromise;const destination=path.join(output,'fixture-anomalies.csv');await download.saveAs(destination);
            const rows=fs.readFileSync(destination,'utf8').split('\n');
            assert.match(download.suggestedFilename(),/^anomalies_.*\.csv$/);
            assert.ok(rows[1].endsWith(',0,0,0,0'),rows[1]);
        }finally{await fixture.isolated.close();}
    },'browser-only fixture');
    await check('Previous-night fallback remains visible and correctly dated',async()=>{
        const fixture=await fixturePage({snapshot:data=>{data.stations.KAK.date='2026-10-16';data.is_hybrid_aggregation=true;}});
        try{await ready(fixture.target);assert.match(await fixture.target.locator('#selected-station-plot').innerText(),/Showing 2026-10-16/);assert.ok(await fixture.target.locator('.fallback-notice').isVisible());}
        finally{await fixture.isolated.close();}
    },'browser-only fixture');
    await check('Individual-station fallback works when the aggregate is unavailable', async () => {
        const fixture = await fixturePage({route: target => target.route('**/data/aggregated_*.json', route => route.fulfill({status:404,body:'Unavailable'}))});
        try {
            await ready(fixture.target);
            const loaded = await fixture.target.evaluate(() => Object.keys(allStationsData).sort());
            assert.deepEqual(loaded, Object.keys(snapshots[metadata.available_dates[0]].stations).sort());
            await fixture.target.locator('#station-selector').selectOption('HON');
            await fixture.target.waitForFunction(() => document.querySelector('.station-identity h3 b')?.textContent === 'HON', null, {timeout:25000});
            assert.match(await fixture.target.locator('#selected-station-plot').innerText(), /Honolulu/);
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'browser-only fault injection');
    await check('Touch-enabled mobile station selection, map zoom, export access and theme toggle', async () => {
        const fixture = await fixturePage({}, {viewport:{width:390,height:844},hasTouch:true});
        try {
            await ready(fixture.target);
            await fixture.target.locator('#station-selector').selectOption('HON');
            assert.match(await fixture.target.locator('#selected-station-plot').innerText(), /Honolulu/);
            await fixture.target.evaluate(() => map.getContainer().scrollIntoView({block:'center',behavior:'instant'}));
            const before = await fixture.target.evaluate(() => map.getZoom());
            await fixture.target.locator('.leaflet-control-zoom-in').tap(); await pause(350);
            assert.ok(await fixture.target.evaluate(() => map.getZoom()) > before);
            assert.ok(await fixture.target.locator('#download-anomalies-btn').isVisible());
            await fixture.target.locator('label.toggle-switch').tap();
            assert.ok(await fixture.target.locator('#dark-mode-toggle').isChecked());
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'mobile browser emulation');
    await check('Rapid date switching keeps the most recent user selection',async()=>{
        const fixture=await fixturePage({route:async target=>{
            await target.route('**/data/aggregated_2026-10-16.json',async route=>{await pause(1400);await route.fulfill({json:snapshots['2026-10-16']});});
        }});
        try{
            await ready(fixture.target);
            await fixture.target.locator('#date-selector').selectOption('2026-10-16');await pause(50);
            await fixture.target.locator('#date-selector').selectOption('2026-10-15');await pause(3500);
            const state=await fixture.target.evaluate(()=>({selected:selectedDate,control:document.getElementById('date-selector').value,station:document.querySelector('.station-footnote').textContent}));
            await fixture.target.screenshot({path:path.join(output,'rapid-date-switch.png'),fullPage:true});
            assert.equal(state.control,'2026-10-15',JSON.stringify(state));
            assert.match(state.station,/2026-10-15/,JSON.stringify(state));
        }finally{await fixture.isolated.close();}
    },'browser-only fault injection');
    await check('Late statistics and chart responses cannot overwrite a newer date', async () => {
        for (const stage of ['statistics', 'trend', 'earthquakes']) {
            const fixture = await fixturePage();
            try {
                await ready(fixture.target);
                await fixture.target.evaluate(() => { if (typeof invalidateDataRequests === 'function') invalidateDataRequests(); });
                let notify, intercepted = false, earthquakeRequests = 0;
                const reached = new Promise(resolve => { notify = resolve; });
                const pattern = stage === 'statistics' ? '**/data/earthquake_stats_2026-10-16.json' : stage === 'trend' ? '**/data/aggregated_2026-10-13.json' : '**/data/recent_earthquakes_2026-10-16.csv';
                await fixture.target.route(pattern, async route => {
                    earthquakeRequests++;
                    if (!intercepted) {
                        intercepted = true; notify(); await pause(1400);
                    }
                    await route.continue();
                });
                await fixture.target.locator('#date-selector').selectOption('2026-10-16');
                await Promise.race([reached, pause(20000).then(() => { throw new Error(`Did not reach ${stage}`); })]);
                await fixture.target.locator('#date-selector').selectOption('2026-10-15');
                await waitDate('2026-10-15', fixture.target); await ready(fixture.target); await pause(1800);
                const state = await fixture.target.evaluate(() => ({ selected:selectedDate, control:document.getElementById('date-selector').value,
                    trend:charts.trend.data.labels.at(-1), station:document.querySelector('.station-footnote').textContent,
                    canvases:document.querySelectorAll('canvas').length, markers:document.querySelectorAll('.station-marker').length }));
                assert.equal(state.selected,'2026-10-15',stage); assert.equal(state.control,'2026-10-15',stage);
                assert.equal(state.trend,'Oct 15',stage); assert.match(state.station,/2026-10-15/,stage);
                assert.equal(state.canvases,6,stage); assert.equal(state.markers,51,stage);
                assert.deepEqual(fixture.errors,[],stage);
            } finally { await fixture.isolated.close(); }
        }
    }, 'browser-only fault injection');
    await check('Repeated refresh revalidates inputs and retains unchanged map, charts and markers', async () => {
        const fixture = await fixturePage();
        try {
            await ready(fixture.target);
            const observations = [];
            fixture.target.on('request', request => { if (request.url().includes('/data/stations.json')) observations.push(request.url()); });
            const state = await fixture.target.evaluate(async () => {
                const before = {map,charts:Object.values(charts),stationCharts:[...stationCharts],marker:markers.KAK};
                map.setView([35,140],4,{animate:false});
                for (let i=0;i<12;i++) await renderDashboard(selectedDate,{refresh:true});
                return {mapSame:map===before.map,chartsSame:Object.values(charts).every((chart,i)=>chart===before.charts[i]),
                    stationChartsSame:stationCharts.every((chart,i)=>chart===before.stationCharts[i]),markerSame:markers.KAK===before.marker,
                    zoom:map.getZoom(),lat:map.getCenter().lat,canvases:document.querySelectorAll('canvas').length,cacheSize:dataRequests.size};
            });
            assert.equal(state.mapSame,true); assert.equal(state.chartsSame,true); assert.equal(state.stationChartsSame,true);
            assert.equal(state.markerSame,true); assert.equal(state.zoom,4); assert.ok(Math.abs(state.lat-35)<1);
            assert.equal(state.canvases,6); assert.ok(state.cacheSize<=32); assert.equal(observations.length,12);
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'browser-only refresh simulation');
    await check('Changed refresh updates classifications while retaining map and chart instances', async () => {
        let changed = false;
        const fixture = await fixturePage({snapshot:data=>{
            if (changed) { const station=data.stations.KAK;station.is_anomalous=true;station.nAnomHours=1;station.isAnomalous=station.P.map((_,i)=>i===0); }
        }});
        try {
            await ready(fixture.target);
            await fixture.target.evaluate(()=>{window.__previousMap=map;window.__previousCharts=Object.values(charts);});
            changed=true;
            await fixture.target.evaluate(()=>renderDashboard(selectedDate,{refresh:true}));
            assert.equal(await fixture.target.locator('.metric-card .value').nth(1).innerText(),'1');
            assert.equal(await fixture.target.evaluate(()=>charts.successRate.data.datasets[0].data[1]),100);
            assert.equal(await fixture.target.evaluate(()=>map===window.__previousMap&&Object.values(charts).every((chart,i)=>chart===window.__previousCharts[i])),true);
            assert.match(await fixture.target.locator('.observation-tag').innerText(),/Anomaly/);
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'browser-only refresh simulation');
    await check('Refresh discovers a newly available date while preserving the selected night', async () => {
        let updated = false;
        const fixture = await fixturePage({route: target => target.route('**/data/stations.json', route => {
            const copy = structuredClone(metadata);
            if (updated) { copy.available_dates.unshift('2026-10-18'); copy.most_recent_date='2026-10-18'; }
            return route.fulfill({json:copy});
        })});
        try {
            await ready(fixture.target); updated = true;
            await fixture.target.evaluate(()=>renderDashboard(selectedDate,{refresh:true}));
            assert.equal(await fixture.target.locator('#date-selector').inputValue(),'2026-10-17');
            assert.equal(await fixture.target.locator('#date-selector option[value="2026-10-18"]').count(),1);
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'browser-only refresh simulation');
    await check('Rapid station switching preserves the last station selection', async () => {
        const fixture = await fixturePage();
        try {
            await ready(fixture.target);
            await fixture.target.evaluate(() => {
                const original = loadEarthquakeCorrelations;
                loadEarthquakeCorrelations = async (...args) => {
                    if (args[0] === 'KAK') await new Promise(resolve => setTimeout(resolve,1200));
                    return original(...args);
                };
            });
            await fixture.target.locator('#station-selector').selectOption('KAK'); await pause(50);
            await fixture.target.locator('#station-selector').selectOption('HON'); await pause(1600);
            assert.equal(await fixture.target.locator('.station-identity h3 b').innerText(),'HON');
            assert.equal(await fixture.target.locator('#station-selector').inputValue(),'HON');
            assert.deepEqual(fixture.errors,[]);
        } finally { await fixture.isolated.close(); }
    }, 'browser-only fault injection');
    await check('Unavailable earthquake statistics are not displayed as confirmed zero',async()=>{
        const fixture=await fixturePage({route:target=>target.route('**/data/earthquake_stats_*.json',route=>route.fulfill({status:503,body:'Unavailable'}))});
        try{await ready(fixture.target);const value=await fixture.target.locator('.metric-card').nth(2).innerText();await fixture.target.screenshot({path:path.join(output,'missing-earthquake-stats.png'),fullPage:true});assert.match(value,/unavailable|unknown|N\/A/i,value);}
        finally{await fixture.isolated.close();}
    },'browser-only fault injection');
    await check('Network failure after initial load clears or labels stale metrics',async()=>{
        const fixture=await fixturePage();
        try{
            await ready(fixture.target);
            await fixture.target.route('**/data/stations.json',route=>route.abort());
            await fixture.target.locator('#date-selector').selectOption('2026-10-16');await pause(1200);
            const summary=await fixture.target.locator('#summary-stats').innerText();
            const error=await fixture.target.locator('#map-container').innerText();
            assert.match(error,/No Data Available|error/i);
            assert.ok(!summary.trim() || /stale|unavailable|previous|failed/i.test(summary),'Previous metrics remain displayed without a stale-data label: '+summary.slice(0,160));
            assert.equal(await fixture.target.locator('#download-anomalies-btn').isDisabled(),true);
            assert.equal(await fixture.target.locator('#station-selector').isDisabled(),true);
            assert.equal(await fixture.target.evaluate(() => Object.keys(charts).length),0);
            assert.equal(await fixture.target.locator('#run-health').isVisible(),false);
            await fixture.target.unroute('**/data/stations.json');
            await fixture.target.locator('#date-selector').selectOption('2026-10-15');
            await waitDate('2026-10-15',fixture.target); await ready(fixture.target);
            assert.equal(await fixture.target.locator('#download-anomalies-btn').isEnabled(),true);
            assert.equal(await fixture.target.locator('#station-selector').isEnabled(),true);
            assert.deepEqual(fixture.errors,[]);
        }finally{await fixture.isolated.close();}
    },'browser-only fault injection');
    await check('No-data initial response presents a useful empty state',async()=>{
        const fixture=await fixturePage({route:target=>target.route('**/data/stations.json',route=>route.fulfill({status:503,body:'Unavailable'}))});
        try{assert.match(await fixture.target.locator('#map-container').innerText(),/No Data Available|error/i);assert.deepEqual(fixture.errors,[]);}
        finally{await fixture.isolated.close();}
    },'browser-only fault injection');
    await check('Dates remain calendar-correct for an American time zone',async()=>{
        const fixture=await fixturePage({}, {timezoneId:'America/Los_Angeles'});
        try{
            await ready(fixture.target);
            const labels=await fixture.target.evaluate(()=>({selected:selectedDate,date:formatDate(selectedDate),option:document.getElementById('date-selector').selectedOptions[0].textContent,trend:charts.trend.data.labels.at(-1)}));
            assert.match(labels.date,/Oct 17, 2026/,JSON.stringify(labels));
            assert.equal(labels.trend,'Oct 17');
        }finally{await fixture.isolated.close();}
    },'browser-only locale simulation');
    await check('Earthquake UTC times are independent of browser time zone',async()=>{
        const texts=[];
        for(const timezoneId of ['Asia/Kuala_Lumpur','America/Los_Angeles']){
            const fixture=await fixturePage({}, {timezoneId});
            try{await ready(fixture.target);texts.push(await fixture.target.evaluate(()=>markers.earthquakes[0].getPopup().getContent().match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC/)[0]));}
            finally{await fixture.isolated.close();}
        }
        assert.equal(texts[0],texts[1],JSON.stringify(texts));
        const source = await (await context.request.get(base + 'data/recent_earthquakes_2026-10-17.csv')).text();
        const firstTime = source.trim().split(/\r?\n/)[1].split(',')[0].slice(0,19).replace('T',' ') + ' UTC';
        assert.equal(texts[0],firstTime);
    },'browser-only locale simulation');
    await context.close();
}
main().catch(error=>{results.push({name:'Harness execution',status:'fail',error:error.stack});console.error(error);}).finally(async()=>{
    if(browser)await browser.close();
    const report={site:base,testedAt:new Date().toISOString(),results,browserErrors,networkFailures,
        counts:{passed:results.filter(r=>r.status==='pass').length,failed:results.filter(r=>r.status==='fail').length}};
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));
    console.log('RESULTS',JSON.stringify(report.counts));
    if (report.counts.failed) process.exitCode = 1;
});
