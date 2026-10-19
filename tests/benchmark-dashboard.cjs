/* Compare the reviewed baseline UI with current UI against local Flask servers. */
const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const baseline = process.argv[2] || 'http://127.0.0.1:5000/';
const optimized = process.argv[3] || 'http://127.0.0.1:5001/';
const ref = process.argv[4] || '7946d3890';
const output = process.argv[5] || 'output/dogfood/optimization/browser-performance.json';
const median = values => [...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
(async () => {
    const bundled = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-win64/chrome-headless-shell.exe');
    const browser = await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || (fs.existsSync(bundled)?bundled:undefined)});
    const results = [];
    try {
        for (const [version,base] of [['baseline',baseline],['optimized',optimized]]) {
            const runs = [];
            for (let i=0;i<3;i++) {
                const context = await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1536,height:1100}});
                try {
                    const page = await context.newPage();
                    if (version==='baseline') {
                        await page.route(base,route=>route.fulfill({contentType:'text/html',body:execFileSync('git',['show',`${ref}:templates/index.html`])}));
                        await page.route(base+'static/app.js',route=>route.fulfill({contentType:'application/javascript',body:execFileSync('git',['show',`${ref}:static/app.js`])}));
                    }
                    let urls=[];
                    page.on('request',r=>{if(r.url().startsWith(base+'data/'))urls.push(r.url().slice(base.length));});
                    const ready = () => page.waitForFunction(() => typeof charts!=='undefined' && charts.magnitude &&
                        document.querySelectorAll('.station-marker').length===51 && Array.isArray(markers.earthquakes) &&
                        !document.getElementById('station-selector').disabled,null,{timeout:30000});
                    let start=Date.now(); await page.goto(base,{waitUntil:'domcontentloaded'});await ready();
                    const coldReadyMs=Date.now()-start, coldRequests=urls.length;
                    urls=[];start=Date.now();await page.locator('#date-selector').selectOption('2026-10-16');await ready();
                    const dateSwitchMs=Date.now()-start,dateSwitchRequests=urls.length;
                    urls=[];start=Date.now();await page.evaluate(()=>renderDashboard(selectedDate,{refresh:true}));await ready();
                    runs.push({coldReadyMs,dateSwitchMs,refreshMs:Date.now()-start,coldRequests,dateSwitchRequests,refreshRequests:urls.length});
                } finally {await context.close();}
            }
            const medians=Object.fromEntries(Object.keys(runs[0]).map(key=>[key,median(runs.map(run=>run[key]))]));
            results.push({version,site:base,runs,medians});
            console.log(version,JSON.stringify(medians));
        }
    } finally {await browser.close();}
    fs.mkdirSync(path.dirname(output),{recursive:true});
    fs.writeFileSync(output,JSON.stringify({baselineRef:ref,results,notes:'Three fresh contexts per version, no throttling. Network/CDN variability applies. Browser readiness includes charts and markers, not all map tiles.'},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
