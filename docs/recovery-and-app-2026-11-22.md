# Download recovery and dashboard app — 22 November 2026

## Deployment and scientific impact

Deployment stays on the existing GitHub Pages site. The existing local Windows `GEMPRA` midnight task and workflow entry points remain in place. There is no Render/Cloudflare service, extra paid hosting, or server-side push service. Browser alerts are optional and check while the dashboard is open; they do not run the scientific analysis.

The numerical pipeline is preserved against source revision `1c85b462f`: all 24 existing functions outside `download_data`, `download_symh_data` and `process_station` have identical Python ASTs, including spectral estimation, quiet screening, EVT/k-sigma fitting, nZ guard, persistence, historical baseline selection, anomaly decisions and result saving. All analysis constants/options remain identical. The threshold still uses 13 previous nights plus the observation night. Missing SYM-H remains assumed quiet; covered hours retain disturbance screening. Earthquake integration and the Windows deployment/scheduler scripts are unchanged.

The three operational changes are:

- `intermagnet_hapi.py` and `download_data`: use INTERMAGNET's official HAPI adjusted/PT1S/Cartesian XYZ product in six-hour binary transfers, with bounded response sizes, read/transfer limits, retries, metadata validation, timestamp validation and atomic cache replacement. Preserve the legacy IAGA 0.01 nT precision. There is no switch to minute or reported data, interpolation, resampling, or fabricated observation. Existing valid raw files are reused. The original adjusted/second GIN download remains the bounded fallback; `INTERMAGNET_TRANSPORT=gin` selects the previous diagnostic path.
- `process_station`: distinguish the provider's explicit date-specific zero published samples/unknown observatory from exhausted transport failures. Genuine transport failures still fail the station. No-data outcomes retain the existing availability/valid-hour checks and actual observation dates. HAPI intervals are clipped to published availability, so partial days preserve gaps and are evaluated by the existing window checks.
- `download_symh_data`: memoize the same global OMNI UTC date-range query for this run, including an empty response, then return each station's original exact requested UTC slice as a copy. This avoids repeated waits against the delayed/unavailable index without changing its quiet assumption or the scientific method.

The previous daily GIN transfer reproduced resets/timeouts even after three retries. A complete KAK UTC day was recovered as 86,400 second samples; all 5,793 overlapping original GIN timestamps had exactly equal XYZ values. The overlapping full-hour P, nZ, nG and quiet outputs were bit-identical. This is a measured KAK comparison, not a claim that every station's full day was independently compared against both transports.

## PWA, API and presentation

- `templates/index.html`, `static/style.css`, `static/app.js`: larger readable labels, stronger contrast/focus states, touch targets, responsive analytics/API controls, and theme-aware chart/earthquake labels. Plotted P/nZ/nG values and classifications are preserved. The large map remains at least 500 px high on tablet/desktop and 380 px on mobile.
- `static/manifest.webmanifest`, app icons, `static/pwa.js`, `static/service-worker.js`: browser installation and scope-relative offline support for the existing project URL. The icons derive from the existing logo; the original asset is preserved. Leaflet 1.9.4 and Chart.js 4.4.0 are vendored at the same versions with licenses so the app can reopen without their CDNs.
- Data uses network-first requests. Cached responses show an offline/cached notice and retain recorded dates. Two caches are bounded to 32 entries each, at most 2 MiB per cached response. Map tiles and scientific image links may be unavailable offline. Cache loss/eviction does not alter source observations.
- Notifications ask permission only after a button click. Initial enablement seeds existing observations without sending historical alerts; subsequent date/station-night IDs are deduplicated. Cached status and older snapshots never trigger new alerts. Disabling alerts stops polling notifications. No background notification delivery is claimed.
- `public_api.py`, `app.py`, `upload_results.py`: read-only versioned JSON envelopes around the same published snapshots. Actual station fallback dates, quality metadata and numerical values are retained. Nonfinite API numbers serialize as JSON `null`, without editing source records. Local Flask rejects writes and sends CORS headers; Pages serves generated JSON files through the same deployment. Export/preview include the root manifest/service worker, API resources, vendor assets and normal PNG Git attributes. The publication gate checks required app assets, PNG signatures and API/dashboard latest-date agreement.

API paths relative to the existing site:

| GET resource | Content |
|---|---|
| `api/v1/index.json` | Catalog, provenance and available dates |
| `api/v1/status.json` | Latest published observation date and station-night anomaly IDs |
| `api/v1/stations.json` | Station metadata and available dates |
| `api/v1/latest.json` | Latest aggregate snapshot |
| `api/v1/observations/YYYY-MM-DD.json` | Advertised date's aggregate |
| `api/v1/stations/KAK/latest.json` | Latest available KAK record, preserving its actual date |
| `api/v1/stations/KAK/YYYY-MM-DD.json` | Available KAK record for that actual night |

There are no API credentials or private raw files added to this API. These are completed research observations, not earthquake predictions. Dates and API version remain explicit; updates follow the existing local publication cadence.

## Verification

- 66 Python tests and 18 JavaScript tests passed, covering transfer failure handling, partial published intervals, precision/fill values, numerical pipeline preservation, API read-only/provenance behavior, theme updates, notification permission/baseline/deduplication/disable and cached-status suppression.
- Both Windows workflow wrappers passed isolated no-input rehearsals. The registered task remains Ready with its existing midnight trigger; the next real trigger is not claimed to have executed.
- The independent visual checker tested 320, 390, 768, 1024 and 1536 px in both themes, including the expanded API. No overflow or uncaught browser errors; app/API controls measured 44 px; keyboard navigation/disclosure worked. Visible DOM text contrast checks reported zero violations. This is not a complete accessibility conformance audit of canvas/map content.
- Project-subpath PWA browser verification passed installation scope, icon signatures, API/dashboard equality, permission not requested on load, offline reload/date retention/cached labeling and online recovery, with no uncaught errors.
- Before importing any recovered observations, all 1,490 original result/context files matched SHA-256 hashes; all 1,122 original raw files retained their recorded sizes and modification timestamps. Recovery runs use an independent data copy so their retention cleanup cannot remove original data.

Detailed logs, preservation checks, browser reports and screenshots are retained under ignored `output/dogfood/network-2026-11-22/`, `output/dogfood/pwa-smoke/` and `output/playwright/visual-checker/`. Full recovery and publication outcomes are recorded after the final export gate.

## Full recovery

The independent full analysis completed with 18 successful stations, 42 no-data/no-usable-window outcomes and zero failed/error stations. Seventeen recovered nights have eight valid hours; NGK has three valid hours and retains its partial coverage. No recovered night was flagged anomalous. API and EYR have completed local November 22 nights; the other recovered nights are November 21. Actual historical baseline counts, including warmup, are retained.

Import added only 54 new JSON/CSV/figure artifacts and appended one row to each of 18 coverage ledgers. Existing raw measurements and earlier scientific result artifacts were not overwritten or deleted. The unchanged earthquake integration completed with exit 0 and no query warnings/errors in this run. Its seven daily global requests succeeded. Operational context/history snapshots and the export run reports were refreshed with original copies preserved in the evidence backup. The exporter’s existing cleanup removed older tracked generated web artifacts locally; those historical generated files were restored from their unchanged committed inputs before publication. The current reviewed deployment bundle was built separately.

The final recovered-data export passed the publication gate and all 357 station/date selections and 100 available scientific-figure links, with zero uncaught browser errors or failed site requests. Offline/date/API checks also passed against that export. The registered `GEMPRA` task remains Ready, next trigger November 23 at 00:00 local time. Its prior interrupted run is not represented as a successful scheduler execution.

See `recovery-validation-2026-11-22.json` for the scientific preservation and import summary.

## Publication verification

Functional source revision `6ebfcc26e8520f9949e5498bbe569df8f5702055` was published as Pages revision `477a9fd08c19aac97b8b0888563b114edc762e68` on the existing `gh-pages` branch. [GitHub's Pages build completed successfully](https://github.com/syaifulafrizal/global-pra-observation/actions/runs/44928874889).

All 16 hosted manifest hashes matched the reviewed bundle, including HTML, CSS, JavaScript, PWA assets, API status/latest and advertised aggregates. All 111 PNGs in the publication tree were validated as ordinary browser-readable Git blobs. The public-site sweep passed all 357 station/date selections and 100 figure links, five responsive widths, theme and refresh preservation, with zero uncaught errors or failed site requests. The public PWA check passed the actual `/global-pra-observation/` installation scope, icon signatures, API/dashboard equality, no permission prompt on load, offline date retention/cached labeling and online recovery.

The task is enabled and Ready, still invoking the same local `deploy_all.bat`. No analysis/integration recovery subprocess remains running. Main source and Pages publication were both pushed without changing the registered deployment target. Public screenshots and reports are in `output/dogfood/network-2026-11-22/public-browser/` and `public-pwa/`.
