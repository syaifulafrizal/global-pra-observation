/* Read-only deployment smoke check using the dates actually advertised by the site. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = (process.argv[2] || 'http://127.0.0.1:5002/').replace(/\/?$/, '/');
const output = path.resolve(process.argv[3] || 'output/dogfood/deployment-smoke');
fs.mkdirSync(output, {recursive: true});
const report = {site:base, testedAt:new Date().toISOString(), checks:[], errors:[], failedRequests:[]};
let browser;
async function main() {
    const bundled = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-win64/chrome-headless-shell.exe');
    browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || (fs.existsSync(bundled) ? bundled : undefined)});
    const context = await browser.newContext({viewport:{width:1536,height:1100}, timezoneId:'Asia/Kuala_Lumpur', ignoreHTTPSErrors:true});
    const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('response', response => {
        if (response.url().startsWith(base) && response.status() >= 400)
            report.failedRequests.push({url:response.url(),status:response.status()});
    });
    const response = await page.goto(base, {waitUntil:'networkidle',timeout:60000});
    assert.equal(response.status(),200);
    await page.waitForFunction(() => document.querySelectorAll('.station-marker').length && charts.magnitude);
    const metadata = await (await context.request.get(base+'data/stations.json')).json();
    assert.equal(metadata.most_recent_date,metadata.available_dates[0]);
    assert.equal(await page.locator('.station-marker').count(),metadata.stations.length);
    assert.match(await page.locator('.method-strip').innerText(),/14 nights/);
    const images = new Set();
    for (const day of metadata.available_dates) {
        const snapshotResponse = await context.request.get(base+`data/aggregated_${day}.json`);
        assert.equal(snapshotResponse.status(),200);
        const snapshot = await snapshotResponse.json();
        await page.evaluate(day => renderDashboard(day),day);
        for (const station of metadata.stations) {
            await page.evaluate(async station => {
                document.getElementById('station-selector').value = station;
                await renderStationPlot(station);
            },station);
            const result = snapshot.stations[station];
            if (!result) {
                assert.match(await page.locator('#selected-station-plot').innerText(),/unavailable/i);
                continue;
            }
            const values = await page.evaluate(() => ({P:stationCharts[0].data.datasets[0].data,
                nZ:stationCharts[1].data.datasets[0].data,nG:stationCharts[1].data.datasets[1].data}));
            assert.deepEqual(values.P,result.P); assert.deepEqual(values.nZ,result.nZ); assert.deepEqual(values.nG,result.nG);
            if (result.baseline_window_days === 14) {
                const nights = result.baseline_historical_nights + (result.baseline_includes_observation ? 1 : 0);
                assert.ok((await page.locator('.station-footnote').innerText()).includes(`${nights}/14 nights used`));
            }
            images.add(`figures/${station}/PRA_${station}_${result.date.replaceAll('-','')}.png`);
        }
        report.checks.push({date:day,stationSelections:metadata.stations.length,usable:Object.keys(snapshot.stations).length});
    }
    const entries = [...images];
    for (let i=0;i<entries.length;i+=8) await Promise.all(entries.slice(i,i+8).map(async name => {
        const response = await context.request.get(base+name);
        assert.equal(response.status(),200,name);
        assert.ok((await response.body()).subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])),name);
        await response.dispose();
    }));
    report.scientificFigures = entries.length;
    await page.evaluate(async day => {await renderDashboard(day);await renderStationPlot('KNY');},metadata.available_dates[0]);
    await page.locator('#station-selector').selectOption('KNY');
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    for (const width of [320,390,768,1024,1536]) {
        await page.setViewportSize({width,height:1000});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth+1),false,`${width}px overflow`);
        assert.ok((await page.locator('#map-container').boundingBox()).height >= (width <= 520 ? 380 : 460));
        if (width === 390) await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    }
    await page.locator('label.toggle-switch').click();
    assert.ok(await page.locator('#dark-mode-toggle').isChecked());
    await page.evaluate(() => {map.setView([35,140],4,{animate:false});});
    await page.evaluate(() => renderDashboard(selectedDate,{refresh:true}));
    assert.equal(await page.evaluate(() => map.getZoom()),4);
    assert.deepEqual(report.errors,[]);
    assert.deepEqual(report.failedRequests,[]);
    report.latestDate = metadata.most_recent_date;
    report.status = 'pass';
    await context.close();
}
main().catch(error => {report.status='fail';report.failure=error.stack;console.error(error);process.exitCode=1;})
    .finally(async () => {
        if(browser) await browser.close();
        fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));
        console.log(JSON.stringify({status:report.status,dates:report.checks.length,stationSelections:report.checks.reduce((sum,item)=>sum+item.stationSelections,0),figures:report.scientificFigures,errors:report.errors,failedRequests:report.failedRequests}));
    });
