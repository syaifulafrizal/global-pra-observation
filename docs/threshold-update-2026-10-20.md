# Threshold and quiet-context update — 20 October 2026

Baseline source: `888cf9441ff87d99185a329c7fa157da0e3e9729`.

The requested window is **13 previous local observation nights + the observation night = 14 nights total**. It is a calendar window, not the latest 14 available records. Missing nights are not filled with older observations. Available quiet hourly P samples from that window determine the threshold; short histories use the available samples and record their actual coverage.

| Area | Prior version | This version | Impact |
| --- | --- | --- | --- |
| Threshold samples | Up to six previous nights; observation night excluded when history existed | Up to 13 previous nights, combined with observation-night quiet samples | Threshold values and resulting anomaly flags can change. Current-night outliers can influence their own threshold, as explicitly requested. |
| Missing or sparse SYM-H | Entire station skipped when empty; uncovered hours excluded otherwise | Assume quiet for uncovered hours; covered hours still use the existing disturbance fraction rule | More usable geomagnetic observations can be classified. Assumed quiet does not establish measured geomagnetic quiet. |
| Historical P eligibility | Required `symh_verified` | Uses stored `isQuiet`, including assumed-quiet decisions; invalid spectra still rejected | Newly assumed-quiet results can contribute on following days. No anomaly-absence proxy is introduced. |
| Local retention | JSON, CSV and figures used the same seven-day cutoff | JSON retained for at least 14 inclusive nights; CSV and figure cutoff unchanged | Small increase in JSON storage; enough history survives for subsequent threshold calculations. |
| Provider availability | Unknown INTERMAGNET observatories made the whole batch fail before export | The specific HTTP 400 “Unable to find observatory” response leaves that station unavailable and allows the remaining observations to export; genuine transport/server failures still fail | Required operational fix exposed by the first live run; no synthetic raw measurements or classifications are created. |
| Results | Analysis version 2 | Version 3, configured window, historical nights, current-night inclusion, sample count, quiet policy and covered/assumed hours | The calculation and assumptions can be traced per observation. |
| Dashboard | No threshold window explanation; smaller map | Explains 13 + current, shows actual contributing nights/quiet hours per new result; wider/taller responsive map | Older results retain their recorded thresholds and historical-settings label. |
| Export resilience | Individual-file loading omitted previous-night fallback; optional summaries could be absent | Match aggregate fallback dates/validity; export unavailable summaries with null counts | Missing context displays N/A without normal-use 404s. Fallback notices span both layout columns. |

EVT GPD fitting, the tail quantile, false-positive target, minimum tail count and k-sigma formula are unchanged. With the existing eight hourly samples per night and at most 112 samples over 14 nights, the upper quartile has fewer than the required 30 tail samples; the existing k-sigma fallback will normally apply. This update does not lower that EVT requirement.

Multitaper/FFT normalization, frequency band, hour windows, fill-value handling, nZ guard and its separate six-previous-night calibration, persistence settings, earthquake matching distance/time rules, and conservative earthquake-coverage accounting are unchanged. Assumed-quiet observations still do not claim measured SYM-H coverage in the earthquake coverage ledger. This is completed-night observation analysis; forward earthquake matching evaluates later events.

Existing observations are not force-rerun or rewritten. First new runs may use fewer than 14 nights because the previous retention policy and upstream availability limited the history. The dashboard reports the actual baseline rather than claiming complete coverage.

## Validation

- `python -B -m unittest discover -s tests -q`: 40 tests passed, including exact 13-night boundaries, calendar gaps, invalid records, quiet-policy behavior, EVT inputs, threshold values/anomaly flags, retention, provider availability, optional-context export, and an eight-hour missing-SYM-H run using 13 previous nights.
- `node --test tests/dashboard.test.js`: 15 tests passed, including new/partial baseline labels, historical snapshot provenance, and individual-file fallback validity/dates.
- `python -B verify_threshold_update.py --output docs/threshold-validation-2026-10-20.json`: preserved 10 scientific functions, two aggregate/date-discovery functions, and eight integration/scheduler/publication-gate files against the baseline revision.
- `python -B verify_scheduler.py`: both Windows workflow wrappers completed the expected stages in isolated fixtures. This checks stage order and exit handling; it does not claim that fixture execution is a live scheduled run.
- Registered Windows task `GEMPRA` remains at midnight with the same action. At inspection, its last run was 20 October 00:00:01, result 0; next run was 21 October 00:00.

The older `verify_optimization.py` report describes equivalence for the earlier performance-only change. It is not a claim of threshold equivalence for this deliberate scientific-policy change. Use the new impact checks and regression tests for this version.

## Real-data run and preservation

Processing and the unchanged earthquake integration first ran in an independent temporary copy. The corrected full station batch and integration both exited 0. The actual daily exporter and publication validator then passed in that copy and in the local workspace.

- Added 18 station-night observations: 16 dated 19 October and two dated 20 October, with 14 complete and four partial observations in total. No anomalies were identified. Every threshold, contributing-sample count, method, and hourly anomaly flag was independently recomputed from its recorded samples and checked.
- Each new baseline uses five available previous nights plus the observation night: **6/14 nights used**. The dashboard states this explicitly. No unavailable older nights were fabricated or substituted.
- All 2,710 protected files were unchanged before importing validated outputs. After import, all **834 original station result JSON/CSV/figure artifacts and 129 original raw files** still matched their original hashes. No files were deleted in the local workspace.
- Import added 77 files and refreshed ten operational/context files. Originals of refreshed files and the previous generated web output were backed up under `C:\Users\SYAIFUL\AppData\Local\Temp\gempra-before-14-night-publish-9ettdf4i`.
- The unchanged earthquake integration refreshed one existing API correlation row from Unknown to TP after fetching the March 22 M6.2 event (185.13 km, 12.02 days after detection). This is a data refresh by the existing matching method, not a change to its rules. The CSV retained four rows and the same columns.
- KNY, MMB and SJG operational false-negative CSVs each changed from one row to zero under the existing coverage-aware integration. Their output schema now includes the already-supported `earthquake_id` and `coverage_verified` columns. The cumulative archive still preserves all 12 historical false-negative records, and the anomaly archive retains its one existing record.
- The October 19 global earthquake CSV refreshed from zero to seven events, with the same eight column names in the integration script's normal order. New coverage ledgers record the actual analysis dates and do not mark assumed SYM-H context as measured coverage.
- The final exported-site browser suite passed **46/46 checks**, including all 51 stations across seven dates, chart values, actual baseline labels, scientific-figure links, fallback paths, map interaction/alignment, mobile/touch layouts, themes, exports, refresh races and network-failure recovery. No uncaught JavaScript errors or normal-use failed network requests were recorded.

Detailed file hashes, CSV row/column changes, real-observation checks, screenshots and browser results are saved under ignored `output/dogfood/method-2026-10-20/` (`data-merge.json`, `real-observation-audit.json`, and `candidate-final/results.json`). Deployment verification is recorded separately there after publication.
