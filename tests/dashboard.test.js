const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function dashboard() {
    const context = vm.createContext({
        document: { addEventListener() {}, getElementById() { return null; },
                    body: { classList: { contains() { return false; } } } },
        window: {}, console: { log() {}, warn() {}, error() {}, debug() {} },
        setTimeout() {}, setInterval() {}, Date, Map,
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8'), context);
    return context;
}

test('quoted earthquake place names retain their CSV columns', () => {
    const page = dashboard();
    const result = page.parseCSV('place,magnitude,status\r\n"Coast, Japan",5.5,TP\r\n"A ""quoted"" place",6.1,TP\r\n');
    assert.equal(result[0].place, 'Coast, Japan');
    assert.equal(result[0].magnitude, '5.5');
    assert.equal(result[1].place, 'A "quoted" place');
});

test('pending, unknown and blank-magnitude forecasts are never confirmed matches', () => {
    const page = dashboard();
    for (const status of ['Pending', 'FP', 'Unknown', undefined]) {
        assert.equal(page.isConfirmedCorrelation({ status, earthquake_magnitude: 5.5 }), false);
    }
    assert.equal(page.isConfirmedCorrelation({ status: 'TP', earthquake_magnitude: '' }), false);
    assert.equal(page.isConfirmedCorrelation({ status: 'TP', earthquake_magnitude: 5.5 }), true);
    assert.equal(page.isConfirmedFalsePositive({ status: 'Pending', has_correlated_eq: false }), false);
});

test('aggregates preserve actual fallback dates and coverage provenance', async () => {
    const page = dashboard();
    page.fetch = async url => ({ ok: true, json: async () => url === 'data/stations.json' ? {
        stations: ['KAK'], available_dates: ['2026-04-11'], most_recent_date: '2026-04-11',
        last_updated: '2026-04-11T05:00:00Z',
    } : {
        date: '2026-04-11', stations: { KAK: { date: '2026-04-10' } },
        station_quality: { KAK: 'partial' }, earthquake_correlations: { KAK: [
            { status: 'Pending', earthquake_magnitude: '' },
        ] },
    } });
    const result = await page.loadData();
    assert.equal(result.station_dates.KAK, '2026-04-10');
    assert.equal(result.is_hybrid_aggregation, true);
    assert.equal(result.station_quality.KAK, 'partial');
    assert.equal(result.last_updated, '2026-04-11T05:00:00Z');
    const forecasts = await page.loadEarthquakeCorrelations('KAK', '2026-04-11');
    assert.equal(forecasts.length, 1);
    assert.equal(forecasts[0].status, 'Pending');
});

test('no anomalies renders N/A rather than a fabricated failure percentage', () => {
    const page = dashboard();
    let configuration;
    page.document.getElementById = () => ({});
    page.Chart = function (element, options) { configuration = options; };
    page.createDetectionRateChart(null);
    assert.equal(configuration.data.datasets[0].data.join(','), '0,0');
    let label;
    const context = { save() {}, restore() {}, fillText(value) { label = value; } };
    configuration.plugins[0].afterDraw({ ctx: context, data: configuration.data, chartArea: { left: 0, right: 100, top: 0, bottom: 100 } });
    assert.equal(label, 'N/A');
});

test('station charts preserve missing values and the recorded numerical scale', () => {
    const page = dashboard();
    assert.equal(JSON.stringify(page.recordedValues([1.428, null, 1.429, 'invalid'])), '[1.428,null,1.429,null]');
    assert.equal(page.stationHour('2026-10-17T11:29:59', 'Asia/Tokyo'), '20:30');
    assert.equal(page.stationHour('2026-10-17T11:29:59Z', 'Asia/Tokyo'), '20:30');
});

test('observatory labels are escaped before insertion into plot markup', () => {
    const page = dashboard();
    assert.equal(page.escapeText('<Station & "name">'), '&lt;Station &amp; &quot;name&quot;&gt;');
});

test('calendar dates and earthquake instants remain correct across viewer time zones', () => {
    const { execFileSync } = require('node:child_process');
    const script = `
        const fs = require('node:fs'), vm = require('node:vm');
        const page = vm.createContext({ document: { addEventListener() {} } });
        vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), page);
        console.log(JSON.stringify({ date: page.formatDate('2026-10-17'),
            naive: page.earthquakeTimes('2026-10-17 13:59:34.575', -92.8552),
            explicit: page.earthquakeTimes('2026-10-17T21:59:34.575+08:00', -92.8552) }));
    `;
    const results = ['Asia/Kuala_Lumpur', 'America/Los_Angeles'].map(TZ => JSON.parse(execFileSync(process.execPath, ['-e', script], {
        cwd: path.join(__dirname, '..'), env: { ...process.env, TZ }, encoding: 'utf8'
    })));
    assert.deepEqual(results[0], results[1]);
    assert.equal(results[0].date, 'Oct 17, 2026');
    assert.equal(results[0].naive.utc, '2026-10-17 13:59:34 UTC');
    assert.equal(results[0].naive.local, '2026-10-17 07:59:34 UTC-6');
    assert.deepEqual(results[0].naive, results[0].explicit);
});

test('unknown event counts remain unknown while a measured zero is preserved', () => {
    const page = dashboard();
    for (const value of [null, undefined, '', '0', -1, NaN, Infinity, 1.5]) {
        assert.equal(page.validEventCount(value), null);
    }
    assert.equal(page.validEventCount(0), 0);
    assert.equal(page.validEventCount(3), 3);
});

test('an obsolete aggregate cannot overwrite the current correlation cache', async () => {
    const page = dashboard();
    let current = true, release;
    const delayed = new Promise(resolve => { release = resolve; });
    page.fetch = async url => ({ ok: true, json: async () => url === 'data/stations.json' ? {
        stations: ['KAK'], available_dates: ['2026-10-17'], most_recent_date: '2026-10-17'
    } : delayed });
    const request = page.loadData('2026-10-17', () => current);
    await new Promise(resolve => setImmediate(resolve));
    current = false;
    page.window.earthquakeCorrelations = { HON: ['newer selection'] };
    release({ stations: { KAK: { date: '2026-10-17' } }, earthquake_correlations: { KAK: ['old selection'] } });
    assert.equal(await request, null);
    assert.deepEqual(page.window.earthquakeCorrelations, { HON: ['newer selection'] });
});

test('downloaded CSV preserves zero-valued fields and quotes text', async () => {
    const page = dashboard();
    let blob, clicked = false, revoked = false;
    const link = { setAttribute() {}, style: {}, click() { clicked = true; } };
    page.Blob = Blob;
    page.URL = { createObjectURL(value) { blob = value; return 'blob:csv'; }, revokeObjectURL() { revoked = true; } };
    page.document.createElement = () => link;
    page.document.body.appendChild = () => {};
    page.document.body.removeChild = () => {};
    vm.runInContext(`allStations = ['KAK']; isAggregatedDataLoaded = true; selectedDate = '2026-10-17';
        allStationsData = { KAK: { timestamps: ['a,"quoted" timestamp'], isAnomalous: [true],
            P: [0], nZ: [0], nG: [0], threshold: 0 } };`, page);
    await page.downloadAnomaliesCSV();
    assert.equal(clicked, true);
    assert.equal(revoked, true);
    assert.match(await blob.text(), /KAK,"a,""quoted"" timestamp",0,0,0,0$/);
});

test('concurrent reads share requests and refresh invalidates cached data', async () => {
    const page = dashboard();
    let calls = 0;
    page.fetch = async () => ({ok: true, json: async () => ({version: ++calls})});
    const first = await Promise.all([page.cachedData('test.json'), page.cachedData('test.json')]);
    assert.equal(calls, 1);
    assert.equal(first[0], first[1]);
    page.invalidateDataRequests();
    assert.equal((await page.cachedData('test.json')).version, 2);
});

test('failed requests are retried, cache is bounded and parallel reads preserve order', async () => {
    const page = dashboard();
    let fail = true;
    page.fetch = async () => ({ok: !fail, status: 503, json: async () => ({ok:true})});
    await assert.rejects(page.cachedData('retry.json'), /503/);
    fail = false;
    await page.cachedData('retry.json');
    for (let i = 0; i < 50; i++) await page.cachedData(`${i}.json`);
    assert.equal(vm.runInContext('dataRequests.size', page), 32);
    let active = 0, peak = 0;
    const values = await page.parallelMap([1,2,3,4,5,6], async value => {
        peak = Math.max(peak, ++active);
        await new Promise(resolve => setImmediate(resolve)); active--;
        return value * 2;
    }, 3);
    assert.equal(peak, 3);
    assert.deepEqual(Array.from(values), [2,4,6,8,10,12]);
});

test('observation completeness labels do not depend on SYM-H verification', () => {
    const page = dashboard();
    for (const symh_verified of [true, false, undefined]) {
        const observation = {data_quality:{status:'complete',symh_verified}};
        assert.equal(page.observationRecordLabel(observation), 'Complete observation');
        assert.equal(page.observationStatusText(observation), 'Complete observation · no anomaly recorded');
    }
    assert.equal(page.observationRecordLabel({data_quality:{status:'partial',symh_verified:true}}), 'Partial observation');
    assert.equal(page.observationRecordLabel({P:[1,2]}), 'Historical observation');
    assert.match(page.observationStatusText({P:[1,2]}), /coverage not recorded/);
    assert.doesNotMatch(page.observationStatusText({P:[1,2]}), /unverified|SYM-H/);
    assert.equal(page.observationRecordLabel(null), 'Unavailable');
});

test('threshold labels describe actual baseline coverage and preserve old snapshot provenance', () => {
    const page = dashboard();
    assert.equal(page.thresholdBaselineLabel({}), 'Recorded threshold · historical settings');
    assert.equal(page.thresholdBaselineLabel({baseline_window_days:14, baseline_historical_nights:13,
        baseline_includes_observation:true, baseline_samples:112}), '14-night threshold · 14/14 nights used · 112 quiet hours');
    assert.equal(page.thresholdBaselineLabel({baseline_window_days:14, baseline_historical_nights:2,
        baseline_includes_observation:true, baseline_samples:20}), '14-night threshold · 3/14 nights used · 20 quiet hours');
});

test('individual fallback retains previous-night dates, quality and rejects invalid spectra', async () => {
    const page = dashboard(), requests = [];
    const previous = {date:'2026-04-10', P:[1,2], nZ:[4,5], nG:[4,4], data_quality:{status:'partial'}};
    const invalid = {date:'2026-04-11', P:[.5,.5], nZ:[20,20], nG:[40,40]};
    page.fetch = async url => {
        requests.push(url);
        const result = url === 'data/KAK_2026-04-10.json' ? previous : url === 'data/BAD_2026-04-11.json' ? invalid : null;
        return {ok: Boolean(result), json: async () => result};
    };
    const data = await page.loadDataFallback('2026-04-11',{stations:['KAK','BAD','ABSENT']},['2026-04-11'],'2026-04-11');
    assert.equal(Object.keys(data.data).join(','),'KAK');
    assert.equal(data.station_dates.KAK,'2026-04-10');
    assert.equal(data.station_quality.KAK,'partial');
    assert.equal(data.station_quality.BAD,'invalid');
    assert.equal(data.station_quality.ABSENT,'missing');
    assert.equal(data.is_hybrid_aggregation,true);
    assert.ok(!requests.includes('data/BAD_2026-04-10.json'));
    assert.ok(!requests.some(url=>url.includes('2026-04-09')));
    assert.equal(page.stationResultUsable({P:[null]}),false);
    assert.equal(page.stationResultUsable({P:[1],data_quality:{status:'invalid'}}),false);
    assert.equal(page.stationResultUsable(previous),true);
});
